"""A partial refresh (collect re-scores only the places it fetched) must not leave another place's today row
pointing at an alternative whose window the refresh just removed. Found by the hourly `integrity` job on
2026-10-07: POI003 offered POI076 at 20시 after POI076's own row had no window left."""

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from engine.jobs.forecast import refresh_recommendations
from engine.parsers import KST
from engine.tests.tempdb import schema


def _row(conn, place_id, windows, no_window, alt_places):
    conn.execute(
        """
        insert into recommendations (
          place_id, date, tolerance, purpose, state, windows, no_window, hours, strip_mode,
          alt_dates, alt_places
        ) values (%s, '2026-10-07', 'moderate', 'food', 'on', %s, %s, %s, 'windows_only', '[]', %s)
        """,
        (
            place_id,
            Jsonb(windows),
            no_window,
            Jsonb(
                [
                    {"h": hour, "rating": 1, "in_window": False, "reason": "fit", "crowd": 2}
                    for hour in range(9, 24)
                ]
            ),
            Jsonb(alt_places),
        ),
    )


def test_partial_refresh_recomputes_the_alternatives_of_rows_it_did_not_rescore():
    with schema() as dsn:
        issued = datetime(2026, 10, 7, 5, 0, tzinfo=KST)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                """
                insert into places (id, tier, name, serve_state, lat, lon) values
                  ('POI003', 'A1', 'Busy', 'on', 37.560, 126.985),
                  ('POI076', 'A1', 'Near', 'on', 37.562, 126.987)
                """
            )
            conn.execute(
                "insert into similar_places (place_id, rank, other_id, score) "
                "values ('POI003', 1, 'POI076', 0.9)"
            )
            # POI076 has data only up to 20시 today: once it is re-scored at 20:30 nothing is left ahead.
            for hour in range(9, 21):
                conn.execute(
                    """
                    insert into forecast_hourly
                      (place_id, target_ts, issued_ts, source, level, a_all, a_food, a_shop, ready)
                    values ('POI076', %s, %s, 'profile', 3, 0.9, 0.9, 0.9, true)
                    """,
                    (datetime(2026, 10, 7, hour, tzinfo=KST), issued),
                )
            # Rows as the 20:00 collect left them: POI003 points at POI076 20시, POI076 still has that window.
            _row(
                conn,
                "POI003",
                [{"hours": [21], "score": 0.4, "crowd": 3}],
                False,
                [{"place_id": "POI076", "hours": [20], "crowd": 1}],
            )
            _row(conn, "POI076", [{"hours": [20], "score": 0.9, "crowd": 1}], False, [])
            kept_dates = [{"date": "2026-10-08", "hours": [13], "score": 0.8}]
            # Built by yesterday's forecast, the row also offers yesterday; after midnight that date is gone.
            past = {"date": "2026-10-06", "hours": [15], "score": 0.9}
            conn.execute(
                "update recommendations set alt_dates = %s where place_id = 'POI003'",
                (Jsonb([past, *kept_dates]),),
            )
            conn.commit()
            started = datetime(2026, 10, 7, 20, 30, tzinfo=KST)
            # The 20:30 collect fetched POI076 only (POI003's call failed).
            refresh_recommendations(conn, started, started.date(), place_ids=["POI076"], only_today=True)
            conn.commit()
            where = "date = '2026-10-07' and tolerance = 'moderate' and purpose = 'food'"
            near_now = conn.execute(
                f"select state, no_window from recommendations where place_id = 'POI076' and {where}"
            ).fetchone()
            alt, alt_dates = conn.execute(
                f"select alt_places, alt_dates from recommendations where place_id = 'POI003' and {where}"
            ).fetchone()
    # Precondition: the refresh really removed POI076's window (otherwise the test proves nothing).
    assert near_now[0] == "off" or near_now[1] is True
    assert all(item["place_id"] != "POI076" for item in alt or [])
    # The row that was not re-scored keeps its alternative dates (the pool held none of its other days),
    # except one that is now in the past.
    assert alt_dates == kept_dates
