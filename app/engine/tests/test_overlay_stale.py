"""Stale follows the newest observation, in both directions."""

from datetime import datetime, timedelta

import psycopg

from engine.jobs.forecast import apply_overlay
from engine.parsers import KST
from engine.tests.tempdb import schema


def _place(conn, place_id: str, observed: datetime, stale: bool, now: datetime) -> None:
    conn.execute(
        "insert into places (id, tier, name, serve_state) values (%s, 'A2', %s, 'on')",
        (place_id, place_id),
    )
    conn.execute(
        """
        insert into live_obs (place_id, ts, pop_min, pop_max, level)
        values (%s, %s, 10, 20, 1)
        """,
        (place_id, observed),
    )
    target = datetime(2026, 10, 3, 12, tzinfo=KST)
    conn.execute(
        """
        insert into forecast_hourly (place_id, target_ts, issued_ts, source, level, ready, stale)
        values (%s, %s, %s, 'profile', 1, true, %s)
        """,
        (place_id, target, now, stale),
    )


def test_stale_follows_the_newest_observation_both_ways():
    now = datetime(2026, 10, 2, 15, 0, tzinfo=KST)
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            _place(conn, "OLD", now - timedelta(minutes=120), False, now)
            _place(conn, "FRESH", now - timedelta(minutes=10), True, now)
            conn.commit()
            apply_overlay(conn, now)
            conn.commit()
            rows = dict(conn.execute("select place_id, stale from forecast_hourly").fetchall())
    assert rows["OLD"] is True
    assert rows["FRESH"] is False
