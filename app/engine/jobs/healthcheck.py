"""healthcheck: prove the wiring. Calls the Seoul citydata API and the KASI holiday API once each and writes a
`job_runs` row with what came back. Status `ok` only when both calls returned 200 and parsed.

The API keys travel only inside URLs. httpx exceptions embed the URL in their message, so every httpx error is
re-raised as `HealthcheckError` carrying the endpoint name and status only (AGENTS.md hard rule 4).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

import httpx

from engine import db, settings
from engine.log import log

JOB = "healthcheck"
NEEDS = ("DATABASE_URL", "SEOUL_API_KEY", "KASI_API_KEY")
SEOUL_URL = "http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/POI001"
KASI_URL = (
    "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
    "?solYear=2026&solMonth=10&_type=json&ServiceKey={key}"
)
TIMEOUT = 20.0


class HealthcheckError(RuntimeError):
    """Raised with an endpoint name and status; never with a URL or key."""


def _get(client: httpx.Client, endpoint: str, url: str) -> httpx.Response:
    try:
        return client.get(url, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise HealthcheckError(f"{endpoint}: {type(exc).__name__}") from None


def check(client: httpx.Client, env: Mapping[str, str], detail: dict[str, Any]) -> dict[str, Any]:
    """Fill `detail` in place as each call returns, so a failure still records what came back.

    Raises HealthcheckError when either call is not usable.
    """
    r = _get(client, "seoul", SEOUL_URL.format(key=env["SEOUL_API_KEY"]))
    detail["seoul_status"] = r.status_code
    seoul_ok = False
    if r.status_code == 200:
        try:
            seoul_ok = "AREA_NM" in r.json().get("CITYDATA", {})
        except ValueError:
            seoul_ok = False
    detail["seoul_ok"] = seoul_ok

    r = _get(client, "kasi", KASI_URL.format(key=env["KASI_API_KEY"]))
    detail["kasi_status"] = r.status_code
    items: list[dict[str, Any]] = []
    if r.status_code == 200:
        try:
            body = r.json()["response"]["body"]["items"]
            raw = body.get("item", []) if isinstance(body, dict) else []
            items = raw if isinstance(raw, list) else [raw]
        except (ValueError, KeyError, TypeError, AttributeError):
            items = []
    detail["kasi_items"] = len(items)
    detail["kasi_dates"] = [str(i.get("locdate")) for i in items]

    if not (seoul_ok and detail["kasi_status"] == 200 and items):
        raise HealthcheckError(
            f"seoul HTTP {detail['seoul_status']} ok={seoul_ok}; "
            f"kasi HTTP {detail['kasi_status']} items={len(items)}"
        )
    return detail


JobRun = Callable[[str, str], AbstractContextManager[dict[str, Any]]]


def run(
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
    job_run: JobRun | None = None,
) -> int:
    if env is None:
        settings.load_env()
        env = settings.require(NEEDS)
    else:
        env = settings.require(NEEDS, dict(env))
    job_run = job_run or db.job_run
    client = client or httpx.Client()
    log(JOB, "start")
    try:
        with job_run(env["DATABASE_URL"], JOB) as ctx:
            detail = ctx["detail"] = {}
            check(client, env, detail)
    except HealthcheckError as exc:
        log(JOB, "fail", reason=str(exc))
        return 1
    finally:
        client.close()
    log(JOB, "ok", **{k: v for k, v in detail.items() if k != "kasi_dates"})
    return 0
