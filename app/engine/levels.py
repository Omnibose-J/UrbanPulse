"""Level thresholds from the last 90 days of raw live rows. Port of `thresholds()`."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from engine.parsers import KST


def level_of(pop: float, t1: float, t2: float, t3: float) -> int:
    """How many thresholds are at or below `pop`. Monotone in pop when t1 <= t2 <= t3."""
    return int(pop >= t1) + int(pop >= t2) + int(pop >= t3)


def thresholds_for(frame: pd.DataFrame) -> tuple[float, float, float, int, bool]:
    """`frame` has columns value and level for one place.

    Returns t1, t2, t3, based_on_days, ready. A missing level's threshold is infinity.
    Ready when at least three of the four levels 0..3 occur.
    """
    if frame.empty:
        return float("inf"), float("inf"), float("inf"), 0, False
    days = int(pd.to_datetime(frame["ts"]).dt.date.nunique())
    ready = frame["level"].nunique() >= 3
    cuts = []
    for level in (1, 2, 3):
        chosen = frame.loc[frame["level"] >= level, "value"]
        cuts.append(float(chosen.min()) if not chosen.empty else float("inf"))
    return cuts[0], cuts[1], cuts[2], days, ready


def window_start(today: date) -> date:
    return today - timedelta(days=90)


def as_kst_date(stamp) -> date:
    value = pd.Timestamp(stamp)
    if value.tzinfo is None:
        value = value.tz_localize(KST)
    else:
        value = value.tz_convert(KST)
    return value.date()
