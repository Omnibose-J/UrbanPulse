"""Hourly live and commerce values.

The engine floors timestamps into `[h, h+1)`. `--grid research` reproduces the old
round-half-even grid from `live_hourly` (even hours average the stamps that land there).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from engine.parsers import KST


def as_kst(ts: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize(KST)
    return stamp.tz_convert(KST)


def floor_hour(ts: datetime) -> pd.Timestamp:
    return as_kst(ts).floor("h")


def research_hour(ts: datetime) -> pd.Timestamp:
    """Round half-even to the hour. 10:30 → 10:00, 11:30 → 12:00."""
    return as_kst(ts).round("h")


def hourly_frame(rows: pd.DataFrame, grid: str) -> pd.DataFrame:
    """Rows need place_id, ts, value, and optionally level.

    `floor`: mean value in the hour; level of the latest row.
    `research`: round half-even, keep the first row of each exact timestamp, then the mean
    of the values that land in that hour (the research `live_hourly` grid).
    """
    if rows.empty:
        return pd.DataFrame(columns=["place_id", "hour", "value", "level"])
    frame = rows.copy()
    frame["ts"] = frame["ts"].map(as_kst)
    frame = frame.sort_values(["place_id", "ts"])
    if grid == "research":
        frame = frame.drop_duplicates(["place_id", "ts"], keep="first")
        frame["hour"] = frame["ts"].map(research_hour)
        grouped = frame.groupby(["place_id", "hour"], as_index=False).agg(
            value=("value", "mean"), level=("level", "last")
        )
        return grouped
    if grid != "floor":
        raise ValueError(f"unknown grid: {grid}")
    frame["hour"] = frame["ts"].map(floor_hour)
    latest = frame.groupby(["place_id", "hour"], as_index=False).tail(1)[["place_id", "hour", "level"]]
    means = frame.groupby(["place_id", "hour"], as_index=False).agg(value=("value", "mean"))
    return means.merge(latest, on=["place_id", "hour"])


def baseline_values(series: pd.Series, target: pd.Timestamp, horizon_d: int) -> list[float]:
    """The up-to-three same-weekday hourly values the baseline may use. Missing hours are omitted."""
    kmin = 1 if horizon_d < 7 else 2
    found: list[float] = []
    for k in range(kmin, kmin + 3):
        stamp = target - pd.Timedelta(days=7 * k)
        if stamp in series.index and pd.notna(series.loc[stamp]):
            found.append(float(series.loc[stamp]))
    return found


def baseline(series: pd.Series, target: pd.Timestamp, horizon_d: int) -> float | None:
    """Mean of the existing week values. Fewer than 2 of the 3 → not ready."""
    found = baseline_values(series, target, horizon_d)
    if len(found) < 2:
        return None
    return sum(found) / len(found)
