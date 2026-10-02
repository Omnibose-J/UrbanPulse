"""A failed job records fail and keeps the caller's writes off the visible tables."""

import psycopg
import pytest

from engine import db
from engine.tests.tempdb import schema


def test_a_sql_error_leaves_one_fail_row_and_no_place():
    with schema() as dsn:
        with pytest.raises(psycopg.Error):
            with db.ledger(dsn, "demo") as (held, _ctx):
                held.execute(
                    "insert into places (id, tier, name, serve_state) values ('POI001', 'A1', 'One', 'on')"
                )
                held.execute("select * from missing_table")
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            status = conn.execute("select status from job_runs").fetchall()
            places = conn.execute("select count(*) from places").fetchone()[0]
    assert status == [("fail",)]
    assert places == 0


def test_system_exit_leaves_one_fail_row_and_no_place():
    with schema() as dsn:
        with pytest.raises(SystemExit):
            with db.ledger(dsn, "demo") as (held, _ctx):
                held.execute(
                    "insert into places (id, tier, name, serve_state) values ('POI001', 'A1', 'One', 'on')"
                )
                raise SystemExit(1)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            status = conn.execute("select status from job_runs").fetchall()
            places = conn.execute("select count(*) from places").fetchone()[0]
    assert status == [("fail",)]
    assert places == 0
