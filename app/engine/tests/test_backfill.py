"""Backfill dedupe and a rolled-back load of the CSV fixtures."""

import csv
import uuid
from pathlib import Path

from engine import db, settings
from engine.jobs.backfill import (
    _COMMERCE_UPSERT,
    _LIVE_UPSERT,
    _commerce_record,
    _live_record,
    _load_files,
    keep_latest,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_duplicate_ppltn_time_keeps_latest_snap():
    # The live extracts have no repeated (poi, ppltn_time). Two real rows from different
    # extracts keep their snap_time and pmin; only the observation time is shared.
    left_src = _rows("obs_hist_sample.csv")[0]
    right_src = _rows("obs_sample.csv")[0]
    assert left_src["snap_time"] != right_src["snap_time"]
    shared = left_src["ppltn_time"]
    left = dict(left_src)
    right = dict(right_src, poi=left_src["poi"], ppltn_time=shared)
    kept = keep_latest([left, right], lambda row: (row["poi"], row["ppltn_time"]))
    expected = left if left["snap_time"] >= right["snap_time"] else right
    winner = kept[(left_src["poi"], shared)]
    assert winner["snap_time"] == expected["snap_time"]
    assert winner["pmin"] == expected["pmin"]


def test_real_commerce_duplicate_keeps_latest_snap():
    rows = _rows("cmrcl_sample.csv")
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault((row["poi"], row["cmrcl_time"]), []).append(row)
    duplicated = [group for group in groups.values() if len({item["snap_time"] for item in group}) >= 2]
    assert duplicated
    kept = keep_latest(rows, lambda row: (row["poi"], row["cmrcl_time"]))
    for group in duplicated:
        latest = max(group, key=lambda item: item["snap_time"])
        winner = kept[(latest["poi"], latest["cmrcl_time"])]
        assert winner["snap_time"] == latest["snap_time"]
        assert winner["pay_cnt"] == latest["pay_cnt"]


def _load_both(conn) -> None:
    pois = {row["poi"] for name in ("obs_hist_sample.csv", "cmrcl_sample.csv") for row in _rows(name)}
    _load_files(
        conn,
        FIXTURES,
        ("obs_hist_sample.csv",),
        pois,
        lambda row: (row["poi"], row["ppltn_time"]),
        _live_record,
        _LIVE_UPSERT,
    )
    _load_files(
        conn,
        FIXTURES,
        ("cmrcl_sample.csv",),
        pois,
        lambda row: (row["poi"], row["cmrcl_time"]),
        _commerce_record,
        _COMMERCE_UPSERT,
    )


def _counts(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("select count(*) from live_obs")
        live = cur.fetchone()[0]
        cur.execute("select count(*) from commerce_obs")
        commerce = cur.fetchone()[0]
    return live, commerce


def test_loading_fixtures_twice_keeps_the_same_counts():
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    schema = "m1bf_" + uuid.uuid4().hex[:8]
    with db.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"create schema {schema}")
            cur.execute(f"create table {schema}.live_obs (like public.live_obs including all)")
            cur.execute(f"create table {schema}.commerce_obs (like public.commerce_obs including all)")
            cur.execute(f"set search_path to {schema}")
        conn.commit()
        try:
            _load_both(conn)
            first = _counts(conn)
            _load_both(conn)
            second = _counts(conn)
            assert first == second
            assert first[0] > 0 and first[1] > 0
        finally:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()
