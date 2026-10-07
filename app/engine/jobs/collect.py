"""Collect one Seoul citydata snapshot for every place. `python -m engine collect`.

Raw bodies are written before parsing and are never rewritten. More than 20 failures or empty
snapshots among places whose serve_state is not off ends the run as fail. After a successful store,
today's forecast rows are overlaid from live observations and the city forecast.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import yaml
from psycopg.types.json import Jsonb

from engine import db, raw_store, settings
from engine.log import log
from engine.parsers import KST, CitySnapshot, parse_citydata
from engine.seoul_api import SeoulError, fetch

JOB = "collect"
NEEDS = ("DATABASE_URL", "SEOUL_API_KEY")
WORKERS = 10
# Connection-level failures cluster in the opening burst (2026-10-07: 17 of 98 runs lost 1-5 of the
# first places to ConnectTimeout after three quick attempts). Those places get one more pass after a
# pause, three at a time.
# An HTTP error status is the server's answer and is not retried again.
SECOND_PASS_ERRORS = ("ConnectTimeout", "ConnectError", "ReadTimeout", "PoolTimeout", "RemoteProtocolError")
SECOND_PASS_PAUSE_S = 15.0
SECOND_PASS_WORKERS = 3
# The first WORKERS places open their connections STAGGER_S apart instead of all at once: every one of the 64
# connection failures seen on 2026-10-05..07 hit one of the first eleven places.
STAGGER_S = 0.5
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
where live_obs.pop_min is distinct from excluded.pop_min
   or live_obs.pop_max is distinct from excluded.pop_max
   or live_obs.level is distinct from excluded.level
   or live_obs.age_rates is distinct from excluded.age_rates
   or live_obs.male_rate is distinct from excluded.male_rate
"""

_COMMERCE_UPSERT = """
insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts)
values (%(place_id)s, %(ts)s, %(level)s, %(pay_cnt)s, %(cat_counts)s)
on conflict (place_id, ts) do update set
  level = excluded.level,
  pay_cnt = excluded.pay_cnt,
  cat_counts = excluded.cat_counts
where commerce_obs.level is distinct from excluded.level
   or commerce_obs.pay_cnt is distinct from excluded.pay_cnt
   or commerce_obs.cat_counts is distinct from excluded.cat_counts
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
  and (
    city_fcst.issued_ts is distinct from excluded.issued_ts
    or city_fcst.pop_min is distinct from excluded.pop_min
    or city_fcst.pop_max is distinct from excluded.pop_max
    or city_fcst.level is distinct from excluded.level
  )
"""

Ledger = Callable[[str, str], AbstractContextManager[dict[str, Any]]]
Store = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
_CODES = Path(__file__).resolve().parents[1] / "config" / "place_codes.yaml"


def _connect(database_url: str) -> psycopg.Connection:
    return db.connect(database_url)


def load_place_codes(path: Path | None = None) -> list[str]:
    path = path or _CODES
    if not path.exists():
        raise RuntimeError("missing place_codes.yaml; run load_places")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    codes = data.get("codes") if isinstance(data, dict) else None
    if not isinstance(codes, list) or not codes:
        raise RuntimeError("place_codes.yaml has no codes")
    if len(set(codes)) != len(codes):
        raise RuntimeError("place_codes.yaml has duplicate codes")
    return [str(code) for code in codes]


@contextmanager
def _ledger(database_url: str, job: str) -> Iterator[dict[str, Any]]:
    """job_runs row whose status comes from ctx['status'] (ok, warn, or fail)."""
    with db.ledger(database_url, job) as (_conn, ctx):
        try:
            yield ctx
        except psycopg.OperationalError:
            ctx["detail"] = dict(ctx["detail"] or {})
            ctx["detail"]["reason"] = "database unavailable"
            raise


def _raw_dir(env: Mapping[str, str], raw_dir: str | Path | None) -> str | Path:
    if raw_dir is not None:
        return raw_dir
    configured = env.get("RAW_DIR") or os.environ.get("RAW_DIR") or "data/raw"
    if str(configured).startswith("gs://"):
        return str(configured)
    path = Path(configured)
    if not path.is_absolute():
        path = settings.REPO_ROOT / path
    return path


