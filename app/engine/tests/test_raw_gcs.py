"""Raw snapshots: local folder or a write-once bucket. No network."""

import json
from datetime import datetime

import pytest

from engine import raw_gcs, raw_store
from engine.jobs import ingest_raw
from engine.parsers import KST


class FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store = store
        self.name = name

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        if if_generation_match == 0 and self.name in self._store:
            raise FileExistsError(self.name)
        self._store[self.name] = data

    def download_as_bytes(self):
        return self._store[self.name]


class FakeBucket:
    def __init__(self, store: dict):
        self._store = store

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self._store, name)


class FakeClient:
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(self.store)

    def list_blobs(self, bucket, prefix=None):
        names = sorted(name for name in self.store if prefix is None or name.startswith(prefix))
        return [FakeBlob(self.store, name) for name in names]


def _install(monkeypatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(raw_gcs, "storage_client", lambda given=None: client if given is None else given)
    return client


def test_object_name_layout_and_a_second_write_raises(monkeypatch):
    client = _install(monkeypatch)
    when = datetime(2026, 10, 1, 9, 20, 45, tzinfo=KST)
    raw_store.write(when, "POI001", {"CITYDATA": {"AREA_CD": "POI001"}}, "gs://bucket/raw", client)
    assert list(client.store) == ["raw/2026/10/01/0920/POI001.json.gz"]
    with pytest.raises(FileExistsError):
        raw_store.write(when, "POI001", {"CITYDATA": {}}, "gs://bucket/raw", client)


def test_ingest_raw_reads_what_the_writer_wrote(monkeypatch):
    client = _install(monkeypatch)
    when = datetime(2026, 10, 1, 9, 20, tzinfo=KST)
    body = {
        "CITYDATA": {
            "AREA_CD": "POI001",
            "LIVE_PPLTN_STTS": [
                {
                    "PPLTN_TIME": "2026-10-01 09:00",
                    "AREA_PPLTN_MIN": "1",
                    "AREA_PPLTN_MAX": "2",
                    "AREA_CONGEST_LVL": "여유",
                }
            ],
        }
    }
    raw_store.write(when, "POI001", body, "gs://bucket/raw", client)
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    monkeypatch.setenv("RAW_DIR", "gs://bucket/raw")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    seen = {}

    def remember(_url, live, commerce, forecasts):
        seen["live"] = live
        return 1

    monkeypatch.setattr(ingest_raw, "store_observations", remember)

    from contextlib import contextmanager

    @contextmanager
    def ledger(_url, _job):
        ctx = {"status": "ok", "detail": None}
        yield ctx

    monkeypatch.setattr(ingest_raw, "_ledger", ledger)
    assert ingest_raw.run("2026-10-01") == 0
    assert seen["live"][0]["place_id"] == "POI001"
    assert json.loads(json.dumps(body))["CITYDATA"]["AREA_CD"] == "POI001"


def test_a_truncated_file_warns_and_the_other_file_is_stored(tmp_path, monkeypatch):
    when = datetime(2026, 10, 1, 9, 20, tzinfo=KST)
    body = {
        "CITYDATA": {
            "AREA_CD": "POI001",
            "LIVE_PPLTN_STTS": [
                {
                    "PPLTN_TIME": "2026-10-01 09:00",
                    "AREA_PPLTN_MIN": "1",
                    "AREA_PPLTN_MAX": "2",
                    "AREA_CONGEST_LVL": "여유",
                }
            ],
        }
    }
    raw_store.write(when, "POI001", body, tmp_path)
    bad = tmp_path / "2026" / "10" / "01" / "0920" / "POI002.json.gz"
    bad.write_bytes(b"not-gzip")
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    monkeypatch.setenv("RAW_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    seen = {}

    def remember(_url, live, _commerce, _forecasts):
        seen["ids"] = [row["place_id"] for row in live]
        return 1

    monkeypatch.setattr(ingest_raw, "store_observations", remember)

    from contextlib import contextmanager

    @contextmanager
    def ledger(_url, _job):
        ctx = {"status": "ok", "detail": None}
        yield ctx
        seen["status"] = ctx["status"]
        seen["failed"] = ctx["detail"]["failed"]
        seen["folders"] = ctx["detail"]["folders"]

    monkeypatch.setattr(ingest_raw, "_ledger", ledger)
    assert ingest_raw.run("2026-10-01") == 0
    assert seen["status"] == "warn"
    assert seen["ids"] == ["POI001"]
    assert seen["failed"][0]["file"] == "POI002"
    assert seen["folders"] == 1


def test_an_existing_final_name_is_not_replaced_and_leaves_no_temp(tmp_path):
    when = datetime(2026, 10, 1, 9, 20, tzinfo=KST)
    raw_store.write(when, "POI001", {"CITYDATA": {}}, tmp_path)
    with pytest.raises(OSError):
        raw_store.write(when, "POI001", {"CITYDATA": {"again": True}}, tmp_path)
    assert list((tmp_path / "2026" / "10" / "01" / "0920").glob("*.tmp")) == []


def test_a_local_raw_dir_still_round_trips(tmp_path):
    when = datetime(2026, 10, 1, 9, 20, tzinfo=KST)
    body = {"CITYDATA": {"AREA_CD": "POI009"}}
    raw_store.write(when, "POI009", body, tmp_path)
    with pytest.raises(FileExistsError):
        raw_store.write(when, "POI009", body, tmp_path)
    assert raw_store.read_day(tmp_path, when.date()) == [("POI009", body)]
