"""Postgres access via psycopg 3 and the `job_runs` ledger."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def connect(database_url: str) -> psycopg.Connection:
    """Connect with a 5s timeout. A failure is a fixed message, never the URL."""
    try:
        return psycopg.connect(database_url, autocommit=False, connect_timeout=5)
    except psycopg.Error:
        raise psycopg.OperationalError("database connection failed") from None


def abandon_stale(database_url: str, job: str) -> None:
    """A start older than two hours is not still running."""
    conn = connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                update job_runs
                set status = 'fail', finished_at = now(), detail = %s
                where job = %s and status = 'running'
                  and started_at < now() - interval '2 hours'
                """,
                (Jsonb({"reason": "abandoned"}), job),
            )
        conn.commit()
    finally:
        conn.close()


def write_ledger(database_url: str, run_id: int, status: str, detail) -> None:
    """Ledger write on its own connection, after the caller's transaction was rolled back."""
    conn = connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "update job_runs set finished_at = now(), status = %s, detail = %s where id = %s",
                (status, Jsonb(detail) if detail is not None else None, run_id),
            )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def ledger(database_url: str, job: str):
    """Start a job row, yield (conn, ctx). On any error roll back, record fail, re-raise."""
    abandon_stale(database_url, job)
    conn = connect(database_url)
    run_id = None
    try:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            cur.execute("insert into job_runs (job, status) values (%s, 'running') returning id", (job,))
            run_id = cur.fetchone()[0]
        conn.commit()
        ctx: dict[str, Any] = {"detail": None, "status": "ok"}
        try:
            yield conn, ctx
            write_ledger(database_url, run_id, ctx.get("status") or "ok", ctx["detail"])
        except BaseException as exc:
            conn.rollback()
            detail = dict(ctx["detail"] or {})
            detail["error"] = f"{type(exc).__name__}: {exc}"
            write_ledger(database_url, run_id, "fail", detail)
            raise
    finally:
        conn.close()


@contextmanager
def job_run(database_url: str, job: str) -> Iterator[dict[str, Any]]:
    """Record a job in `job_runs`. Failures roll back, then the ledger is written on its own connection."""
    with ledger(database_url, job) as (_conn, ctx):
        yield ctx
