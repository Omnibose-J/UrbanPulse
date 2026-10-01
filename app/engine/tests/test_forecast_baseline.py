"""Baseline uses only hours known before the issue date."""

import pandas as pd

from engine.hourly import baseline, baseline_values


def test_baseline_reads_no_live_row_on_or_after_issue_midnight():
    issue = pd.Timestamp("2026-08-10 00:00", tz="Asia/Seoul")
    index = []
    values = []
    for day in range(-40, 3):
        stamp = issue + pd.Timedelta(days=day, hours=15)
        index.append(stamp)
        values.append(100.0 + day)
    series = pd.Series(values, index=pd.DatetimeIndex(index))
    for horizon in range(8):
        found_times = []
        kmin = 1 if horizon < 7 else 2
        for k in range(kmin, kmin + 3):
            found_times.append(issue + pd.Timedelta(hours=15) - pd.Timedelta(days=7 * k))
        assert all(stamp < issue for stamp in found_times)
        if horizon < 7:
            assert found_times == [
                issue + pd.Timedelta(hours=15) - pd.Timedelta(days=7),
                issue + pd.Timedelta(hours=15) - pd.Timedelta(days=14),
                issue + pd.Timedelta(hours=15) - pd.Timedelta(days=21),
            ]
        else:
            assert found_times[0] == issue + pd.Timedelta(hours=15) - pd.Timedelta(days=14)
        assert baseline(series, issue + pd.Timedelta(hours=15), horizon) is not None


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
