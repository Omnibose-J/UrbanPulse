"""Replay one KST day's raw snapshots into live_obs, commerce_obs, and city_fcst.

Uses the same upsert statements as collect. A second run of the same files changes nothing.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime

from engine import settings
from engine.jobs.collect import _ledger, _raw_dir, _relative, store_observations
from engine.log import log
from engine.parsers import KST, parse_citydata

JOB = "ingest_raw"


def _day(date: str | None):
    if date is None:
        return datetime.now(KST).date()
    return datetime.strptime(date, "%Y-%m-%d").date()


def run(date: str | None = None) -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    day = _day(date)
    root = _raw_dir(env, None) / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
    if not root.is_dir():
        log(JOB, "fail", reason="no raw folder", raw_dir=_relative(root))
        return 1
    folders = sorted(path for path in root.iterdir() if path.is_dir())
    live = []
    commerce = []
    forecasts = []
    files = 0
    unknowns: list[tuple[str, ...]] = []
    for folder in folders:
        for path in sorted(folder.glob("*.json.gz")):
            place_id = path.name.removesuffix(".json.gz")
            body = json.loads(gzip.decompress(path.read_bytes()))
            snapshot = parse_citydata(place_id, body)
            files += 1
            if snapshot.live is None:
                continue
            live.append(snapshot.live)
            if snapshot.commerce is not None:
                commerce.append(snapshot.commerce)
            forecasts.extend(snapshot.forecasts)
            if snapshot.unknown_categories:
                unknowns.append(snapshot.unknown_categories)
    log(JOB, "start", date=day.isoformat(), folders=len(folders), files=files)
    try:
        with _ledger(env["DATABASE_URL"], JOB) as ctx:
            affected = store_observations(env["DATABASE_URL"], live, commerce, forecasts)
            ctx["detail"] = {
                "folders": len(folders),
                "files": files,
                "live": len(live),
                "commerce": len(commerce),
                "unknown_categories": sorted(
                    {name for snapshot_unknown in unknowns for name in snapshot_unknown}
                ),
            }
            ctx["status"] = "ok"
    except Exception as exc:
        log(JOB, "fail", reason=f"{type(exc).__name__}")
        return 1
    log(JOB, "done", affected=affected, **ctx["detail"])
    return 0
