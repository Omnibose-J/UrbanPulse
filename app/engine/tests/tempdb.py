"""A private schema for tests. Nothing here writes the public schema's rows."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from engine import settings

TABLES = (
    "places",
    "live_obs",
    "commerce_obs",
    "city_fcst",
    "holidays",
    "level_thresholds",
    "tier_b_profile",
    "lively_profile",
    "lively_norm",
    "forecast_hourly",
    "recommendations",
    "similar_places",
    "forecast_log",
    "recommendation_log",
    "eval_daily",
    "reco_eval_daily",
    "strip_eval_daily",
    "model_registry",
    "job_runs",
)


def _scoped(url: str, name: str) -> str:
    info = {key: value for key, value in conninfo_to_dict(url).items() if value is not None}
    info["options"] = f"-c search_path={name}"
    return make_conninfo(**info)


@contextmanager
def schema():
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    name = "h1_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(url, autocommit=True, connect_timeout=5)
    try:
        admin.execute(f"create schema {name}")
        for table in TABLES:
            admin.execute(
                f"create table {name}.{table} (like public.{table} "
                "including defaults including identity including constraints including indexes)"
            )
        foreign = admin.execute(
            """
            select c.conname, t.relname
            from pg_constraint c
            join pg_class t on t.oid = c.conrelid
            join pg_namespace n on n.oid = t.relnamespace
            where n.nspname = %s and c.contype = 'f'
            """,
            (name,),
        ).fetchall()
        for conname, relname in foreign:
            admin.execute(f'alter table {name}.{relname} drop constraint "{conname}"')
        yield _scoped(url, name)
    finally:
        admin.execute(f"drop schema if exists {name} cascade")
        admin.close()
