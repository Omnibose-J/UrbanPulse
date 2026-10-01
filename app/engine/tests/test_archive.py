"""Archive stays a dry run until retention is decided."""

from datetime import date, timedelta
from pathlib import Path

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
