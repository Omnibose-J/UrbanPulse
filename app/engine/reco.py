"""One recommendation row, then alternatives across dates and nearby places.

`windows()` is the research function from exp_e3_e4_reco.py. Allowed hours are the
cells with rating 1, which is narrower than the research lively-hour set.
"""

from __future__ import annotations

import re
from datetime import date

from engine.flags import FlagFile
from engine.geo import haversine_km

STRIP_HOURS = tuple(range(9, 24))
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ALLOWED_LEVEL = {"calm": 1, "moderate": 2, "busy_ok": 3}
ACTIVITY_COLUMN = {"sight": "a_all", "food": "a_food", "shop": "a_shop"}
PURPOSES = {"A1": ("sight", "food", "shop"), "A2": ("none",), "B": ("none",)}
_SPAN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d$")


class OpenHoursError(ValueError):
    """An open_hours span is not HH:MM-HH:MM."""


def require_open_span(value: str) -> str:
    if _SPAN.fullmatch(value) is None:
        raise OpenHoursError("open_hours must be HH:MM-HH:MM")
    return value


def group_of(tier: str, foreign_heavy: bool) -> str:
    if tier == "B":
        return "b"
    if tier == "A2":
        return "a2"
    if foreign_heavy:
        return "a1_foreign"
    return "a1"


def purposes_for(tier: str) -> tuple[str, ...]:
    return PURPOSES[tier]


def open_hours_for(tier: str, open_hours: dict | None, day: date) -> set[int]:
    """Hours whose whole clock hour sits inside the place's open range."""
    if tier == "A1":
        base = set(range(9, 24))
    elif tier == "B":
        base = set(range(9, 23))
    else:
        base = set(range(9, 21))
    if not open_hours:
        return base
    span = (open_hours.get("hours") or {}).get(WEEKDAYS[day.weekday()])
    if span is None:
        return set()
    start_text, end_text = require_open_span(str(span)).split("-")
    start, end = _minutes(start_text), _minutes(end_text)
    inside = {hour for hour in STRIP_HOURS if start <= hour * 60 and (hour + 1) * 60 <= end}
    return base & inside


def choose_windows(scores: dict[int, float], allowed: set[int]) -> list[tuple[tuple[int, ...], float]]:
    """Port of research `windows()`. Ties keep earlier hours, and a 1-hour candidate before a 2-hour one."""
    candidates: list[tuple[tuple[int, ...], float]] = []
    hours = [hour for hour in STRIP_HOURS if hour in allowed]
    for hour in hours:
        candidates.append(((hour,), scores[hour]))
        if hour + 1 in allowed:
            candidates.append(((hour, hour + 1), (scores[hour] + scores[hour + 1]) / 2))
    candidates.sort(key=lambda item: -item[1])
    used: set[int] = set()
    chosen: list[tuple[tuple[int, ...], float]] = []
    for window, score in candidates:
        if used.isdisjoint(window):
            chosen.append((window, score))
            used.update(window)
        if len(chosen) == 3:
            break
    return chosen


def build_row(
    place: dict,
    day: date,
    tolerance: str,
    purpose: str,
    hourly: dict[int, dict],
    flags: FlagFile,
    day_kind: str,
    now_hour: int | None = None,
) -> dict:
    state, off_reason, strip = _state(place, day, tolerance, purpose, hourly, flags, day_kind)
    base = {
        "place_id": place["id"],
        "date": day,
        "tolerance": tolerance,
        "purpose": purpose,
        "tier": place["tier"],
        "state": state,
        "off_reason": off_reason,
    }
    if state == "off":
        return {
            **base,
            "windows": None,
            "no_window": None,
            "hours": None,
            "strip_mode": None,
            "alt_dates": None,
            "alt_places": None,
            "p90": None,
            "lively_min": None,
        }
    lively_min = flags.lively_min.get(purpose) if place["tier"] == "A1" else None
    cells, windows, no_window = _cells(place, day, tolerance, purpose, hourly, lively_min, now_hour)
    return {
        **base,
        "windows": windows,
        "no_window": no_window,
        "hours": cells,
        "strip_mode": strip,
        "alt_dates": [],
        "alt_places": [],
        "p90": None,
        "lively_min": lively_min,
    }


def fill_alternatives(
    rows: list[dict],
    pool: list[dict],
    similar: dict[str, list[str]],
    coords: dict[str, tuple[float | None, float | None]],
) -> None:
    """Fill alt_dates and alt_places on `rows`. `similar` lists other places in rank order."""
    index = {(row["place_id"], row["date"], row["tolerance"], row["purpose"]): row for row in pool}
    groups: dict[tuple, list[dict]] = {}
    for other in pool:
        key = (other["place_id"], other["tolerance"], other["purpose"])
        groups.setdefault(key, []).append(other)
    for row in rows:
        if row["state"] == "off":
            continue
        key = (row["place_id"], row["tolerance"], row["purpose"])
        row["alt_dates"] = _alt_dates(row, groups.get(key, []))
        if row["tier"] in ("A2", "B"):
            row["alt_places"] = []
            continue
        row["alt_places"] = _alt_places(row, index, similar.get(row["place_id"], []), coords)


def log_candidates(rows: list[dict], issued: date) -> list[dict]:
    target = issued.toordinal() + 3
    return [
        row
        for row in rows
        if (
            row.get("tier") != "B"
            and row["date"].toordinal() == target
            and row["state"] in ("on", "reference")
        )
    ]


