"""Archive stays a dry run until retention is decided."""

from datetime import datetime, timedelta

import psycopg

from engine.__main__ import main
from engine.parsers import KST
from engine.tests.tempdb import schema


def test_dry_run_counts_the_rows_past_each_cut_and_deletes_none(monkeypatch, capsys):
    today = datetime.now(KST).date()

    def stamp(days_back: int) -> datetime:
        return datetime.combine(today - timedelta(days=days_back), datetime.min.time()).replace(tzinfo=KST)

    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                # live_obs: two rows past the 90-day cut, one exactly on the cut day (kept), one recent
                for days_back in (200, 91, 90, 1):
                    cur.execute(
                        "insert into live_obs (place_id, ts, pop_min, pop_max, level) values "
                        "('POI001', %s, 1, 1, 0)",
                        (stamp(days_back),),
                    )
                cur.execute(
                    "insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts) values "
                    "('POI001', %s, 0, 1, '{}')",
                    (stamp(120),),
                )
                # forecast_log: one row past the 180-day cut, one inside it
                for days_back in (181, 179):
                    cur.execute(
                        "insert into forecast_log (place_id, issued_date, target_ts, horizon_d, "
                        "pred, baseline, model_version) "
                        "values ('POI001', %s, %s, 1, 1, 1, 'v')",
                        (today - timedelta(days=days_back + 1), stamp(days_back)),
                    )
            conn.commit()
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        assert main(["archive", "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "live_obs 2" in out and "commerce_obs 1" in out and "forecast_log 1" in out
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            counts = conn.execute(
                "select (select count(*) from live_obs), (select count(*) from commerce_obs), "
                "(select count(*) from forecast_log)"
            ).fetchone()
            detail = conn.execute("select detail from job_runs where job = 'archive'").fetchone()[0]
        assert counts == (4, 1, 2)
        assert detail == {"dry_run": True, "counts": {"live_obs": 2, "commerce_obs": 1, "forecast_log": 1}}


class _Cursor:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params=None) -> None:
        self.sql.append(sql)

    def fetchone(self):
        return (3,)

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


class _Conn:
    def __init__(self) -> None:
        self.cursor_obj = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_obj

    def commit(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_no_flag_exits_2_without_connecting(monkeypatch, capsys):
    def refuse(_url: str):
        raise AssertionError("archive connected")

    monkeypatch.setattr("engine.jobs.archive.db.connect", refuse)
    code = main(["archive"])
    captured = capsys.readouterr()
    assert code == 2
    assert "deletion is not enabled" in captured.out + captured.err


def test_execute_exits_2_without_deleting(monkeypatch, capsys):
    def refuse(_url: str):
        raise AssertionError("archive connected")

    monkeypatch.setattr("engine.jobs.archive.db.connect", refuse)
    code = main(["archive", "--execute"])
    captured = capsys.readouterr()
    assert code == 2
    assert "retention decision pending" in captured.out + captured.err


def test_dry_run_counts_and_does_not_delete(monkeypatch, capsys):
    conn = _Conn()

    def connect(_url: str):
        return conn

    monkeypatch.setattr("engine.jobs.archive.db.connect", connect)
    code = main(["archive", "--dry-run"])
    captured = capsys.readouterr()
    assert code == 0
    assert "live_obs 3" in captured.out
    assert not any(sql.lower().lstrip().startswith("delete") for sql in conn.cursor_obj.sql)
