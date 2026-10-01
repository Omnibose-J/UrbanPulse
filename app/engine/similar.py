"""Similar A1 places. Each feature block is L2-normalised, then cosine similarity picks the top 10."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from engine.parsers import COMMERCE_CATEGORIES, KST


def use_visitors(distinct_dates: dict[str, int]) -> bool:
    """True only when every place has age rates on at least 28 distinct dates."""
    if not distinct_dates:
        return False
    return all(count >= 28 for count in distinct_dates.values())


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def top_others(
    ids: list[str], vectors: list[list[float]], limit: int = 10
) -> dict[str, list[tuple[int, str, float]]]:
    """Rank 1..limit. Ties break by place id. A place is never its own neighbour."""
    ranked: dict[str, list[tuple[int, str, float]]] = {}
    for index, place_id in enumerate(ids):
        scored = []
        for other_index, other_id in enumerate(ids):
            if other_index == index:
                continue
            scored.append((cosine(vectors[index], vectors[other_index]), other_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        ranked[place_id] = [
            (rank, other_id, score) for rank, (score, other_id) in enumerate(scored[:limit], start=1)
        ]
    return ranked


def feature_vectors(
    ids: list[str],
    commerce: dict[str, list[float]],
    categories: dict[str, str | None],
    visitors: dict[str, list[float]] | None,
) -> list[list[float]]:
    labels = sorted({categories.get(place_id) or "" for place_id in ids})
    vectors = []
    for place_id in ids:
        mix = l2_normalize(list(commerce.get(place_id, [0.0] * len(COMMERCE_CATEGORIES))))
        category = categories.get(place_id) or ""
        one_hot = l2_normalize([1.0 if category == label else 0.0 for label in labels])
        blocks = [mix, one_hot]
        if visitors is not None:
            blocks.append(l2_normalize(visitors.get(place_id, [])))
        vectors.append([value for block in blocks for value in block])
    return vectors


def replace_similar(conn, today: date) -> dict:
    """Replace similar_places for A1 places that are on. Returns whether the visitors block was used."""
    start = datetime.combine(today - timedelta(days=28), datetime.min.time()).replace(tzinfo=KST)
    end = datetime.combine(today, datetime.min.time()).replace(tzinfo=KST)
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, category from places
            where tier = 'A1' and serve_state = 'on'
            order by id
            """
        )
        places = cur.fetchall()
        ids = [row[0] for row in places]
        categories = {row[0]: row[1] for row in places}
        if len(ids) < 2:
            cur.execute("delete from similar_places")
            return {"places": len(ids), "visitors_block": False, "rows": 0}
        cur.execute(
            """
            select place_id, cat_counts
            from commerce_obs
            where place_id = any(%s) and ts >= %s and ts < %s
            """,
            (ids, start, end),
        )
        commerce_rows = cur.fetchall()
        cur.execute(
            """
            select place_id, (ts at time zone 'Asia/Seoul')::date, age_rates, male_rate
            from live_obs
            where place_id = any(%s) and ts >= %s and ts < %s
            """,
            (ids, start, end),
        )
        live_rows = cur.fetchall()
    commerce = _commerce_shares(ids, commerce_rows)
    visitors, visitors_on = _visitors(ids, live_rows)
    vectors = feature_vectors(ids, commerce, categories, visitors if visitors_on else None)
    ranked = top_others(ids, vectors)
    payload = [
        (place_id, other_id, score, rank)
        for place_id, rows in ranked.items()
        for rank, other_id, score in rows
    ]
    with conn.cursor() as cur:
        cur.execute("delete from similar_places")
        cur.executemany(
            """
            insert into similar_places (place_id, other_id, score, rank)
            values (%s, %s, %s, %s)
            """,
            payload,
        )
    return {"places": len(ids), "visitors_block": visitors_on, "rows": len(payload)}


def _commerce_shares(ids: list[str], rows: list[tuple]) -> dict[str, list[float]]:
    totals = {place_id: [0.0] * len(COMMERCE_CATEGORIES) for place_id in ids}
    sums = {place_id: 0.0 for place_id in ids}
    names = list(COMMERCE_CATEGORIES)
    for place_id, counts in rows:
        if place_id not in totals or not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            try:
                amount = float(value or 0)
            except (TypeError, ValueError):
                continue
            sums[place_id] += amount
            if key in names:
                totals[place_id][names.index(key)] += amount
    shares = {}
    for place_id in ids:
        whole = sums[place_id]
        if whole <= 0:
            shares[place_id] = [0.0] * len(COMMERCE_CATEGORIES)
        else:
            shares[place_id] = [value / whole for value in totals[place_id]]
    return shares


def _visitors(ids: list[str], rows: list[tuple]) -> tuple[dict[str, list[float]], bool]:
    dates: dict[str, set] = {place_id: set() for place_id in ids}
    buckets: dict[str, dict[str, list[float]]] = {place_id: {} for place_id in ids}
    males: dict[str, list[float]] = {place_id: [] for place_id in ids}
    for place_id, day, rates, male in rows:
        if place_id not in dates or rates is None:
            continue
        dates[place_id].add(day)
        if isinstance(rates, dict):
            for key, value in rates.items():
                if value is None:
                    continue
                buckets[place_id].setdefault(str(key), []).append(float(value))
        if male is not None:
            males[place_id].append(float(male))
    counts = {place_id: len(days) for place_id, days in dates.items()}
    if not use_visitors(counts):
        return {}, False
    keys = sorted({key for place in buckets.values() for key in place})
    vectors = {}
    for place_id in ids:
        means = []
        for key in keys:
            values = buckets[place_id].get(key) or []
            means.append(sum(values) / len(values) if values else 0.0)
        male_values = males[place_id]
        means.append(sum(male_values) / len(male_values) if male_values else 0.0)
        vectors[place_id] = means
    return vectors, True
