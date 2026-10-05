"""Replay one KST day's raw snapshots into live_obs, commerce_obs, and city_fcst.

Uses the same upsert statements as collect. A second run of the same files changes nothing.
"""

from __future__ import annotations

from datetime import datetime

from engine import raw_store, settings
from engine.jobs.collect import _ledger, _raw_dir, store_observations
from engine.log import log
from engine.parsers import KST, parse_citydata

JOB = "ingest_raw"


def _day(date: str | None):
    if date is None:
        return datetime.now(KST).date()
    return datetime.strptime(date, "%Y-%m-%d").date()


def _fail_before_store(database_url: str, exc: BaseException) -> int:
    log(JOB, "fail", reason=type(exc).__name__, stage="read")
    try:
        with _ledger(database_url, JOB) as ctx:
            ctx["detail"] = {"stage": "read"}  # the ledger adds `error` from the exception
            raise exc
    except Exception:
        # The context manager wrote the fail row; a database that is down as well leaves only the log line.
        return 1
    return 1


def run(date: str | None = None) -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    day = _day(date)
    location = _raw_dir(env, None)
    live = []
    commerce = []
    forecasts = []
    unknowns: list[tuple[str, ...]] = []
    failed = []
    folders: set[str] = set()
    files = 0
    saw_any = False
    try:
        for folder, place_id, body, error in raw_store.iter_day(location, day):
            saw_any = True
            files += 1
            folders.add(folder)
            if error or body is None:
                failed.append({"file": place_id, "error": error or "empty"})
                continue
            try:
                snapshot = parse_citydata(place_id, body)
            except (ValueError, KeyError, TypeError) as exc:
                failed.append({"file": place_id, "error": type(exc).__name__})
                continue
            if snapshot.live is None:
                continue
            live.append(snapshot.live)
            if snapshot.commerce is not None:
                commerce.append(snapshot.commerce)
            forecasts.extend(snapshot.forecasts)
            if snapshot.unknown_categories:
                unknowns.append(snapshot.unknown_categories)
    except Exception as exc:
        # The store itself failed (bucket listing, disk): a `fail` ledger row names the stage, then exit 1.
        return _fail_before_store(env["DATABASE_URL"], exc)
    if not saw_any:
        log(JOB, "fail", reason="no raw folder", raw_dir=day.isoformat())
        return 1
    log(JOB, "start", date=day.isoformat(), files=files, failed=len(failed))
    try:
        with _ledger(env["DATABASE_URL"], JOB) as ctx:
            affected = store_observations(env["DATABASE_URL"], live, commerce, forecasts)
            ctx["detail"] = {
                "folders": len(folders),
                "files": files,
                "failed": failed,
                "live": len(live),
                "commerce": len(commerce),
                "unknown_categories": sorted(
                    {name for snapshot_unknown in unknowns for name in snapshot_unknown}
                ),
            }
            ctx["status"] = "warn" if failed else "ok"
    except Exception as exc:
        log(JOB, "fail", reason=f"{type(exc).__name__}")
        return 1
    log(JOB, "done", affected=affected, **ctx["detail"])
    return 0
