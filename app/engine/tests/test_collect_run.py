"""collect against mocked HTTP. No network, no database, no real key."""

import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime

import httpx
import pytest

from engine.jobs import collect
from engine.parsers import KST

SENTINEL = "SEOULKEY-collect-9f3a1c7e"


@pytest.fixture(autouse=True)
def _no_stagger(monkeypatch):
    """The opening stagger is a production pacing; tests that do not measure it run without it."""
    monkeypatch.setattr(collect, "STAGGER_S", 0.0)
ENV = {"DATABASE_URL": "postgresql://example", "SEOUL_API_KEY": SENTINEL}


def _places() -> list[dict[str, str]]:
    rows = []
    for number in range(1, 122):
        serve = "off" if number > 111 else "preparing"
        rows.append({"id": f"POI{number:03d}", "serve_state": serve})
    return rows


def _ok_body(code: str) -> dict:
    return {
        "CITYDATA": {
            "AREA_CD": code,
            "LIVE_PPLTN_STTS": [
                {
                    "PPLTN_TIME": "2026-10-01 09:00",
                    "AREA_PPLTN_MIN": "10",
                    "AREA_PPLTN_MAX": "20",
                    "AREA_CONGEST_LVL": "여유",
                    "MALE_PPLTN_RATE": "40.0",
                    "PPLTN_RATE_0": "5.0",
                    "FCST_PPLTN": [
                        {
                            "FCST_TIME": "2026-10-01 10:00",
                            "FCST_PPLTN_MIN": "11",
                            "FCST_PPLTN_MAX": "21",
                            "FCST_CONGEST_LVL": "보통",
                        }
                    ],
                }
            ],
        }
    }


class _Runs:
    def __init__(self):
        self.rows: list[dict] = []

    @contextmanager
    def job_run(self, database_url, job):
        ctx: dict = {"detail": None, "status": "ok"}
        row = {"job": job, "status": "running", "detail": None}
        self.rows.append(row)
        try:
            yield ctx
            row["status"] = ctx.get("status") or "ok"
            row["detail"] = ctx["detail"]
        except Exception as exc:
            row["status"] = "fail"
            row["detail"] = {**(ctx["detail"] or {}), "error": f"{type(exc).__name__}: {exc}"}
            raise


def _client(fail_through: int) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.rstrip("/").split("/")[-1]
        number = int(code.removeprefix("POI"))
        if number <= fail_through:
            return httpx.Response(500, text="unavailable")
        return httpx.Response(200, json=_ok_body(code))

    return httpx.Client(transport=httpx.MockTransport(handler))


def _run(tmp_path, fail_through: int):
    runs = _Runs()
    code = collect.run(
        env=ENV,
        client=_client(fail_through),
        places=_places(),
        raw_dir=tmp_path,
        ledger=runs.job_run,
        store=lambda live, commerce, forecasts: None,
        now=datetime(2026, 10, 1, 9, 20, 30, tzinfo=KST),
    )
    return code, runs.rows[-1], list(tmp_path.rglob("*.json.gz"))


def test_twenty_five_failures_exit_1(tmp_path, capsys):
    code, row, files = _run(tmp_path, 25)
    assert code == 1
    assert row["status"] == "fail"
    assert row["detail"]["failed"] == 25
    assert row["detail"]["called"] == 121
    names = {path.name for path in files}
    assert names == {f"POI{number:03d}.json.gz" for number in range(26, 122)}
    captured = capsys.readouterr()
    blob = captured.out + captured.err + json.dumps(row)
    assert SENTINEL not in blob


def test_five_failures_warn_and_exit_0(tmp_path, capsys):
    code, row, files = _run(tmp_path, 5)
    assert code == 0
    assert row["status"] == "warn"
    assert row["detail"]["failed"] == 5
    assert len(files) == 116
    failed = {f"POI{number:03d}.json.gz" for number in range(1, 6)}
    assert failed.isdisjoint({path.name for path in files})
    captured = capsys.readouterr()
    blob = captured.out + captured.err + json.dumps(row)
    assert SENTINEL not in blob


