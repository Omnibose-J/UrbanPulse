"""Database steps of the cloud move: schema check, one-off data copy, gap and recommendation comparison.

URLs come from env files (`DATABASE_URL`), never from the command line, and are never printed.

    python scripts/cloud/dbtool.py check-schema --target-env .env.cloud
    python scripts/cloud/dbtool.py copy         --target-env .env.cloud
    python scripts/cloud/dbtool.py gap          --target-env .env.cloud --since 2026-10-02
    python scripts/cloud/dbtool.py recos-diff   --target-env .env.cloud [--against saved.bin]
    python scripts/cloud/dbtool.py recos-save   --target-env .env.cloud --out saved.bin
    python scripts/cloud/dbtool.py last-runs    --target-env .env.cloud --job collect --count 2

The source is `.env` (the local database) unless `--source-env` says otherwise.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

from engine import db
from engine.parsers import KST

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOCKED_ROLES = ("anon", "authenticated")


def url_from(env_file: str) -> str:
    path = Path(env_file)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        sys.exit(f"missing env file: {env_file}")
    value = dotenv_values(path).get("DATABASE_URL") or ""
    if not value:
        sys.exit(f"missing DATABASE_URL in {env_file}")
    return value


def tables(conn: psycopg.Connection) -> list[str]:
    """Public tables, a referenced table before the tables that reference it."""
    names = [
        row[0]
        for row in conn.execute(
            "select tablename from pg_tables where schemaname = 'public' order by tablename"
        ).fetchall()
    ]
    edges = conn.execute(
        """
        select child.relname, parent.relname
        from pg_constraint c
        join pg_class child on child.oid = c.conrelid
        join pg_class parent on parent.oid = c.confrelid
        join pg_namespace n on n.oid = child.relnamespace
        where c.contype = 'f' and n.nspname = 'public' and child.oid <> parent.oid
        """
    ).fetchall()
    needs = {name: {parent for child, parent in edges if child == name} for name in names}
    ordered: list[str] = []
    while needs:
        free = sorted(name for name, parents in needs.items() if not parents - set(ordered))
        if not free:
            sys.exit("foreign keys form a cycle; copy order is undefined")
        ordered.extend(free)
        for name in free:
            del needs[name]
    return ordered


def columns(conn: psycopg.Connection, table: str) -> list[str]:
    """Stored columns in table order. Generated columns are computed by the target."""
    return [
        row[0]
        for row in conn.execute(
            """
            select a.attname from pg_attribute a
            where a.attrelid = %s::regclass and a.attnum > 0 and not a.attisdropped and a.attgenerated = ''
            order by a.attnum
            """,
            (f"public.{table}",),
        ).fetchall()
    ]


def count(conn: psycopg.Connection, table: str) -> int:
    return conn.execute(sql.SQL("select count(*) from public.{}").format(sql.Identifier(table))).fetchone()[0]


def check_schema(source: psycopg.Connection, target: psycopg.Connection) -> int:
    want, have = set(tables(source)), set(tables(target))
    no_rls = [
        row[0]
        for row in target.execute(
            "select tablename from pg_tables where schemaname = 'public' and not rowsecurity order by 1"
        ).fetchall()
    ]
    grants = target.execute(
        "select count(*) from information_schema.role_table_grants "
        "where table_schema = 'public' and grantee = any(%s)",
        (list(BLOCKED_ROLES),),
    ).fetchone()[0]
    print(f"tables {len(have)} (source {len(want)})")
    print(f"missing {sorted(want - have)} extra {sorted(have - want)}")
    print(f"without_rls {no_rls}")
    print(f"anon_authenticated_grants {grants}")
    ok = want == have and not no_rls and grants == 0
    print("schema OK" if ok else "schema FAIL")
    return 0 if ok else 1


def copy(source: psycopg.Connection, target: psycopg.Connection) -> int:
    """Copy every public table once. One snapshot on the source, one transaction on the target."""
    source.execute("set transaction isolation level repeatable read read only")
    order = tables(source)
    if set(order) != set(tables(target)):
        print("target tables differ from the source; run the schema push first")
        return 1
    filled = [name for name in order if count(target, name) > 0]
    if filled:
        print(f"target is not empty: {filled}. Nothing was copied; rows are never merged by hand.")
        return 1
    rows = {}
    for name in order:
        names = columns(source, name)
        if names != columns(target, name):
            print(f"column list differs: {name}")
            target.rollback()
            return 1
        listing = sql.SQL(", ").join(sql.Identifier(column) for column in names)
        out = sql.SQL("copy (select {} from public.{}) to stdout (format binary)").format(
            listing, sql.Identifier(name)
        )
        into = sql.SQL("copy public.{} ({}) from stdin (format binary)").format(sql.Identifier(name), listing)
        with source.cursor().copy(out) as reader, target.cursor().copy(into) as writer:
            for block in reader:
                writer.write(block)
        rows[name] = (count(source, name), count(target, name))
    for name in order:
        for column in columns(target, name):
            sequence = target.execute(
                "select pg_get_serial_sequence(%s, %s)", (f"public.{name}", column)
            ).fetchone()[0]
            if sequence:
                target.execute(
                    sql.SQL("select setval(%s, (select max({}) from public.{}))").format(
                        sql.Identifier(column), sql.Identifier(name)
                    ),
                    (sequence,),
                )
    newest = [conn.execute("select max(ts) from public.live_obs").fetchone()[0] for conn in (source, target)]
    equal = all(a == b for a, b in rows.values()) and newest[0] == newest[1]
    print(f"{'table':<24}{'source':>10}{'target':>10}")
    for name, (a, b) in rows.items():
        print(f"{name:<24}{a:>10}{b:>10}{'' if a == b else '  DIFFERENT'}")
    print(f"live_obs max(ts) source {newest[0]} target {newest[1]}")
    if not equal:
        target.rollback()
        print("copy FAIL: nothing was committed")
        return 1
    target.commit()
    size = target.execute("select pg_database_size(current_database())").fetchone()[0]
    print(f"target size {size / 1024 / 1024:.0f} MB")
    print("copy OK")
    return 0


def gap(source: psycopg.Connection, target: psycopg.Connection, since: str) -> int:
    """Every observation time the source has from `since` on must exist in the target."""
    query = "select distinct ts from public.live_obs where ts >= %s::timestamp at time zone 'Asia/Seoul'"
    have = {row[0] for row in target.execute(query, (since,)).fetchall()}
    want = {row[0] for row in source.execute(query, (since,)).fetchall()}
    lost = sorted(want - have)
    print(f"distinct ts since {since}: source {len(want)} target {len(have)} missing_in_target {len(lost)}")
    for ts in lost[:10]:
        print(f"  missing {ts}")
    return 1 if lost or not want else 0


def reco_rows(conn: psycopg.Connection, from_days: int) -> tuple[list[str], dict[tuple, tuple]]:
    """Recommendation rows from today + `from_days` on, keyed by their primary key, without `generated_at`."""
    first = datetime.now(KST).date() + timedelta(days=from_days)
    names = [name for name in columns(conn, "recommendations") if name != "generated_at"]
    query = sql.SQL("select {} from public.recommendations where date >= %s").format(
        sql.SQL(", ").join(sql.Identifier(name) for name in names)
    )
    key = [names.index(name) for name in ("place_id", "date", "tolerance", "purpose")]
    return names, {tuple(row[i] for i in key): row for row in conn.execute(query, (first,)).fetchall()}


def recos_save(target: psycopg.Connection, from_days: int, out: str) -> int:
    names, rows = reco_rows(target, from_days)
    Path(out).write_bytes(pickle.dumps((names, rows)))
    print(f"saved {len(rows)} recommendation rows")
    return 0 if rows else 1


def recos_diff(
    left: tuple[list[str], dict], target: psycopg.Connection, from_days: int, same_data: bool
) -> int:
    """`left` (the source database, or a saved set) against the target. A difference or an empty set fails.

    Two databases fed by different collectors hold different rows for today, and `alt_dates` of a later
    date may point at today. That column is compared only when both sides were built from the same data.
    """
    names, a = left
    other, b = reco_rows(target, from_days)
    if names != other:
        print("column lists differ")
        return 1
    if not same_data:
        skip = names.index("alt_dates")
        a = {k: row[:skip] + row[skip + 1 :] for k, row in a.items()}
        b = {k: row[:skip] + row[skip + 1 :] for k, row in b.items()}
        names = names[:skip] + names[skip + 1 :]
        print("alt_dates is not compared across two collectors")
    differing = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))
    print(f"recommendations from today+{from_days}: left {len(a)} target {len(b)} differing {len(differing)}")
    for k in differing[:10]:
        row_a, row_b = a.get(k), b.get(k)
        if row_a is None or row_b is None:
            print(f"  {k}: only in {'target' if row_a is None else 'left'}")
        else:
            print(f"  {k}: {[name for name, x, y in zip(names, row_a, row_b, strict=True) if x != y]}")
    return 1 if differing or not a else 0


def last_runs(target: psycopg.Connection, job: str, wanted: int) -> int:
    """The newest `wanted` runs of a job must all be `ok` and the newest under 45 minutes old."""
    rows = target.execute(
        "select status, started_at, now() - started_at < interval '45 minutes' from public.job_runs "
        "where job = %s order by id desc limit %s",
        (job, wanted),
    ).fetchall()
    for status, started, _fresh in rows:
        print(f"{job} {status} {started.astimezone(KST):%Y-%m-%d %H:%M}")
    ok = len(rows) == wanted and all(row[0] == "ok" for row in rows) and rows[0][2]
    print("last runs OK" if ok else "last runs FAIL")
    return 0 if ok else 1


def runs_since(target: psycopg.Connection, since: str, jobs: list[str]) -> int:
    """Count ledger rows of `jobs` started at or after a UTC time. Any row fails (used to prove isolation)."""
    found = target.execute(
        "select count(*) from public.job_runs "
        "where job = any(%s) and started_at >= %s::timestamp at time zone 'UTC'",
        (jobs, since),
    ).fetchone()[0]
    print(f"runs of {jobs} since {since} UTC: {found}")
    return 0 if found == 0 else 1


COMMANDS = ("check-schema", "copy", "gap", "recos-save", "recos-diff", "last-runs", "runs-since")
NO_SOURCE = ("recos-save", "last-runs", "runs-since")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dbtool")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--source-env", default=".env")
    parser.add_argument("--target-env", required=True)
    parser.add_argument("--since", help="gap: first KST date, YYYY-MM-DD; runs-since: UTC time")
    parser.add_argument("--from-days", type=int, default=2, help="recos-*: first date is today + N")
    parser.add_argument("--out", help="recos-save: file to write")
    parser.add_argument("--against", help="recos-diff: a recos-save file used instead of the source database")
    parser.add_argument("--job", help="last-runs: job name; runs-since: comma-separated job names")
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args(argv)
    for command, option in (
        ("gap", "since"),
        ("recos-save", "out"),
        ("last-runs", "job"),
        ("runs-since", "since"),
        ("runs-since", "job"),
    ):
        if args.command == command and not getattr(args, option):
            parser.error(f"{command} needs --{option}")
    saved = args.command == "recos-diff" and args.against
    source = None if args.command in NO_SOURCE or saved else db.connect(url_from(args.source_env))
    target = db.connect(url_from(args.target_env))
    try:
        if args.command == "check-schema":
            return check_schema(source, target)
        if args.command == "copy":
            return copy(source, target)
        if args.command == "gap":
            return gap(source, target, args.since)
        if args.command == "recos-save":
            return recos_save(target, args.from_days, args.out)
        if args.command == "runs-since":
            return runs_since(target, args.since, args.job.split(","))
        if args.command == "last-runs":
            return last_runs(target, args.job, args.count)
        left = pickle.loads(Path(args.against).read_bytes()) if saved else reco_rows(source, args.from_days)
        return recos_diff(left, target, args.from_days, same_data=bool(saved))
    finally:
        if source is not None:
            source.close()
        target.close()


if __name__ == "__main__":
    sys.exit(main())
