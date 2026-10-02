"""Which rows are logged. That a second run adds nothing is run for real in test_forecast_run."""

from datetime import date, timedelta

from engine.reco import log_candidates


def test_log_candidates_are_only_the_on_rows_three_days_ahead():
    issued = date(2026, 10, 1)
    rows = [
        {"date": issued + timedelta(days=3), "state": "on"},
        {"date": issued + timedelta(days=3), "state": "off"},
        {"date": issued + timedelta(days=2), "state": "reference"},
        {"date": issued + timedelta(days=3), "state": "reference"},
    ]
    picked = log_candidates(rows, issued)
    assert [row["state"] for row in picked] == ["on", "reference"]
    assert all((row["date"] - issued).days == 3 for row in picked)