@pytest.mark.parametrize(
    ("found", "status"),
    [({}, "ok"), ({"window cell that is not rated 1": 2}, "warn")],
)
def test_a_station_without_a_code_still_ends_ok(tmp_path, monkeypatch, found, status):
    """Places without a code pass the code check; a sweep finding turns the run into a warning."""
    monkeypatch.setattr(collect, "load_place_codes", lambda path=None: ["POI001", "POI002", "POI003"])

    def places(_url: str):
        rows = [
            {"id": f"POI{number:03d}", "serve_state": "on", "poi_code": f"POI{number:03d}"}
            for number in range(1, 4)
        ]
        rows.append({"id": "STN001", "serve_state": "experimental", "poi_code": None})
        return rows

    monkeypatch.setattr(collect, "_load_places", places)

    class _Conn:
        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    @contextmanager
    def connected(_url: str):
        yield _Conn()

    monkeypatch.setattr(collect, "_connect", connected)
    import engine.jobs.forecast as forecast
    import engine.jobs.integrity as integrity

    # The database is a stand-in here, so the three functions that read and write it are too.
    monkeypatch.setattr(forecast, "apply_overlay", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(forecast, "refresh_recommendations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integrity, "sweep", lambda *_args, **_kwargs: dict(found))
    runs = _Runs()
    code = collect.run(
        env=ENV,
        client=_client(0),
        raw_dir=tmp_path,
        ledger=runs.job_run,
        store=lambda live, commerce, forecasts: None,
        now=datetime(2026, 10, 1, 9, 20, tzinfo=KST),
    )
    assert code == 0
    assert runs.rows[-1]["status"] == status
    assert "only_in_db" not in runs.rows[-1]["detail"]
    assert runs.rows[-1]["detail"].get("integrity", {}) == found


def test_database_down_writes_raw_and_exits_1(tmp_path, monkeypatch, capsys):
    import psycopg

    monkeypatch.setattr(collect, "load_place_codes", lambda path=None: ["POI001", "POI002", "POI003"])

    def down(database_url: str):
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(collect, "_connect", down)
    code = collect.run(
        env=ENV,
        client=_client(0),
        raw_dir=tmp_path,
        now=datetime(2026, 10, 1, 9, 20, tzinfo=KST),
    )
    assert code == 1
    assert len(list(tmp_path.rglob("*.json.gz"))) == 3
    assert "database unavailable" in capsys.readouterr().out


def _run_places(tmp_path, places, client, **kwargs):
    runs = _Runs()
    code = collect.run(
        env=ENV,
        client=client,
        places=places,
        raw_dir=kwargs.pop("raw_dir", tmp_path),
        ledger=runs.job_run,
        store=lambda live, commerce, forecasts: None,
        now=datetime(2026, 10, 1, 9, 20, tzinfo=KST),
        **kwargs,
    )
    return code, runs.rows[-1]


def test_every_non_off_place_with_no_data_fails(tmp_path):
    from engine.seoul_api import TIMEOUT

    assert TIMEOUT.connect == 5.0
    assert TIMEOUT.read == 20.0

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"CITYDATA": {"AREA_CD": "POI001"}})

    places = [{"id": f"POI{number:03d}", "serve_state": "on"} for number in range(1, 22)]
    code, row = _run_places(tmp_path, places, httpx.Client(transport=httpx.MockTransport(handler)))
    assert code == 1
    assert row["status"] == "fail"
    assert row["detail"]["no_data"] == 21
    assert row["detail"]["ok"] == 0


def test_a_hanging_place_ends_within_the_deadline(tmp_path):
    release = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        release.wait(5)
        code = request.url.path.rstrip("/").split("/")[-1]
        return httpx.Response(200, json=_ok_body(code))

    places = [{"id": "POI001", "serve_state": "on"}]
    started = time.monotonic()
    try:
        code, row = _run_places(
            tmp_path,
            places,
            httpx.Client(transport=httpx.MockTransport(handler)),
            deadline_s=0.4,
        )
    finally:
        release.set()
    assert time.monotonic() - started < 2
    assert row["detail"]["failed_places"] == {"POI001": "deadline"}
    assert code == 0
    assert row["status"] == "warn"


