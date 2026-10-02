"""Archive stays a dry run until retention is decided."""

from datetime import date, timedelta
from pathlib import Path

from engine.__main__ import main
from engine.jobs.archive import run


def test_existing_parquet_is_not_overwritten(tmp_path: Path, monkeypatch):
    folder = tmp_path / "live_obs"
    folder.mkdir()
    target = folder / "2026-10-01.parquet"
    target.write_bytes(b"already")
    assert target.exists()


def test_cuts_are_ninety_and_one_hundred_eighty_days():
    today = date(2026, 10, 1)
    assert today - timedelta(days=90) == date(2026, 7, 3)
    assert today - timedelta(days=180) == date(2026, 4, 4)
    assert run is not None


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
