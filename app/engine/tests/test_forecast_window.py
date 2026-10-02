"""The issued day stays the window even when the clock crosses midnight."""

from datetime import date, datetime

import psycopg
import pytest

from engine import settings
from engine.jobs.forecast import drop_past_forecasts, drop_unprofiled_tier_b, issued_midnight
from engine.parsers import KST


def test_issued_midnight_stays_on_the_issued_day():
    assert issued_midnight(date(2026, 10, 1)) == datetime(2026, 10, 1, 0, 0, tzinfo=KST)


def test_past_cut_keeps_the_issued_day_and_a_place_without_a_profile_is_removed():
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    try:
        conn = psycopg.connect(url, autocommit=False, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.fail("local database not reachable (cd app; supabase start)")
    issued = date(2026, 10, 1)
    bare = "STNTEST"
    kept = "STNKEEP"
    with conn:
        with conn.cursor() as cur:
            for place_id, name in ((bare, "없는역"), (kept, "있는역")):
                cur.execute(
                    """
                    insert into places (id, tier, name, serve_state)
                    values (%s, 'B', %s, 'experimental')
                    """,
                    (place_id, name),
                )
            cur.execute(
                """
                insert into tier_b_profile (place_id, day_type, hour, rel)
                values (%s, 'weekday', 9, 0.5)
                """,
                (kept,),
            )
            hours = (
                (bare, date(2026, 9, 30)),
                (bare, issued),
                (kept, date(2026, 9, 30)),
                (kept, issued),
            )
            for place_id, day in hours:
                stamp = datetime(day.year, day.month, day.day, 10, tzinfo=KST)
                cur.execute(
                    """
                    insert into forecast_hourly (place_id, target_ts, issued_ts, source, level, ready)
                    values (%s, %s, %s, 'profile', 1, true)
                    """,
                    (place_id, stamp, issued_midnight(issued)),
                )
            cur.execute(
                """
                insert into recommendations (place_id, date, tolerance, purpose, state, off_reason)
                values (%s, %s, 'moderate', 'none', 'off', 'preparing')
                """,
                (bare, issued),
            )
        drop_unprofiled_tier_b(conn)
        drop_past_forecasts(conn, issued)
        with conn.cursor() as cur:
            cur.execute("select count(*) from forecast_hourly where place_id = %s", (bare,))
            bare_hours = cur.fetchone()[0]
            cur.execute("select count(*) from recommendations where place_id = %s", (bare,))
            bare_rows = cur.fetchone()[0]
            cur.execute(
                "select (target_ts at time zone 'Asia/Seoul')::date from forecast_hourly where place_id = %s",
                (kept,),
            )
            kept_days = [row[0] for row in cur.fetchall()]
        conn.rollback()
    assert bare_hours == 0
    assert bare_rows == 0
    assert kept_days == [issued]
