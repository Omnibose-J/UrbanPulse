"""collect against mocked HTTP. No network, no database, no real key."""

import json
from contextlib import contextmanager
from datetime import datetime

import httpx

from engine.jobs import collect
from engine.parsers import KST

SENTINEL = "SEOULKEY-collect-9f3a1c7e"
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
