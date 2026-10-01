"""Load research extracts into `live_obs` and `commerce_obs`. One-off: `python -m engine backfill`.

Several snapshots can share one observation time. The row with the latest `snap_time` wins.
Rows whose poi is not in `places` are skipped and counted. One transaction per file.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from engine import db, settings
from engine.log import log
from engine.parsers import COMMERCE_TIME_FMT, LIVE_TIME_FMT, kst, parse_commerce_level, parse_live_level

JOB = "backfill"
CHUNK = 5000

LIVE_FILES = (
    "analysis/data/obs_hist.csv",
    "analysis/data/obs_hist_aug.csv",
    "analysis/data/obs.csv",
)
COMMERCE_FILES = (
    "analysis/data/cmrcl.csv",
    "analysis/data/cmrcl_rest.csv",
)
COMMERCE_CATS = (
    "음식·음료",
    "유통",
    "패션·뷰티",
    "여가·오락",
    "생활서비스",
    "의료·건강",
    "교육",
    "숙박",
)

_LIVE_UPSERT = """
insert into live_obs (place_id, ts, pop_min, pop_max, level, age_rates, male_rate)
values (%(place_id)s, %(ts)s, %(pop_min)s, %(pop_max)s, %(level)s, %(age_rates)s, %(male_rate)s)
on conflict (place_id, ts) do update set
  pop_min = excluded.pop_min,
  pop_max = excluded.pop_max,
  level = excluded.level,
  age_rates = excluded.age_rates,
  male_rate = excluded.male_rate
where live_obs.pop_min is distinct from excluded.pop_min
   or live_obs.pop_max is distinct from excluded.pop_max
   or live_obs.level is distinct from excluded.level
   or live_obs.age_rates is distinct from excluded.age_rates
   or live_obs.male_rate is distinct from excluded.male_rate
"""

_COMMERCE_UPSERT = """
insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts)
values (%(place_id)s, %(ts)s, %(level)s, %(pay_cnt)s, %(cat_counts)s)
on conflict (place_id, ts) do update set
  level = excluded.level,
  pay_cnt = excluded.pay_cnt,
  cat_counts = excluded.cat_counts
where commerce_obs.level is distinct from excluded.level
   or commerce_obs.pay_cnt is distinct from excluded.pay_cnt
   or commerce_obs.cat_counts is distinct from excluded.cat_counts
