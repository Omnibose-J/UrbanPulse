"""The integrity sweep finds what it is meant to find, and nothing on consistent rows."""

from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from engine.jobs import integrity
from engine.parsers import KST
from engine.tests.tempdb import schema


def cells(window_hour: int | None, bad: dict | None = None) -> list[dict]:
    out = []
    for hour in range(9, 24):
        cell = {
            "h": hour,
            "rating": 1,
            "in_window": hour == window_hour,
            "reason": "fit",
            "crowd": 1,
            "act": "lively",
        }
        if bad and hour == bad["h"]:
            cell.update(bad)
        out.append(cell)
    return out


def insert_row(conn, place: str, day, hours, windows, state="on", alt_dates=None, generated=None) -> None:
    conn.execute(
        """
        insert into recommendations (
          place_id, date, tolerance, purpose, state, off_reason, windows, no_window,
          hours, strip_mode, alt_dates, alt_places, generated_at)
        values (%s, %s, 'moderate', 'sight', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            place,
            day,
            state,
            "failed" if state == "off" else None,
            None if state == "off" else Jsonb(windows),
            None if state == "off" else not windows,
            None if state == "off" else Jsonb(hours),
            None if state == "off" else "windows_only",
            None if state == "off" else Jsonb(alt_dates or []),
            None if state == "off" else Jsonb([]),
            generated or datetime.now(KST).replace(hour=0, minute=1),
        ),
    )


def test_consistent_rows_raise_nothing_and_each_fault_is_named():
    today = datetime.now(KST).date()
    tomorrow = today + timedelta(days=1)
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute(
            "insert into places (id, tier, name, foreign_heavy, serve_state) values "
            "('GOOD', 'A1', 'Good', false, 'on'), ('PARK', 'A2', 'Park', false, 'on')"
        )
        insert_row(conn, "GOOD", tomorrow, cells(13), [{"hours": [13], "score": 0.8}])
        conn.commit()
        assert integrity.sweep(conn) == {}

        # 1. a window cell rated 0, which also makes rating and reason disagree
        insert_row(conn, "BAD1", tomorrow, cells(13, {"h": 13, "rating": 0}), [{"hours": [13], "score": 0.8}])
        # 2. the windows list names an hour the cells do not mark
        insert_row(conn, "BAD2", tomorrow, cells(13), [{"hours": [14], "score": 0.8}])
        # 3. an A2 place whose cells carry activity text
        insert_row(conn, "PARK", tomorrow, cells(13), [{"hours": [13], "score": 0.8}])
        # 4. an alternative date that turns out to have no window, and one in the past
        insert_row(conn, "BAD4", today + timedelta(days=2), cells(None), [])
        insert_row(
            conn,
            "BAD4",
            tomorrow,
            cells(None),
            [],
            alt_dates=[
                {"date": (today + timedelta(days=2)).isoformat(), "hours": [13], "score": 1},
                {"date": (today - timedelta(days=1)).isoformat(), "hours": [13], "score": 1},
            ],
        )
        # 5. a cell whose crowd is not the forecast level of that hour
        insert_row(conn, "BAD5", tomorrow, cells(13), [{"hours": [13], "score": 0.8}])
        stamp = datetime.combine(tomorrow, datetime.min.time()).replace(tzinfo=KST) + timedelta(hours=13)
        conn.execute(
            "insert into forecast_hourly (place_id, target_ts, issued_ts, source, pop, level, ready) "
            "values ('BAD5', %s, now(), 'model', 500, 3, true)",
            (stamp,),
        )
        # 6. a window of today that starts before the hour its row was built
        built = datetime.now(KST).replace(hour=20, minute=5)
        insert_row(conn, "BAD6", today, cells(10), [{"hours": [10], "score": 0.8}], generated=built)
        # 7. a job that never finished
        conn.execute(
            "insert into job_runs (job, status, started_at) "
            "values ('collect', 'running', now() - interval '3 hours')"
        )
        conn.commit()

        found = integrity.sweep(conn)
        assert found == {
            "window cell that is not rated 1": 1,
            "rating and reason disagree": 1,
            "window hours differ from the in_window cells": 1,
            "activity text on a place that has none": 15,
            "alternative date that is off or has no window": 1,
            "alternative date in the past": 1,
            "cell crowd differs from the forecast level of that hour": 1,
            "window of today starting before the hour it was built": 1,
            "job stuck in running for over two hours": 1,
        }


def test_the_full_set_also_checks_row_counts_and_past_rows():
    today = datetime.now(KST).date()
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute(
            "insert into places (id, tier, name, foreign_heavy, serve_state) "
            "values ('POI001', 'A1', 'One', false, 'on')"
        )
        insert_row(conn, "POI001", today - timedelta(days=1), cells(13), [{"hours": [13], "score": 0.8}])
        conn.commit()
        assert integrity.sweep(conn) == {}
        found = integrity.sweep(conn, full=True)
        assert found == {
            "served A1/A2 place without 8 days of 24 forecast hours": 1,
            "served A1/A2 place without all its recommendation rows": 1,
            "recommendation row for a past date": 1,
        }


def test_the_job_exits_1_and_records_what_it_found(monkeypatch, capsys):
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into level_thresholds (place_id, t1, t2, t3, based_on_days) "
                "values ('POI001', 1, 2, 3, 9)"
            )
            conn.commit()
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        assert integrity.run() == 0
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute("alter table level_thresholds drop constraint if exists level_thresholds_check")
            conn.execute("update level_thresholds set t1 = 5")
            conn.commit()
        assert integrity.run() == 1
        assert "thresholds out of order" in capsys.readouterr().out
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            rows = conn.execute(
                "select status, detail->'found' from job_runs where job = 'integrity' order by id"
            ).fetchall()
        assert rows == [("ok", {}), ("warn", {"thresholds out of order": 1})]


def test_the_hourly_job_also_names_data_that_stopped_arriving():
    """Nothing stored for two hours, no forecast issued today: a paused scheduler fails no run itself."""
    now = datetime.now(KST)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute(
            "insert into places (id, tier, name, foreign_heavy, serve_state) "
            "values ('POI001', 'A1', 'One', false, 'on')"
        )
        conn.execute(
            "insert into live_obs (place_id, ts, pop_min, pop_max, level) values ('POI001', %s, 1, 2, 0)",
            (now - timedelta(hours=3),),
        )
        conn.execute(
            "insert into forecast_hourly (place_id, target_ts, issued_ts, source, level, ready) "
            "values ('POI001', %s, %s, 'profile', 1, true)",
            (midnight + timedelta(hours=13), midnight - timedelta(days=1)),
        )
        conn.commit()
        assert integrity.sweep(conn) == {}
        found = integrity.sweep(conn, fresh=True)
        assert found["no observation stored in the last two hours"] == 1
        late_name = "served A1/A2 place without a forecast issued today (after 07:00)"
        assert found.get(late_name, 0) == (1 if now.hour >= 7 else 0)
        conn.execute(
            "insert into live_obs (place_id, ts, pop_min, pop_max, level) values ('POI001', %s, 1, 2, 0)",
            (now - timedelta(minutes=20),),
        )
        conn.execute("update forecast_hourly set issued_ts = %s", (midnight,))
        conn.commit()
        assert integrity.sweep(conn, fresh=True) == {}
