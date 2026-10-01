"""Calendar features. Port of `calendar()` in analysis/scripts/eval_ratio_live.py.

Holiday dates and 설/추석 block starts are arguments so research and table calendars share one function.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

# range(-3, 7): days -3 through +6 around a block start.
BLOCK_OFFSETS = range(-3, 7)


def load_research_calendar(path) -> tuple[list[date], list[date], list[date]]:
    holidays: list[date] = []
    seol: list[date] = []
    chuseok: list[date] = []
    section = "holidays"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            lower = line.lower()
            if "seol" in lower:
                section = "seol"
            elif "chuseok" in lower:
                section = "chuseok"
            else:
                section = "holidays"
            continue
        day = date.fromisoformat(line)
        if section == "seol":
            seol.append(day)
        elif section == "chuseok":
            chuseok.append(day)
        else:
            holidays.append(day)
    return holidays, seol, chuseok


def block_starts(days: list[date]) -> list[date]:
    """Earliest date of each run of consecutive days."""
    starts: list[date] = []
    previous: date | None = None
    for day in sorted(days):
        if previous is None or (day - previous).days > 1:
            starts.append(day)
        previous = day
    return starts


def day_type(day: date, kinds: dict[date, str]) -> str:
    kind = kinds.get(day)
    if kind in ("seol", "chuseok"):
        return "myeongjeol"
    if kind:
        return "holiday"
    if day.weekday() >= 5:
        return "weekend"
    return "weekday"


def calendar(
    times: pd.DatetimeIndex,
    holidays: list[date],
    seol_starts: list[date],
    chuseok_starts: list[date],
) -> pd.DataFrame:
    """Features for an hourly index. `big` is 1 inside a 설 window and 2 inside a 추석 window."""
    if times.tz is not None:
        clock = times.tz_convert("Asia/Seoul").tz_localize(None)
    else:
        clock = times
    day = pd.DatetimeIndex(clock).normalize()
    holiday_index = pd.DatetimeIndex(pd.to_datetime(holidays))
    hol = day.isin(holiday_index)
    big = np.zeros(len(times), dtype=int)
    blocks = ((1, seol_starts), (2, chuseok_starts))
    for code, starts in blocks:
        for start in starts:
            window = [pd.Timestamp(start) + pd.Timedelta(days=offset) for offset in BLOCK_OFFSETS]
            big[day.isin(window)] = code
    if holidays:
        ordered = np.array(sorted(set(holidays)), dtype="datetime64[D]")
        values = day.values.astype("datetime64[D]")
        pos = np.searchsorted(ordered, values)
        nxt = (ordered[np.minimum(pos, len(ordered) - 1)] - values) / np.timedelta64(1, "D")
        prv = (values - ordered[np.maximum(pos - 1, 0)]) / np.timedelta64(1, "D")
        to_hol = np.clip(nxt.astype(float), 0, 8)
        from_hol = np.clip(prv.astype(float), 0, 8)
    else:
        to_hol = np.zeros(len(times))
        from_hol = np.zeros(len(times))
    stamp = pd.DatetimeIndex(clock)
    return pd.DataFrame(
        {
            "hour": stamp.hour.astype(int),
            "dow": stamp.dayofweek.astype(int),
            "month": stamp.month.astype(int),
            "hol": hol.astype(int),
            "hol_wkend": (hol & (stamp.dayofweek >= 5)).astype(int),
            "big": big,
            "to_hol": to_hol,
            "from_hol": from_hol,
        },
        index=times,
    )


def window_dates(start: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in BLOCK_OFFSETS]