def _state(place, day, tolerance, purpose, hourly, flags: FlagFile, day_kind: str):
    if place["serve_state"] == "preparing":
        return "off", "preparing", None
    slots = [hourly.get(hour) for hour in STRIP_HOURS]
    if any(slot is None or not slot.get("ready") or slot.get("level") is None for slot in slots):
        return "off", "preparing", None
    if place["tier"] == "A1" and any(_activity(place["tier"], purpose, slot) is None for slot in slots):
        return "off", "preparing", None
    if place["tier"] == "A1" and day_kind == "myeongjeol":
        return "off", "myeongjeol", None
    if place["tier"] == "B" and day_kind in ("holiday", "myeongjeol"):
        return "off", "unverified", None
    group = group_of(place["tier"], bool(place["foreign_heavy"]))
    state, strip = flags.lookup(group, purpose, tolerance)
    if state == "off":
        reason = "failed" if flags.known(group, purpose, tolerance) else "unverified"
        return "off", reason, None
    return state, None, strip


def _cells(place, day, tolerance, purpose, hourly, lively_min, now_hour: int | None):
    tier = place["tier"]
    open_hours = open_hours_for(tier, place.get("open_hours"), day)
    minimum = 0.0 if lively_min is None else lively_min
    cells = []
    scores: dict[int, float] = {}
    allowed: set[int] = set()
    for hour in STRIP_HOURS:
        slot = hourly[hour]
        activity = _activity(tier, purpose, slot)
        level = int(slot["level"])
        reason = _reason(tier, hour, open_hours, activity, level, tolerance, minimum)
        rating = 1 if reason == "fit" else 0
        act = None
        if tier == "A1":
            act = "lively" if activity >= minimum else "quiet"
        cells.append(
            {
                "h": hour,
                "rating": rating,
                "in_window": False,
                "reason": reason,
                "crowd": level,
                "act": act,
            }
        )
        if rating == 1 and (now_hour is None or hour >= now_hour):
            allowed.add(hour)
            scores[hour] = _score(tolerance, float(activity), level)
    chosen = choose_windows(scores, allowed)
    covered: set[int] = set()
    windows = []
    for hours, score in chosen:
        covered.update(hours)
        levels = [int(hourly[hour]["level"]) for hour in hours]
        windows.append(
            {
                "hours": list(hours),
                "score": round(float(score), 3),
                "crowd": max(levels),
                "act": purpose if tier == "A1" else None,
                "act_level": "lively" if tier == "A1" else None,
            }
        )
    for cell in cells:
        cell["in_window"] = cell["h"] in covered
    return cells, windows, len(windows) == 0


def _reason(tier, hour, open_hours, activity, level, tolerance, lively_min) -> str:
    if hour not in open_hours:
        return "outside_hours"
    if tier == "A1" and activity < lively_min:
        return "closed"
    if level > ALLOWED_LEVEL[tolerance]:
        return "too_busy"
    return "fit"


def _score(tolerance: str, activity: float, level: int) -> float:
    if tolerance == "calm":
        return activity - 0.6 * level
    if tolerance == "moderate":
        return activity - 0.5 * abs(level - 1)
    return activity - 0.2 * max(level - 2, 0)


def _activity(tier: str, purpose: str, slot: dict) -> float | None:
    if tier in ("A2", "B"):
        return 1.0
    value = slot.get(ACTIVITY_COLUMN[purpose])
    if value is None:
        return None
    return float(value)


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _best(row: dict) -> dict | None:
    windows = row.get("windows") or []
    if not windows:
        return None
    return windows[0]


def _serves(row: dict) -> bool:
    return row["state"] in ("on", "reference") and _best(row) is not None


def _alt_dates(row: dict, pool: list[dict]) -> list[dict]:
    own = _best(row)
    found = []
    for other in pool:
        if other is row:
            continue
        if other["place_id"] != row["place_id"]:
            continue
        if other["tolerance"] != row["tolerance"] or other["purpose"] != row["purpose"]:
            continue
        if other["date"] == row["date"] or not _serves(other):
            continue
        best = _best(other)
        if own is not None and best["score"] <= own["score"]:
            continue
        found.append(best | {"date": other["date"].isoformat(), "score": best["score"]})
    # Equal scores are common; the nearer date wins, so a rebuild cannot reorder them.
    found.sort(key=lambda item: (-item["score"], item["date"]))
    return [{"date": item["date"], "hours": item["hours"], "score": item["score"]} for item in found[:2]]


def _alt_places(row, index, neighbours, coords) -> list[dict]:
    own = _best(row)
    here = coords.get(row["place_id"])
    if here is None or here[0] is None or here[1] is None:
        return []
    found = []
    for other_id in neighbours:
        there = coords.get(other_id)
        if there is None or there[0] is None or there[1] is None:
            continue
        if haversine_km(here[0], here[1], there[0], there[1]) > 5:
            continue
        other = index.get((other_id, row["date"], row["tolerance"], row["purpose"]))
        if other is None or not _serves(other):
            continue
        best = _best(other)
        if own is not None and best["crowd"] > own["crowd"] - 1:
            continue
        found.append({"place_id": other_id, "hours": best["hours"], "crowd": best["crowd"]})
        if len(found) == 3:
            break
    return found
