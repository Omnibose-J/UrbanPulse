"""Today's refresh rewrites alt dates on the other days of the same place."""

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from engine.jobs.forecast import refresh_recommendations
from engine.parsers import KST
from engine.tests.tempdb import schema


def test_today_refresh_drops_past_hours_from_other_dates():
    with schema() as dsn:
        issued = datetime(2026, 10, 2, 8, 0, tzinfo=KST)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into places (id, tier, name, serve_state) values ('POI001', 'A2', 'One', 'on')"
            )
            for hour in range(9, 24):
                target = datetime(2026, 10, 2, hour, tzinfo=KST)
                conn.execute(
                    """
                    insert into forecast_hourly (place_id, target_ts, issued_ts, source, level, ready)
                    values ('POI001', %s, %s, 'profile', 1, true)
                    """,
                    (target, issued),
                )
            conn.execute(
                """
                insert into recommendations (
                  place_id, date, tolerance, purpose, state, windows, no_window, hours, strip_mode,
                  alt_dates, alt_places
                ) values (
                  'POI001', '2026-10-03', 'moderate', 'none', 'on', %s, false, %s, 'windows_only',
                  %s, '[]'
                )
                """,
                (
                    Jsonb([{"hours": [10, 11], "score": 0.1, "crowd": 1}]),
                    Jsonb([{"h": hour, "rating": 1} for hour in range(9, 24)]),
                    Jsonb([{"date": "2026-10-02", "hours": [9], "score": 0.9}]),
                ),
            )
            conn.commit()
            started = datetime(2026, 10, 2, 15, 0, tzinfo=KST)
            refresh_recommendations(conn, started, started.date(), place_ids=["POI001"], only_today=True)
            conn.commit()
            alt = conn.execute(
                """
                select alt_dates from recommendations
                where place_id = 'POI001' and date = '2026-10-03'
                  and tolerance = 'moderate' and purpose = 'none'
                """
            ).fetchone()[0]
    hours = [hour for item in (alt or []) if item["date"] == "2026-10-02" for hour in item["hours"]]
    assert 9 not in hours
