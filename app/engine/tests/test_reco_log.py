"""recommendation_log keeps the first issue of a day and only today+3."""

from datetime import date, timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb

from engine import settings
from engine.reco import log_candidates


def test_log_candidates_are_only_the_on_rows_three_days_ahead():
    issued = date(2026, 10, 1)
    rows = [
        {"date": issued + timedelta(days=3), "state": "on"},
        {"date": issued + timedelta(days=3), "state": "off"},
        {"date": issued + timedelta(days=2), "state": "reference"},
        {"date": issued + timedelta(days=3), "state": "reference"},
    ]
    picked = log_candidates(rows, issued)
    assert [row["state"] for row in picked] == ["on", "reference"]
    assert all((row["date"] - issued).days == 3 for row in picked)


def test_second_insert_the_same_day_changes_nothing():
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    try:
        conn = psycopg.connect(url, autocommit=False, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.fail("local database not reachable (cd app; supabase start)")
    issued = date(2099, 1, 1)
    target = issued + timedelta(days=3)
    hours = Jsonb([{"h": hour, "rating": 1} for hour in range(9, 24)])
    windows = Jsonb([{"hours": [12], "score": 0.5}])
    with conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from recommendation_log")
            before = cur.fetchone()[0]
            for _ in range(2):
                cur.execute(
                    """
                    insert into recommendation_log (
                      place_id, issued_date, date, tolerance, purpose, state, windows, hours, p90, lively_min
                    ) values ('POI001', %s, %s, 'moderate', 'sight', 'on', %s, %s, 1.0, 0.5)
                    on conflict do nothing
                    """,
                    (issued, target, windows, hours),
                )
            cur.execute(
                """
                select count(*), min(date - issued_date), max(date - issued_date)
                from recommendation_log
                where place_id = 'POI001' and issued_date = %s
                """,
                (issued,),
            )
            count, low, high = cur.fetchone()
            cur.execute("select count(*) from recommendation_log")
            after = cur.fetchone()[0]
        conn.rollback()
    assert count == 1
    assert low == 3 and high == 3
    assert after == before + 1
