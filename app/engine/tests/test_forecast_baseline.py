"""The readiness rule of the baseline. That it reads nothing from issue time on is in test_forecast_run."""

import pandas as pd

from engine.hourly import baseline, baseline_values


def test_two_weeks_are_ready_and_one_week_is_not():
    target = pd.Timestamp("2026-08-10 15:00", tz="Asia/Seoul")
    two = pd.Series(
        [10.0, 30.0],
        index=pd.DatetimeIndex([target - pd.Timedelta(days=7), target - pd.Timedelta(days=14)]),
    )
    one = pd.Series([10.0], index=pd.DatetimeIndex([target - pd.Timedelta(days=7)]))
    assert baseline(two, target, 0) == 20.0
    assert baseline(one, target, 0) is None
    assert len(baseline_values(two, target, 7)) == 1
