"""Overlap rule and stable station ids. Synthetic polygons, no shapefile."""

import psycopg
import pytest
from psycopg.types.json import Jsonb
from shapely.geometry import box

from engine import settings
from engine.tierb.stations import _counts, covered, display_name, station_ids, upsert_station


def _fraction(station, union) -> float:
    return station.intersection(union).area / station.area


def test_half_the_circle_is_dropped_and_just_under_is_kept():
    station = box(0, 0, 10, 10)
    assert covered(_fraction(station, box(0, 0, 10, 5)))
    assert not covered(_fraction(station, box(0, 0, 10, 4.9)))


def test_ids_follow_normalised_name_order():
    keys = ["다", "가", "나"]
    assert station_ids(keys) == ["STN001", "STN002", "STN003"]
    assert station_ids(keys) == station_ids(list(reversed(keys)))


def test_second_upsert_changes_nothing_and_leaves_other_tiers():
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    try:
        conn = psycopg.connect(url, autocommit=False, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.fail("local database not reachable (cd app; supabase start)")
    row = {
        "id": "STNTEST",
        "name": "테스트역",
        "category": "역세권",
        "gu": "강남구",
        "lat": 37.5,
        "lon": 127.0,
        "geom": Jsonb({"type": "Point", "coordinates": [127.0, 37.5]}),
        "station_codes": ["0001"],
    }
    with conn:
        with conn.cursor() as cur:
            before = _counts(conn)
            cur.execute("delete from places where id = %s", ("STNTEST",))
            first = upsert_station(cur, row)
            second = upsert_station(cur, row)
            after = _counts(conn)
        conn.rollback()
    assert first == 1
    assert second == 0
    assert after == before


def test_display_name_ends_with_the_station_suffix():
    assert display_name("서울", ["서울(2)역", "서울역"]) == "서울역"
