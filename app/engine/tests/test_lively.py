"""Activity profile from a 10-day hand-built commerce table."""

from datetime import date, datetime, timedelta

import pandas as pd

from engine.lively import hourly_commerce, profile_rows
from engine.parsers import KST


def test_zero_p90_makes_that_purpose_null():
    start = datetime(2026, 8, 1, 10, tzinfo=KST)
    rows = []
    for offset in range(10):
        # Saturdays-only would be thin; use a run of dates the calendar calls weekend/holiday.
        stamp = start + timedelta(days=offset)
        rows.append({"place_id": "POI001", "ts": stamp, "pay_cnt": 0, "food": 10, "shop": 5})
    hourly = hourly_commerce(pd.DataFrame(rows))
    # Force every day to be a weekend so p90 of pay_cnt is 0 and the day type is not thin.
    kinds = {}
    profiles = profile_rows(hourly, kinds, date(2026, 8, 20))
    weekend = [row for row in profiles if row["day_type"] == "weekend" and row["hour"] == 10]
    assert weekend
    assert weekend[0]["a_all"] is None
    assert weekend[0]["a_food"] is not None
