"""Collect one Seoul citydata snapshot for every place. `python -m engine collect`.

Raw bodies are written before parsing and are never rewritten. More than 20 failures among places
whose serve_state is not off ends the run as fail. Overwriting today's forecast_hourly from the
12-hour forecast waits for M2, when those rows have level thresholds.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from psycopg.types.json import Jsonb

from engine import db, raw_store, settings
from engine.log import log
from engine.parsers import KST, CitySnapshot, parse_citydata
from engine.seoul_api import SeoulError, fetch

JOB = "collect"
NEEDS = ("DATABASE_URL", "SEOUL_API_KEY")
WORKERS = 10
FAIL_AFTER = 20

_LIVE_UPSERT = """
insert into live_obs (place_id, ts, pop_min, pop_max, level, age_rates, male_rate)
values (%(place_id)s, %(ts)s, %(pop_min)s, %(pop_max)s, %(level)s, %(age_rates)s, %(male_rate)s)
on conflict (place_id, ts) do update set
  pop_min = excluded.pop_min,
  pop_max = excluded.pop_max,
  level = excluded.level,
  age_rates = excluded.age_rates,
  male_rate = excluded.male_rate
"""

_COMMERCE_UPSERT = """
insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts)
values (%(place_id)s, %(ts)s, %(level)s, %(pay_cnt)s, %(cat_counts)s)
on conflict (place_id, ts) do update set
  level = excluded.level,
  pay_cnt = excluded.pay_cnt,
  cat_counts = excluded.cat_counts
"""

_FCST_UPSERT = """
insert into city_fcst (place_id, target_ts, issued_ts, pop_min, pop_max, level)
values (%(place_id)s, %(target_ts)s, %(issued_ts)s, %(pop_min)s, %(pop_max)s, %(level)s)
on conflict (place_id, target_ts) do update set
  issued_ts = excluded.issued_ts,
  pop_min = excluded.pop_min,
  pop_max = excluded.pop_max,
  level = excluded.level
