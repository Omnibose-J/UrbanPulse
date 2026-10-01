"""Small checks for the ported flow helpers. No database and no shapefiles."""

import pandas as pd

from engine.tierb.flows import norm, prefers_ridership, smooth_share, weekly


def test_norm_strips_a_parenthetical_and_the_station_suffix():
    assert norm("서울역") == "서울"
    assert norm("서울(2)역") == "서울"


def test_share_smoothing_averages_the_previous_bin():
    share = pd.DataFrame([[float(hour) for hour in range(24)]])
    smoothed = smooth_share(share)
    assert list(smoothed.columns) == list(range(24))
    assert smoothed.iloc[0, 0] == (0 + 23) / 2
    assert smoothed.iloc[0, 5] == (5 + 4) / 2


def test_weekly_drops_holiday_dates():
    index = pd.to_datetime(["2026-10-05 10:00", "2026-10-06 10:00", "2026-10-12 10:00"])
    series = pd.Series([9.0, 3.0, 3.0], index=index)
    result = weekly(series, ["2026-10-05"])
    assert result.loc[("wk", 10)] == 3.0
    assert ("wk", 10) in result.index


def test_selection_rule_at_the_zero_boundary():
    assert prefers_ridership(-0.01)
    assert not prefers_ridership(0.0)
    assert not prefers_ridership(0.01)
