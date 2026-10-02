"""A place that turns off loses the forecast rows the full run no longer builds."""

from datetime import datetime

import psycopg

from engine.jobs import forecast
from engine.parsers import KST
from engine.tests.tempdb import schema


def test_a_place_switched_off_has_no_rows_after_the_run(monkeypatch):
    with schema() as dsn:
        issued = datetime(2026, 10, 1, 9, 0, tzinfo=KST)
        target = datetime(2026, 10, 3, 12, 0, tzinfo=KST)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into places (id, tier, name, serve_state) values ('POI001', 'A1', 'One', 'on')"
            )
            conn.execute(
                "insert into places (id, tier, name, serve_state) values ('POI002', 'A2', 'Two', 'preparing')"
            )
            conn.execute(
                """
                insert into live_obs (place_id, ts, pop_min, pop_max, level)
                values ('POI002', %s, 10, 20, 1)
                """,
                (datetime(2026, 10, 2, 9, 0, tzinfo=KST),),
            )
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
                  place_id, date, tolerance, purpose, state, off_reason, generated_at
                )
                values ('POI001', '2026-10-03', 'calm', 'sight', 'off', 'preparing', %s)
                """,
                (issued,),
            )
            conn.commit()
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        forecast.run()
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            hours = conn.execute(
                "select count(*) from forecast_hourly where place_id = 'POI001'"
            ).fetchone()[0]
            recommendations = conn.execute(
                "select count(*) from recommendations where place_id = 'POI001'"
            ).fetchone()[0]
            state = conn.execute("select serve_state from places where id = 'POI001'").fetchone()[0]
            kept = conn.execute(
                "select count(*) from forecast_hourly where place_id = 'POI002'"
            ).fetchone()[0]
    assert state == "off"
    assert hours == 0
    assert recommendations == 0
    assert kept > 0
