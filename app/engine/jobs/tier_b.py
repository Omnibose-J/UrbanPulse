"""Tier B check. `python -m engine tier_b --check` reproduces the E1 figures and writes nothing."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine import db, settings
from engine.hourly import hourly_frame
from engine.tierb.flows import buffers, dtype_of, oa_flow, st_flow, station_groups, weekly

HOURS = list(range(9, 24))
TARGETS = (0.84, 6.67, 62.28)
TOLERANCES = (0.02, 3.0, 2.0)


def _holidays() -> list[pd.Timestamp]:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    with db.connect(url) as conn:
        rows = conn.execute("select date from holidays").fetchall()
    return [pd.Timestamp(row[0]) for row in rows]


def _research_live() -> pd.DataFrame:
    root = settings.REPO_ROOT / "analysis" / "data"
    names = ("obs_hist.csv", "obs_hist_aug.csv", "obs.csv")
    frames = [pd.read_csv(root / name, parse_dates=["ppltn_time"]) for name in names]
    obs = pd.concat(frames, ignore_index=True)
    obs["value"] = (obs.pmin + obs.pmax) / 2
    obs["level"] = 0
    obs = obs.rename(columns={"poi": "place_id", "ppltn_time": "ts"})
    hourly = hourly_frame(obs[["place_id", "ts", "value", "level"]], "research")
    wide = hourly.pivot(index="hour", columns="place_id", values="value").sort_index()
    wide.index = pd.DatetimeIndex(wide.index).tz_convert("Asia/Seoul").tz_localize(None)
    return wide


def _figures(
    live: pd.DataFrame, oa: pd.DataFrame, ridership: pd.DataFrame, holidays
) -> tuple[float, float, float]:
    test = live[live.index >= "2026-08-01"]
    test = test[test.index <= "2026-09-29 23:00:00"]
    correlations = []
    agreements = []
    for place in oa.columns:
        if place not in live.columns:
            continue
        chosen = weekly(oa[place], holidays)
        if place in ridership.columns:
            other = weekly(ridership[place], holidays)
            if chosen.corr(other) < 0.0:
                chosen = other
        truth = weekly(test[place], holidays)
        correlations.append(float(chosen.corr(truth)))
        observed = test[place].dropna()
        holiday_days = pd.to_datetime(list(holidays))
        observed = observed[~observed.index.normalize().isin(holiday_days)]
        observed = observed[observed.index.hour.isin(range(9, 23))]
        if observed.empty:
            continue
        level_hours = chosen.index.get_level_values(1).isin(HOURS)
        relative = chosen / chosen[level_hours].quantile(0.9)
        keys = list(zip(dtype_of(observed.index), observed.index.hour, strict=True))
        predicted = relative.reindex(keys).to_numpy()
        keep = ~np.isnan(predicted)
        actual = (observed / observed.quantile(0.9)).to_numpy()
        same = np.digitize(predicted[keep], [0.5, 0.9]) == np.digitize(actual[keep], [0.5, 0.9])
        agreements.append(same)
    median = float(np.median(correlations))
    weak = float(np.mean([value < 0.3 for value in correlations]) * 100)
    agreement = float(np.concatenate(agreements).mean() * 100)
    return median, weak, agreement


def check() -> int:
    holidays = _holidays()
    groups, coords = station_groups()
    points = [
        (place, coords.loc[station, "LOT"], coords.loc[station, "LAT"])
        for place, stations in groups.items()
        for station in stations
    ]
    circles = buffers([row[0] for row in points], [row[1] for row in points], [row[2] for row in points])
    live = _research_live()
    oa = oa_flow(circles)
    ridership = st_flow(groups)
    median, weak, agreement = _figures(live, oa, ridership, holidays)
    labels = ("median r", "r<0.3 share %", "three-level agreement %")
    measured = (median, weak, agreement)
    for label, value, target, tolerance in zip(labels, measured, TARGETS, TOLERANCES, strict=True):
        verdict = "PASS" if abs(value - target) <= tolerance else "FAIL"
        print(f"{label}: {value:.2f} vs {target:.2f} {verdict} (tolerance {tolerance})")
    return 0


def run(check_only: bool = False) -> int:
    if check_only:
        return check()
    from engine.tierb.profile import build_profiles
    from engine.tierb.stations import load_stations

    code = load_stations()
    if code != 0:
        return code
    return build_profiles()