def _relative(path: Path) -> str:
    try:
        return path.relative_to(settings.REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_places(database_url: str) -> list[dict[str, str | None]]:
    with _connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select id, serve_state, poi_code from places order by id")
            return [{"id": row[0], "serve_state": row[1], "poi_code": row[2]} for row in cur.fetchall()]


def _one(
    place: dict[str, str],
    client: httpx.Client,
    key: str,
    run_ts: datetime,
    raw_dir: str | Path,
    storage_client: Any = None,
) -> dict[str, Any]:
    place_id = place["id"]
    try:
        body = fetch(place_id, client, key)
    except SeoulError as exc:
        return {"id": place_id, "serve_state": place["serve_state"], "outcome": "failed", "error": str(exc)}
    try:
        raw_store.write(run_ts, place_id, body, raw_dir, storage_client)
    except Exception:
        return {
            "id": place_id,
            "serve_state": place["serve_state"],
            "outcome": "failed",
            "error": "raw write",
        }
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


def store_observations(
    database_url: str,
    live: list[dict[str, Any]],
    commerce: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
) -> int:
    """Upsert parsed rows. Returns the number of statements that changed a row. Shared with ingest_raw."""
    live_rows = [_json_ready(row, ("age_rates",)) for row in live]
    commerce_rows = [_json_ready(row, ("cat_counts",)) for row in commerce]
    affected = 0
    with _connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            for statement, rows in (
                (_LIVE_UPSERT, live_rows),
                (_COMMERCE_UPSERT, commerce_rows),
                (_FCST_UPSERT, forecasts),
            ):
                if not rows:
                    continue
                cur.executemany(statement, rows)
                if cur.rowcount > 0:
                    affected += cur.rowcount
        conn.commit()
    return affected


def _status(results: list[dict[str, Any]]) -> str:
    bad = sum(
        1
        for row in results
        if row["outcome"] in ("failed", "no_data") and row["serve_state"] != "off"
    )
    if bad > FAIL_AFTER:
        return "fail"
    if bad >= 1:
        return "warn"
    return "ok"


def run(
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
    places: list[dict[str, str]] | None = None,
    raw_dir: str | Path | None = None,
    ledger: Ledger | None = None,
    store: Store | None = None,
    now: datetime | None = None,
    deadline_s: float = 6 * 60,
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
            store_observations(database_url, live, commerce, forecasts)

    from_file = places is None
    if from_file:
        codes = load_place_codes()
        places = [{"id": code, "serve_state": "preparing"} for code in codes]
    else:
        codes = [place["id"] for place in places]
    log(JOB, "start", called=len(places))
    if raw_store.is_gcs(raw_dir):
        raw_rel = raw_store.relative_folder(run_ts)
    else:
        raw_rel = _relative(raw_store.folder_for(run_ts, raw_dir))
    storage = None
    if raw_store.is_gcs(raw_dir):
        from engine.raw_gcs import storage_client

        storage = storage_client()
    try:
        from concurrent.futures import ThreadPoolExecutor, wait

        deadline_at = time.monotonic() + deadline_s

        opening = {place["id"]: index for index, place in enumerate(places[:WORKERS])}

        def work(place: dict[str, str]) -> dict[str, Any]:
            delay = opening.pop(place["id"], 0) * STAGGER_S
            if delay:
                time.sleep(delay)
            if time.monotonic() >= deadline_at:
                return {
                    "id": place["id"],
                    "serve_state": place["serve_state"],
                    "outcome": "failed",
                    "error": "deadline",
                }
            return _one(place, client, env["SEOUL_API_KEY"], run_ts, raw_dir, storage)

        def run_pool(batch: list[dict[str, str]], workers: int) -> list[dict[str, Any]]:
            pool = ThreadPoolExecutor(max_workers=workers)
            try:
                futures = {pool.submit(work, place): place for place in batch}
                left = max(0.0, deadline_at - time.monotonic())
                done, pending = wait(futures, timeout=left)
                out = [future.result() for future in done]
                for future in pending:
                    place = futures[future]
                    out.append(
                        {
                            "id": place["id"],
                            "serve_state": place["serve_state"],
                            "outcome": "failed",
                            "error": "deadline",
                        }
                    )
                return out
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        results = run_pool(places, WORKERS)
        second_pass = {"tried": 0, "recovered": 0}
        retry_ids = {
            row["id"]
            for row in results
            if row["outcome"] == "failed"
            and any(name in row.get("error", "") for name in SECOND_PASS_ERRORS)
        }
        # Only when the pause and a full attempt (three tries at the 20 s read timeout) fit the deadline.
        if retry_ids and deadline_at - time.monotonic() > SECOND_PASS_PAUSE_S + 70:
            time.sleep(SECOND_PASS_PAUSE_S)
            again = run_pool([place for place in places if place["id"] in retry_ids], SECOND_PASS_WORKERS)
            by_id = {row["id"]: row for row in again}
            recovered = sum(1 for row in again if row["outcome"] == "ok")
            second_pass = {"tried": len(retry_ids), "recovered": recovered}
            results = [by_id.get(row["id"], row) for row in results]
    finally:
        if own_client:
            client.close()

    exit_code = 0
    only_file: list[str] = []
    only_db: list[str] = []
    try:
        with ledger(env["DATABASE_URL"], JOB) as ctx:
            if from_file:
                db_rows = _load_places(env["DATABASE_URL"])
                coded = [row for row in db_rows if row.get("poi_code") is not None]
                db_ids = {row["id"] for row in coded}
                file_ids = set(codes)
                only_file = sorted(file_ids - db_ids)
                only_db = sorted(db_ids - file_ids)
                if only_file or only_db:
                    ctx["status"] = "fail"
                    ctx["detail"] = {
                        "only_in_file": only_file,
                        "only_in_db": only_db,
                        "raw_dir": raw_rel,
                    }
                    exit_code = 1
                else:
                    serve = {row["id"]: row["serve_state"] for row in coded}
                    for result in results:
                        result["serve_state"] = serve[result["id"]]
            if exit_code == 0:
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
                found: dict[str, int] = {}
                if from_file:
                    from engine.jobs.forecast import apply_overlay, refresh_recommendations

                    stored_ids = [row["id"] for row in results if row["outcome"] == "ok"]
                    with _connect(env["DATABASE_URL"]) as overlay_conn:
                        apply_overlay(overlay_conn, run_ts, stored_ids)
                        refresh_recommendations(
                            overlay_conn,
                            run_ts,
                            run_ts.date(),
                            place_ids=stored_ids,
                            only_today=True,
                        )
                        overlay_conn.commit()
                        from engine.jobs import integrity

                        found = integrity.sweep(overlay_conn)
                        overlay_conn.rollback()
                ok = sum(1 for row in results if row["outcome"] == "ok")
                no_data = sum(1 for row in results if row["outcome"] == "no_data")
                failed = sum(1 for row in results if row["outcome"] == "failed")
                status = _status(results)
                detail = {
                    "called": len(places),
                    "ok": ok,
                    "no_data": no_data,
                    "failed": failed,
                    "failed_places": {
                        row["id"]: row.get("error", row["outcome"])
                        for row in results
                        if row["outcome"] == "failed"
                    },
                    "raw_dir": raw_rel,
                    "second_pass": second_pass,
                    "unknown_categories": sorted(
                        {
                            name
                            for result in results
                            if result["outcome"] == "ok"
                            for name in result["snapshot"].unknown_categories
                        }
                    ),
                }
                if found:
                    detail["integrity"] = found
                    if status == "ok":
                        status = "warn"
                ctx["detail"] = detail
                ctx["status"] = status
    except psycopg.OperationalError:
        log(JOB, "fail", reason="database unavailable", raw_dir=raw_rel)
        return 1
    if exit_code == 1:
        log(
            JOB,
            "fail",
            reason="place code mismatch",
            only_in_file=only_file,
            only_in_db=only_db,
            raw_dir=raw_rel,
        )
        return 1
    log(JOB, status, **detail)
    return 1 if status == "fail" else 0
