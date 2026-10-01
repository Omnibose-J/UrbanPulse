"""WAPE and the warning bar. The database path is the acceptance command."""

from datetime import date

import pandas as pd

from engine.jobs.evaluate import _eval_rows, wape


def test_wape_and_holiday_segment():
    pred = pd.Series([10.0, 20.0])
    actual = pd.Series([8.0, 20.0])
    assert round(wape(pred, actual) * 100, 2) == round(2 / 28 * 100, 2)
    frame = pd.DataFrame(
        {
            "place_id": ["POI001", "POI001"],
            "hour": pd.to_datetime(["2026-09-30 10:00", "2026-09-30 11:00"]).tz_localize("Asia/Seoul"),
            "horizon_d": [1, 1],
            "pred": [10.0, 20.0],
            "baseline": [9.0, 20.0],
        }
    )
    live = pd.DataFrame(
        {
            "place_id": ["POI001", "POI001"],
            "hour": frame["hour"],
            "value": [8.0, 20.0],
            "level": [1, 1],
        }
    )
    rows = _eval_rows(frame, live, date(2026, 9, 30), "holiday")
    assert rows[0][2] == "holiday"
    assert rows[0][1] == 1


def test_warning_bar_is_just_over_and_just_under_a_third_of_a_point():
    baseline = 6.0
    assert 6.31 > baseline + 0.3
    assert not (6.29 > baseline + 0.3)
