"""Level thresholds from the last 90 days of raw live rows. Port of `thresholds()`."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine.parsers import KST


def level_of(pop: float, t1: float, t2: float, t3: float) -> int:
    """How many thresholds are at or below `pop`. Monotone in pop when t1 <= t2 <= t3."""
    return int(pop >= t1) + int(pop >= t2) + int(pop >= t3)


def thresholds_for(frame: pd.DataFrame, rule: str = "split") -> tuple[float, float, float, int, bool]:
    """`frame` has columns value and level for one place.

    Returns t1, t2, t3, based_on_days, ready. A missing level's threshold is infinity.
    Ready when at least three of the four levels 0..3 occur.
    `rule="min"` is the old lowest-value cut. `rule="split"` is the error-minimising cut
    and the only rule forecast uses.
    """
    if rule not in ("split", "min"):
        raise ValueError(f"unknown threshold rule: {rule}")
    if frame.empty:
        return float("inf"), float("inf"), float("inf"), 0, False
    days = int(pd.to_datetime(frame["ts"]).dt.date.nunique())
    ready = frame["level"].nunique() >= 3
    cuts = [_cut(frame, level, rule) for level in (1, 2, 3)]
    if rule == "split":
        cuts[1] = max(cuts[1], cuts[0])
        cuts[2] = max(cuts[2], cuts[1])
    return cuts[0], cuts[1], cuts[2], days, ready


def _cut(frame: pd.DataFrame, level: int, rule: str) -> float:
    hi = frame.loc[frame["level"] >= level, "value"]
    if hi.empty:
        return float("inf")
    if rule == "min":
        return float(hi.min())
    lo = frame.loc[frame["level"] < level, "value"]
    if lo.empty:
        return float(hi.min())
    hi_sorted = np.sort(hi.to_numpy(dtype=float))
    lo_sorted = np.sort(lo.to_numpy(dtype=float))
    candidates = np.unique(np.concatenate([hi_sorted, lo_sorted]))
    hi_below = np.searchsorted(hi_sorted, candidates, side="left")
    lo_at_or_above = lo_sorted.size - np.searchsorted(lo_sorted, candidates, side="left")
    errors = hi_below + lo_at_or_above
    return float(candidates[int(np.argmin(errors))])


def window_start(today: date) -> date:
    return today - timedelta(days=90)


def as_kst_date(stamp) -> date:
    value = pd.Timestamp(stamp)
    if value.tzinfo is None:
        value = value.tz_localize(KST)
    else:
        value = value.tz_convert(KST)
    return value.date()
