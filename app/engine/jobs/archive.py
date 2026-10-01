"""Move old observations aside. This SOW runs it only with --dry-run."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.log import log
from engine.parsers import KST

JOB = "archive"


def run(dry_run: bool = False) -> int:
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
        if dry_run:
            for table, count in counts.items():
                print(f"{table} {count}")
            _record(conn, {"dry_run": True, "counts": counts})
            conn.commit()
            log(JOB, "done", dry_run=True)
            return 0
        root = settings.REPO_ROOT / "data" / "archive"
        for table, (column, cut) in cuts.items():
            folder = root / table
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{today.isoformat()}.parquet"
            if target.exists():
                log(JOB, "fail", reason=f"{target.name} already exists")
                return 1
            stamp = datetime.combine(cut, datetime.min.time()).replace(tzinfo=KST)
            frame = pd.read_sql_query(f"select * from {table} where {column} < %s", conn, params=(stamp,))
            frame.to_parquet(target, index=False)
            written = len(pd.read_parquet(target))
            if written != counts[table]:
                log(JOB, "fail", reason=f"{table} count {counts[table]} file {written}")
                return 1
            with conn.cursor() as cur:
                cur.execute(f"delete from {table} where {column} < %s", (stamp,))
            conn.commit()
    log(JOB, "done")
    return 0


def _record(conn, detail: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into job_runs (job, status, finished_at, detail) values ('archive', 'ok', now(), %s)",
            (Jsonb(detail),),
        )
