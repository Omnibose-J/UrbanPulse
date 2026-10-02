"""Count old observations. Deletion stays off until a retention decision."""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg.types.json import Jsonb

from engine import db, settings
from engine.log import log
from engine.parsers import KST

JOB = "archive"


def run(dry_run: bool = False, execute: bool = False) -> int:
    if execute:
        print("retention decision pending")
        return 2
    if not dry_run:
        print("deletion is not enabled")
        return 2
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    today = datetime.now(KST).date()
    cuts = {
        "live_obs": ("ts", today - timedelta(days=90)),
        "commerce_obs": ("ts", today - timedelta(days=90)),
        "forecast_log": ("target_ts", today - timedelta(days=180)),
    }
    counts = {}
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            for table, (column, cut) in cuts.items():
                stamp = datetime.combine(cut, datetime.min.time()).replace(tzinfo=KST)
                cur.execute(f"select count(*) from {table} where {column} < %s", (stamp,))
                counts[table] = cur.fetchone()[0]
        for table, count in counts.items():
            print(f"{table} {count}")
        _record(conn, {"dry_run": True, "counts": counts})
        conn.commit()
    log(JOB, "done", dry_run=True)
    return 0


def _record(conn, detail: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into job_runs (job, status, finished_at, detail) values ('archive', 'ok', now(), %s)",
            (Jsonb(detail),),
        )