"""


def keep_latest(
    rows: Iterable[dict[str, str]],
    key_fn: Callable[[dict[str, str]], tuple],
    snap_field: str = "snap_time",
) -> dict[tuple, dict[str, str]]:
    """Keep, for each key, the row with the greatest snap_time. Ties keep the later row."""
    best: dict[tuple, dict[str, str]] = {}
    snaps: dict[tuple, str] = {}
    for row in rows:
        key = key_fn(row)
        snap = row[snap_field]
        prev = snaps.get(key)
        if prev is None or snap >= prev:
            snaps[key] = snap
            best[key] = row
    return best


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _require_int(value: str, field: str) -> int:
    text = (value or "").strip()
    if text == "":
        raise ValueError(f"missing {field}")
    if "." in text:
        number = float(text)
        if not number.is_integer():
            raise ValueError(f"non-integer {field}: {value}")
        return int(number)
    return int(text)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _live_record(row: dict[str, str]) -> dict[str, Any]:
    return {
        "place_id": row["poi"],
        "ts": kst(row["ppltn_time"], LIVE_TIME_FMT),
        "pop_min": _require_int(row["pmin"], "pmin"),
        "pop_max": _require_int(row["pmax"], "pmax"),
        "level": parse_live_level(row["lvl"]),
        "age_rates": None,
        "male_rate": None,
    }


def _commerce_record(row: dict[str, str]) -> dict[str, Any]:
    counts = {name: _require_int(row[f"cat_{name}"], f"cat_{name}") for name in COMMERCE_CATS}
    return {
        "place_id": row["poi"],
        "ts": kst(row["cmrcl_time"], COMMERCE_TIME_FMT),
        "level": parse_commerce_level(row["lvl"]),
        "pay_cnt": _require_int(row["pay_cnt"], "pay_cnt"),
        "cat_counts": Jsonb(counts),
    }


def _load_files(
    conn: Any,
    root: Path,
    rels: tuple[str, ...],
    place_ids: set[str],
    key_fn: Callable[[dict[str, str]], tuple],
    to_record: Callable[[dict[str, str]], dict[str, Any]],
    sql: str,
) -> tuple[int, list[str]]:
    """Dedupe across the files, then upsert each file's winners in its own transaction."""
    best: dict[tuple, tuple[str, str, dict[str, str]]] = {}
    per_file: dict[str, dict[str, int]] = {}
    skipped_pois: set[str] = set()
    for rel in rels:
        path = root / rel
        raw = _read(path)
        skipped = 0
        for row in raw:
            poi = row.get("poi", "")
            if poi not in place_ids:
                skipped += 1
                if poi:
                    skipped_pois.add(poi)
                continue
            key = key_fn(row)
            snap = row["snap_time"]
            prev = best.get(key)
            if prev is None or snap >= prev[0]:
                best[key] = (snap, path.name, row)
        per_file[path.name] = {"read": len(raw), "skipped": skipped, "written": 0}

    winners: dict[str, list[dict[str, Any]]] = {Path(rel).name: [] for rel in rels}
    for _snap, name, row in best.values():
        winners[name].append(to_record(row))
        per_file[name]["written"] += 1

    for rel in rels:
        name = Path(rel).name
        affected = 0
        with conn.transaction():
            with conn.cursor() as cur:
                for chunk in _chunks(winners[name], CHUNK):
                    cur.executemany(sql, chunk)
                    if cur.rowcount > 0:
                        affected += cur.rowcount
        stats = per_file[name]
        log(
            JOB,
            "file",
            name=name,
            read=stats["read"],
            written=stats["written"],
            skipped=stats["skipped"],
            affected=affected,
        )
    return sum(stats["skipped"] for stats in per_file.values()), sorted(skipped_pois)


def _counts(conn: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with conn.cursor() as cur:
        for table in ("live_obs", "commerce_obs"):
            cur.execute(f"select count(*), min(ts), max(ts) from {table}")
            count, start, end = cur.fetchone()
            out[table] = {
                "count": count,
                "min": None if start is None else start.isoformat(),
                "max": None if end is None else end.isoformat(),
            }
    return out


def run() -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    root = settings.REPO_ROOT
    missing = [rel for rel in (*LIVE_FILES, *COMMERCE_FILES) if not (root / rel).exists()]
    if missing:
        log(JOB, "fail", reason="missing files", files=missing)
        return 1
    log(JOB, "start")
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            cur.execute("select id from places")
            place_ids = {row[0] for row in cur.fetchall()}
        if not place_ids:
            log(JOB, "fail", reason="places is empty")
            return 1
        conn.commit()
        live_skipped, live_pois = _load_files(
            conn,
            root,
            LIVE_FILES,
            place_ids,
            lambda row: (row["poi"], row["ppltn_time"]),
            _live_record,
            _LIVE_UPSERT,
        )
        commerce_skipped, commerce_pois = _load_files(
            conn,
            root,
            COMMERCE_FILES,
            place_ids,
            lambda row: (row["poi"], row["cmrcl_time"]),
            _commerce_record,
            _COMMERCE_UPSERT,
        )
        totals = _counts(conn)
    log(
        JOB,
        "done",
        live_obs=totals["live_obs"]["count"],
        live_min=totals["live_obs"]["min"],
        live_max=totals["live_obs"]["max"],
        commerce_obs=totals["commerce_obs"]["count"],
        commerce_min=totals["commerce_obs"]["min"],
        commerce_max=totals["commerce_obs"]["max"],
        live_skipped=live_skipped,
        commerce_skipped=commerce_skipped,
        skipped_pois=sorted(set(live_pois) | set(commerce_pois)),
    )
    return 0
