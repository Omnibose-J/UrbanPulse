"""A failure before recommendations rolls back the web-visible tables together."""

from datetime import datetime

import psycopg
import pytest

from engine.jobs import forecast
from engine.parsers import KST
from engine.tests.tempdb import schema


def test_failure_before_recommendations_leaves_the_visible_tables_unchanged(monkeypatch):
    with schema() as dsn:
        stamp = datetime(2026, 10, 2, 9, 0, tzinfo=KST)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into places (id, tier, name, serve_state) values ('POI001', 'A1', 'One', 'on')"
            )
            conn.execute(
                "insert into level_thresholds (place_id, t1, t2, t3, based_on_days) "
                "values ('POI001', 1, 2, 3, 4)"
            )
            conn.execute(
                """
                insert into forecast_hourly (place_id, target_ts, issued_ts, source, level, ready)
                values ('POI001', %s, %s, 'profile', 1, true)
                """,
                (stamp, stamp),
            )
            conn.commit()
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)

        def stop(*_args, **_kwargs):
            raise RuntimeError("stop before recommendations")

        monkeypatch.setattr(forecast, "refresh_recommendations", stop)
        with pytest.raises(RuntimeError):
            forecast.run()
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            state = conn.execute("select serve_state from places where id = 'POI001'").fetchone()[0]
            thresholds = conn.execute("select count(*) from level_thresholds").fetchone()[0]
            hours = conn.execute("select count(*) from forecast_hourly").fetchone()[0]
            lively = conn.execute("select count(*) from lively_profile").fetchone()[0]
            norms = conn.execute("select count(*) from lively_norm").fetchone()[0]
            similar = conn.execute("select count(*) from similar_places").fetchone()[0]
            recommendations = conn.execute("select count(*) from recommendations").fetchone()[0]
    assert state == "on"
    assert thresholds == 1
    assert hours == 1
    assert lively == 0
    assert norms == 0
    assert similar == 0
    assert recommendations == 0


def test_a_broken_invariant_after_the_build_fails_the_execution_and_keeps_the_rows(monkeypatch):
    """Spec 4.9: the alert policy watches failed executions only, so the forecast's own sweep must fail it."""
    with schema() as dsn:
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)

        def build(conn, started, today):
            conn.execute(
                "insert into places (id, tier, name, serve_state) values ('POI001', 'A1', 'One', 'on')"
            )
            conn.commit()  # the real build commits the web-visible tables itself
            return {"places": 1}

        monkeypatch.setattr(forecast, "_build", build)
        found = {"thresholds out of order": 1}
        monkeypatch.setattr(forecast.integrity, "sweep", lambda conn, full=False: found)
        assert forecast.run() == 1
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            kept = conn.execute("select count(*) from places").fetchone()[0]
            ledger = conn.execute(
                "select status, detail->'integrity' from job_runs where job = 'forecast'"
            ).fetchone()
    assert kept == 1
    assert ledger == ("warn", {"thresholds out of order": 1})