def test_a_raw_write_error_fails_that_place_only(tmp_path, monkeypatch):
    real = collect.raw_store.write

    def write(run_ts, place_code, body, raw_dir, client=None):
        if place_code == "POI002":
            raise OSError("disk full")
        return real(run_ts, place_code, body, raw_dir, client)

    monkeypatch.setattr(collect.raw_store, "write", write)
    places = [{"id": f"POI{number:03d}", "serve_state": "on"} for number in range(1, 4)]
    code, row = _run_places(tmp_path, places, _client(0))
    assert code == 0
    assert row["status"] == "warn"
    assert row["detail"]["failed_places"] == {"POI002": "raw write"}
    assert {path.name for path in tmp_path.rglob("*.json.gz")} == {"POI001.json.gz", "POI003.json.gz"}


def test_one_storage_client_per_run(tmp_path, monkeypatch):
    created: list[object] = []

    def fake_client(client=None):
        if client is not None:
            return client
        created.append(object())
        return created[-1]

    seen: list[object] = []

    def fake_write(run_ts, place_code, body, raw_dir, client=None):
        seen.append(client)
        return "stored"

    monkeypatch.setattr("engine.raw_gcs.storage_client", fake_client)
    monkeypatch.setattr(collect.raw_store, "write", fake_write)
    places = [{"id": f"POI{number:03d}", "serve_state": "on"} for number in range(1, 4)]
    code, row = _run_places(tmp_path, places, _client(0), raw_dir="gs://bucket/raw")
    assert code == 0
    assert row["status"] == "ok"
    assert len(created) == 1
    assert seen == [created[0], created[0], created[0]]


def test_places_lost_to_connection_timeouts_get_one_later_pass(tmp_path, monkeypatch):
    """The opening burst loses POI001-POI005 to ConnectTimeout on every quick attempt; the later pass
    gets them."""
    monkeypatch.setattr(collect, "SECOND_PASS_PAUSE_S", 0.0)
    monkeypatch.setattr("engine.seoul_api.BACKOFF_S", (0.0, 0.0, 0.0))
    first_pass = {"open": True}
    calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.rstrip("/").split("/")[-1]
        calls[code] = calls.get(code, 0) + 1
        if int(code.removeprefix("POI")) <= 5 and first_pass["open"]:
            if calls[code] == 3:
                # The third quick attempt of the last burst place closes the burst window.
                if all(calls.get(f"POI{n:03d}", 0) >= 3 for n in range(1, 6)):
                    first_pass["open"] = False
            raise httpx.ConnectTimeout("burst", request=request)
        return httpx.Response(200, json=_ok_body(code))

    runs = _Runs()
    code = collect.run(
        env=ENV,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        places=_places(),
        raw_dir=tmp_path,
        ledger=runs.job_run,
        store=lambda live, commerce, forecasts: None,
        now=datetime(2026, 10, 1, 9, 20, 30, tzinfo=KST),
    )
    row = runs.rows[-1]
    assert code == 0
    assert row["status"] == "ok"
    assert row["detail"]["failed"] == 0
    assert row["detail"]["second_pass"] == {"tried": 5, "recovered": 5}
    assert len(list(tmp_path.rglob("*.json.gz"))) == 121


def test_an_http_error_is_not_retried_in_a_later_pass(tmp_path):
    code, row, files = _run(tmp_path, 5)
    assert row["detail"]["second_pass"] == {"tried": 0, "recovered": 0}
    assert row["detail"]["failed"] == 5


def test_the_opening_burst_is_spread_out(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "STAGGER_S", 0.05)
    first_seen: dict[str, float] = {}
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        code = request.url.path.rstrip("/").split("/")[-1]
        with lock:
            first_seen.setdefault(code, time.monotonic())
        return httpx.Response(200, json=_ok_body(code))

    runs = _Runs()
    collect.run(
        env=ENV,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        places=_places(),
        raw_dir=tmp_path,
        ledger=runs.job_run,
        store=lambda live, commerce, forecasts: None,
        now=datetime(2026, 10, 1, 9, 20, 30, tzinfo=KST),
    )
    opening = sorted(first_seen[f"POI{n:03d}"] for n in range(1, collect.WORKERS + 1))
    # Ten opening requests at 0.05 s steps span at least 0.45 s (all at once would span a few milliseconds).
    assert opening[-1] - opening[0] >= 0.4
    assert runs.rows[-1]["status"] == "ok"