where city_fcst.issued_ts <= excluded.issued_ts
"""

Ledger = Callable[[str, str], AbstractContextManager[dict[str, Any]]]
Store = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]


@contextmanager
def _ledger(database_url: str, job: str) -> Iterator[dict[str, Any]]:
    """job_runs row whose status comes from ctx['status'] (ok, warn, or fail)."""
    conn = db.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            cur.execute("insert into job_runs (job, status) values (%s, 'running') returning id", (job,))
            row = cur.fetchone()
            assert row is not None
            run_id = row[0]
        conn.commit()
        ctx: dict[str, Any] = {"detail": None, "status": "ok"}
        try:
            yield ctx
            status = ctx.get("status") or "ok"
            detail = ctx["detail"]
        except Exception as exc:
            status = "fail"
            detail = dict(ctx["detail"] or {})
            detail["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    "update job_runs set finished_at = now(), status = %s, detail = %s where id = %s",
                    (status, Jsonb(detail) if detail is not None else None, run_id),
                )
            conn.commit()
    finally:
        conn.close()


def _raw_dir(env: Mapping[str, str], raw_dir: Path | None) -> Path:
    if raw_dir is not None:
        return raw_dir
    configured = env.get("RAW_DIR") or os.environ.get("RAW_DIR") or "data/raw"
    path = Path(configured)
    if not path.is_absolute():
        path = settings.REPO_ROOT / path
    return path


def _relative(path: Path) -> str:
    try:
        return path.relative_to(settings.REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_places(database_url: str) -> list[dict[str, str]]:
    with db.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select id, serve_state from places order by id")
            return [{"id": row[0], "serve_state": row[1]} for row in cur.fetchall()]


def _one(
    place: dict[str, str],
    client: httpx.Client,
    key: str,
    run_ts: datetime,
    raw_dir: Path,
) -> dict[str, Any]:
    place_id = place["id"]
    try:
        body = fetch(place_id, client, key)
    except SeoulError as exc:
        return {"id": place_id, "serve_state": place["serve_state"], "outcome": "failed", "error": str(exc)}
    raw_store.write(run_ts, place_id, body, raw_dir)
    try:
        snapshot = parse_citydata(place_id, body)
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "id": place_id,
            "serve_state": place["serve_state"],
            "outcome": "failed",
            "error": f"{place_id}: {exc}",
        }
    if snapshot.live is None:
        return {"id": place_id, "serve_state": place["serve_state"], "outcome": "no_data"}
    return {
        "id": place_id,
        "serve_state": place["serve_state"],
        "outcome": "ok",
        "snapshot": snapshot,
    }


def _json_ready(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    out = dict(row)
    for field in fields:
        if out.get(field) is not None:
            out[field] = Jsonb(out[field])
    return out


def _store(
    database_url: str,
    live: list[dict[str, Any]],
    commerce: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
) -> None:
    live_rows = [_json_ready(row, ("age_rates",)) for row in live]
    commerce_rows = [_json_ready(row, ("cat_counts",)) for row in commerce]
    with db.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            if live_rows:
                cur.executemany(_LIVE_UPSERT, live_rows)
            if commerce_rows:
                cur.executemany(_COMMERCE_UPSERT, commerce_rows)
            if forecasts:
                cur.executemany(_FCST_UPSERT, forecasts)
        conn.commit()


def _status(results: list[dict[str, Any]]) -> str:
    non_off_failed = sum(
        1 for row in results if row["outcome"] == "failed" and row["serve_state"] != "off"
    )
    if non_off_failed > FAIL_AFTER:
        return "fail"
    if non_off_failed >= 1:
        return "warn"
    return "ok"


def run(
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
    places: list[dict[str, str]] | None = None,
    raw_dir: Path | None = None,
    ledger: Ledger | None = None,
    store: Store | None = None,
    now: datetime | None = None,
) -> int:
    if env is None:
        settings.load_env()
        env = settings.require(NEEDS)
    else:
        env = settings.require(NEEDS, dict(env))
    raw_dir = _raw_dir(env, raw_dir)
    run_ts = (now or datetime.now(KST)).astimezone(KST).replace(second=0, microsecond=0)
    own_client = client is None
    client = client or httpx.Client()
    ledger = ledger or _ledger
    if store is None:
        database_url = env["DATABASE_URL"]

        def store(
            live: list[dict[str, Any]],
            commerce: list[dict[str, Any]],
            forecasts: list[dict[str, Any]],
        ) -> None:
            _store(database_url, live, commerce, forecasts)

    if places is None:
        places = _load_places(env["DATABASE_URL"])
    log(JOB, "start", called=len(places))
    try:
        with ledger(env["DATABASE_URL"], JOB) as ctx:
            from concurrent.futures import ThreadPoolExecutor

            def work(place: dict[str, str]) -> dict[str, Any]:
                return _one(place, client, env["SEOUL_API_KEY"], run_ts, raw_dir)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                results = list(pool.map(work, places))
            live: list[dict[str, Any]] = []
            commerce: list[dict[str, Any]] = []
            forecasts: list[dict[str, Any]] = []
            for result in results:
                if result["outcome"] != "ok":
                    continue
                snapshot: CitySnapshot = result["snapshot"]
                assert snapshot.live is not None
                live.append(snapshot.live)
                if snapshot.commerce is not None:
                    commerce.append(snapshot.commerce)
                forecasts.extend(snapshot.forecasts)
            store(live, commerce, forecasts)
            ok = sum(1 for row in results if row["outcome"] == "ok")
            no_data = sum(1 for row in results if row["outcome"] == "no_data")
            failed = sum(1 for row in results if row["outcome"] == "failed")
            status = _status(results)
            detail = {
                "called": len(places),
                "ok": ok,
                "no_data": no_data,
                "failed": failed,
                "raw_dir": _relative(raw_store.folder_for(run_ts, raw_dir)),
            }
            ctx["detail"] = detail
            ctx["status"] = status
    except SeoulError as exc:
        log(JOB, "fail", reason=str(exc))
        return 1
    finally:
        if own_client:
            client.close()
    log(JOB, status, **detail)
    return 1 if status == "fail" else 0
