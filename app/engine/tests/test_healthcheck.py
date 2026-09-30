"""healthcheck against mocked HTTP and a fake job_run. No network, no database, no real keys."""

import json
from contextlib import contextmanager

import httpx
import pytest

from engine.jobs import healthcheck

SENTINEL_SEOUL = "SEOULKEY-9f3a1c7e"
SENTINEL_KASI = "KASIKEY-4b8d2e60"
ENV = {"DATABASE_URL": "postgresql://x", "SEOUL_API_KEY": SENTINEL_SEOUL, "KASI_API_KEY": SENTINEL_KASI}

SEOUL_OK = {"CITYDATA": {"AREA_NM": "성수카페거리", "LIVE_PPLTN_STTS": []}}
KASI_3 = {
    "response": {
        "body": {
            "items": {
                "item": [
                    {"locdate": 20261003, "dateName": "개천절"},
                    {"locdate": 20261005, "dateName": "대체공휴일(개천절)"},
                    {"locdate": 20261009, "dateName": "한글날"},
                ]
            }
        }
    }
}


class FakeRuns:
    def __init__(self):
        self.rows = []

    @contextmanager
    def job_run(self, database_url, job):
        ctx = {"detail": None}
        row = {"job": job, "status": "running", "detail": None}
        self.rows.append(row)
        try:
            yield ctx
            row["status"], row["detail"] = "ok", ctx["detail"]
        except Exception as exc:
            row["status"] = "fail"
            row["detail"] = {**(ctx["detail"] or {}), "error": f"{type(exc).__name__}: {exc}"}
            raise


def client_with(seoul, kasi):
    def handler(request: httpx.Request) -> httpx.Response:
        if "openapi.seoul.go.kr" in request.url.host:
            return seoul(request)
        return kasi(request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_both_ok_writes_ok_row_with_counts(capsys):
    runs = FakeRuns()
    client = client_with(
        lambda r: httpx.Response(200, json=SEOUL_OK), lambda r: httpx.Response(200, json=KASI_3)
    )
    code = healthcheck.run(env=ENV, client=client, job_run=runs.job_run)
    assert code == 0
    row = runs.rows[-1]
    assert row["status"] == "ok"
    assert row["detail"]["seoul_ok"] is True
    assert row["detail"]["kasi_items"] == 3
    assert row["detail"]["kasi_dates"] == ["20261003", "20261005", "20261009"]
    out = capsys.readouterr().out
    events = [json.loads(line)["event"] for line in out.strip().splitlines()]
    assert events == ["start", "ok"]


def test_seoul_500_fails_and_never_leaks_the_key(capsys):
    runs = FakeRuns()
    client = client_with(
        lambda r: httpx.Response(500, text="boom"), lambda r: httpx.Response(200, json=KASI_3)
    )
    code = healthcheck.run(env=ENV, client=client, job_run=runs.job_run)
    assert code == 1
    row = runs.rows[-1]
    assert row["status"] == "fail"
    assert row["detail"]["seoul_status"] == 500
    captured = capsys.readouterr()
    everything = captured.out + captured.err + json.dumps(row)
    assert SENTINEL_SEOUL not in everything
    assert SENTINEL_KASI not in everything
    assert "openapi.seoul.go.kr" not in captured.out + captured.err


def test_connection_error_is_reported_without_url_or_key():
    runs = FakeRuns()

    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    client = client_with(boom, lambda r: httpx.Response(200, json=KASI_3))
    code = healthcheck.run(env=ENV, client=client, job_run=runs.job_run)
    assert code == 1
    err = runs.rows[-1]["detail"]["error"]
    assert "ConnectError" in err
    assert SENTINEL_SEOUL not in err and "http" not in err


def test_missing_env_exits_1(monkeypatch):
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    with pytest.raises(SystemExit) as e:
        healthcheck.run(env={"DATABASE_URL": "postgresql://x"})
    assert e.value.code == 1
