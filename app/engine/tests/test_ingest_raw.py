"""`ingest_raw` run for real: a day's raw folder into a private schema, twice, with one unreadable file."""

import gzip
import json
from pathlib import Path

import psycopg

from engine.jobs import ingest_raw
from engine.tests.tempdb import schema


def _write(folder: Path, place: str, pop: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = {
        "CITYDATA": {
            "LIVE_PPLTN_STTS": [
                {
                    "PPLTN_TIME": "2026-10-01 09:00",
                    "AREA_PPLTN_MIN": str(pop),
                    "AREA_PPLTN_MAX": str(pop + 5),
                    "AREA_CONGEST_LVL": "여유",
                }
            ]
        }
    }
    (folder / f"{place}.json.gz").write_bytes(gzip.compress(json.dumps(body).encode("utf-8")))


def _done_line(text: str) -> dict:
    lines = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    return next(line for line in lines if line.get("event") == "done")


def test_a_day_is_stored_once_and_a_bad_file_does_not_block_it(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    morning = raw / "2026" / "10" / "01" / "0900"
    _write(morning, "POI001", 10)
    _write(morning, "POI002", 20)
    whole = gzip.compress(json.dumps({"CITYDATA": {}}).encode("utf-8"))
    (morning / "POI003.json.gz").write_bytes(whole[: len(whole) // 2])  # a write that was cut short
    _write(raw / "2026" / "10" / "02" / "0900", "POI001", 999)  # another day: must not be read

    with schema() as dsn:
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        monkeypatch.setenv("RAW_DIR", str(raw))

        assert ingest_raw.run("2026-10-01") == 0
        first = _done_line(capsys.readouterr().out)
        assert first["affected"] == 2
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            stored = conn.execute(
                "select place_id, pop_min, pop_max, level from live_obs order by 1"
            ).fetchall()
            status, detail = conn.execute(
                "select status, detail from job_runs where job = 'ingest_raw' order by id desc limit 1"
            ).fetchone()
        assert stored == [("POI001", 10, 15, 0), ("POI002", 20, 25, 0)]
        assert status == "warn"
        assert (detail["folders"], detail["files"], detail["live"]) == (1, 3, 2)
        assert [item["file"] for item in detail["failed"]] == ["POI003"]

        assert ingest_raw.run("2026-10-01") == 0
        second = _done_line(capsys.readouterr().out)
        assert second["affected"] == 0
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            assert conn.execute("select count(*) from live_obs").fetchone()[0] == 2


def test_a_day_with_no_folder_exits_1_and_writes_nothing(tmp_path, monkeypatch):
    with schema() as dsn:
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
        assert ingest_raw.run("2026-10-01") == 1
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            assert conn.execute("select count(*) from job_runs").fetchone()[0] == 0
