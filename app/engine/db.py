"""Postgres access via psycopg 3 and the `job_runs` ledger."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=False)


@contextmanager
def job_run(database_url: str, job: str) -> Iterator[dict[str, Any]]:
    """Record a job in `job_runs`.

    Yields a mutable context; the job puts its result under `ctx["detail"]`. On a clean exit the row becomes
    `ok`; if an exception escapes, the row becomes `fail` with `{"error": "<Type>: <message>"}` merged into
    the detail and the exception is re-raised (invariant: a failed job never looks successful).
    """
    conn = connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("insert into job_runs (job, status) values (%s, 'running') returning id", (job,))
            row = cur.fetchone()
            assert row is not None
            run_id = row[0]
        conn.commit()
        ctx: dict[str, Any] = {"detail": None}
        try:
            yield ctx
            status = "ok"
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
