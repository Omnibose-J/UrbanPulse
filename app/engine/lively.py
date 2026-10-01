"""A1 activity profiles. Port of the p90 profile in exp_e3c_calm.py, on the engine's hourly grid."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from engine.calendar_feats import day_type
from engine.parsers import KST

PURPOSES = ("all", "food", "shop")


def hourly_commerce(rows: pd.DataFrame) -> pd.DataFrame:
    """Mean pay and category counts inside each clock hour."""
    if rows.empty:
        return pd.DataFrame(columns=["place_id", "hour", "all", "food", "shop", "day"])
    frame = rows.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True).dt.tz_convert(KST)
    frame["hour"] = frame["ts"].dt.floor("h")
    grouped = frame.groupby(["place_id", "hour"], as_index=False).agg(
        all_=("pay_cnt", "mean"), food=("food", "mean"), shop=("shop", "mean")
    )
    grouped = grouped.rename(columns={"all_": "all"})
    grouped["day"] = grouped["hour"].dt.date
    return grouped


def profile_rows(
    hourly: pd.DataFrame,
    kinds: dict[date, str],
    today: date,
) -> list[dict]:
    """One row per day type and hour 0..23. a_* is null when p90 is missing or the day type is thin."""
    if hourly.empty:
        return []
    history = hourly[hourly["day"] < today].copy()
    if history.empty:
        return []
    history["day_type"] = history["day"].map(lambda day: day_type(day, kinds))
    recent_start = today - timedelta(days=56)
    recent = history[(history["day"] >= recent_start) & (history["day_type"] != "weekday")]
    recent = recent[recent["hour"].dt.hour.between(9, 23)]
    p90 = {purpose: _quantile(recent[purpose]) for purpose in PURPOSES}
    out = []
    for dtype, part in history.groupby("day_type"):
        dates = int(part["day"].nunique())
        thin = dates < (1 if dtype == "myeongjeol" else 4)
        for hour in range(24):
            slot = part[part["hour"].dt.hour == hour]
            row = {
                "day_type": dtype,
                "hour": hour,
                "n_days": int(slot["day"].nunique()),
                "a_all": None,
                "a_food": None,
                "a_shop": None,
            }
            if not thin:
                for purpose, column in (("all", "a_all"), ("food", "a_food"), ("shop", "a_shop")):
                    scale = p90[purpose]
                    if scale is None or scale == 0 or slot.empty:
                        continue
                    row[column] = float((slot[purpose] / scale).mean())
            out.append(row)
    return out


def _quantile(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float(clean.quantile(0.9))
