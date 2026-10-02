"""The forecast job's own functions, run on a private schema with hand-built history."""

import math
from datetime import date, datetime, timedelta

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from engine.jobs import forecast
from engine.parsers import KST
from engine.tests.tempdb import schema

TODAY = date(2026, 9, 14)  # a Monday with no holiday in the following week
STARTED = datetime(2026, 9, 14, 5, 0, tzinfo=KST)
EIGHT_CATS = {
    "음식·음료": 40,
    "유통": 10,
    "패션·뷰티": 10,
    "여가·오락": 0,
    "생활서비스": 0,
    "의료·건강": 0,
    "교육": 0,
    "숙박": 0,
}


class FakeModel:
    """Knows one place and always says +20 %."""

    place_index = {"POI001": 0}

    def ratio(self, place_id, timestamps, horizon_d, holidays, seol_starts, chuseok_starts):
        assert place_id in self.place_index
        return np.full(len(timestamps), math.log(1.2))


def at(day: date, hour: int) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=KST) + timedelta(hours=hour)


def seed(conn) -> None:
    """Three places with four weeks of flat history at 150 people (level 1 between cuts 100 and 200)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into places (id, tier, name, foreign_heavy, serve_state, lat, lon) values
              ('POI001', 'A1', 'In the model', false, 'on', 37.50, 127.00),
              ('POI002', 'A1', 'Not in the model', false, 'on', 37.51, 127.01),
              ('POI003', 'A2', 'A park', false, 'on', 37.52, 127.02)
            """
        )
        cur.execute(
            """
            insert into level_thresholds (place_id, t1, t2, t3, based_on_days)
            select id, 100, 200, 300, 28 from places
            """
        )
        cur.execute(
            "insert into lively_norm (place_id, p90_all, p90_food, p90_shop) values ('POI001', 100, 50, 25)"
        )
        history = [
            (place, at(TODAY - timedelta(days=back), hour), 150, 150, 1)
            for place in ("POI001", "POI002", "POI003")
            for back in range(1, 29)
            for hour in range(24)
        ]
        cur.executemany(
            "insert into live_obs (place_id, ts, pop_min, pop_max, level) values (%s, %s, %s, %s, %s)",
            history,
        )
        profile = [
            (place, day_type, hour, 0.8, 0.8, 0.8, 5)
            for place in ("POI001", "POI002")
            for day_type in ("weekday", "weekend", "holiday", "myeongjeol")
            for hour in range(24)
        ]
        cur.executemany(
            "insert into lively_profile (place_id, day_type, hour, a_all, a_food, a_shop, n_days) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            profile,
        )
    conn.commit()


def row(conn, place: str, day: date, hour: int):
    return conn.execute(
        "select source, pop, level, ready, a_all, a_actual, stale from forecast_hourly where "
        "place_id = %s and target_ts = %s",
        (place, at(day, hour)),
    ).fetchone()


def write(conn):
    logs = forecast._write_forecasts(
        conn, STARTED, TODAY, FakeModel(), set(range(7)), "v-test", {"POI001", "POI002", "POI003"}
    )
    conn.commit()
    return logs


def test_source_follows_the_model_index_and_the_passing_horizons():
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        logs = write(conn)
        assert conn.execute("select count(*) from forecast_hourly").fetchone()[0] == 3 * 8 * 24

        source, pop, level, ready, a_all, a_actual, _ = row(conn, "POI001", TODAY + timedelta(days=3), 15)
        assert (source, level, ready, a_actual) == ("model", 1, True, False)
        assert math.isclose(pop, 180.0, rel_tol=1e-6)
        assert math.isclose(a_all, 0.8, rel_tol=1e-6)

        # horizon 7 did not pass the gate in this registry: baseline only
        source, pop, level, ready, *_ = row(conn, "POI001", TODAY + timedelta(days=7), 15)
        assert (source, level, ready) == ("profile", 1, True)
        assert math.isclose(pop, 150.0, rel_tol=1e-6)

        # a place the model does not know is baseline only at every horizon
        assert row(conn, "POI002", TODAY + timedelta(days=3), 15)[:2] == ("profile", 150.0)

        # A2 rows never carry activity (invariant 6)
        assert row(conn, "POI003", TODAY + timedelta(days=3), 15)[4] is None

        # the evaluation log: horizons 1, 3, 7 and hours 9..23 only, with what was served
        horizons = {entry[3] for entry in logs}
        hours = {entry[2].astimezone(KST).hour for entry in logs}
        assert horizons == {1, 3, 7}
        assert hours == set(range(9, 24))
        served = {
            (entry[0], entry[3]): (entry[4], entry[5])
            for entry in logs
            if entry[2] == at(TODAY + timedelta(days=entry[3]), 15)
        }
        assert (
            math.isclose(served[("POI001", 3)][0], 180.0, rel_tol=1e-6) and served[("POI001", 3)][1] == 150.0
        )
        assert served[("POI001", 7)] == (150.0, 150.0)


def test_a_forecast_never_reads_what_was_not_known_at_issue_time():
    """Invariant 1. Observations dated today or later must not move a baseline; horizon 7 must skip week 1."""
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        write(conn)
        before = conn.execute(
            "select place_id, target_ts, source, pop, level from forecast_hourly where target_ts >= "
            "%s order by 1, 2",
            (at(TODAY + timedelta(days=1), 0),),
        ).fetchall()
        poison = [
            ("POI001", at(TODAY + timedelta(days=ahead), hour), 99999, 99999, 3)
            for ahead in range(1, 8)
            for hour in range(24)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "insert into live_obs (place_id, ts, pop_min, pop_max, level) values (%s, %s, %s, %s, %s)",
                poison,
            )
        conn.commit()
        write(conn)
        after = conn.execute(
            "select place_id, target_ts, source, pop, level from forecast_hourly where target_ts >= "
            "%s order by 1, 2",
            (at(TODAY + timedelta(days=1), 0),),
        ).fetchall()
        assert after == before

        # Week 1 of a horizon-7 target is today itself. Observations made today, after issue, must be ignored.
        with conn.cursor() as cur:
            cur.execute("delete from live_obs where ts >= %s", (at(TODAY, 0),))
            cur.executemany(
                "insert into live_obs (place_id, ts, pop_min, pop_max, level) values (%s, %s, %s, %s, %s)",
                [("POI001", at(TODAY, hour), 99999, 99999, 3) for hour in range(24)],
            )
        conn.commit()
        write(conn)
        assert row(conn, "POI001", TODAY + timedelta(days=7), 15)[:2] == ("profile", 150.0)
        # the same observations are today's measured hours, which is what the overlay is for
        assert row(conn, "POI001", TODAY, 3)[:3] == ("live", 99999.0, 3)


def test_a_place_with_one_week_of_history_is_not_ready():
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        conn.execute(
            "delete from live_obs where place_id = 'POI002' and ts < %s", (at(TODAY - timedelta(days=7), 0),)
        )
        conn.commit()
        write(conn)
        source, pop, level, ready, *_ = row(conn, "POI002", TODAY + timedelta(days=2), 15)
        assert (source, pop, level, ready) == ("profile", None, None, False)


def test_overlay_marks_measured_hours_live_and_city_forecast_hours_seoul():
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        write(conn)
        with conn.cursor() as cur:
            cur.execute(
                "insert into live_obs (place_id, ts, pop_min, pop_max, level) values "
                "('POI001', %s, 240, 260, 2), ('POI001', %s, 280, 300, 2)",
                (at(TODAY, 9), at(TODAY, 9) + timedelta(minutes=30)),
            )
            cur.execute(
                "insert into city_fcst (place_id, target_ts, issued_ts, pop_min, pop_max, level) values "
                "('POI001', %s, %s, 300, 340, 3)",
                (at(TODAY, 12), at(TODAY, 9)),
            )
            cur.execute(
                "insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts) values "
                "('POI001', %s, 1, 80, %s)",
                (at(TODAY, 9) + timedelta(minutes=10), Jsonb(EIGHT_CATS)),
            )
        conn.commit()
        now = at(TODAY, 9) + timedelta(minutes=40)
        forecast.apply_overlay(conn, now, ["POI001"])
        conn.commit()

        source, pop, level, ready, a_all, a_actual, stale = row(conn, "POI001", TODAY, 9)
        assert (source, level, ready, a_actual, stale) == ("live", 2, True, True, False)
        assert math.isclose(pop, 270.0, rel_tol=1e-6)  # mean of the two half-hour stamps
        assert math.isclose(a_all, 0.8, rel_tol=1e-6)  # 80 payments / p90 100
        assert row(conn, "POI001", TODAY, 12)[:3] == ("seoul", 320.0, 3)
        # an hour with neither stays what the forecast wrote, with the expected activity
        source, _pop, _level, _ready, a_all, a_actual, _stale = row(conn, "POI001", TODAY, 15)
        assert (source, a_actual) == ("model", False)
        # a place that was not passed in is untouched
        assert row(conn, "POI002", TODAY, 9)[0] == "profile"

        # 91 minutes after the newest observation the place is stale
        forecast.apply_overlay(conn, at(TODAY, 9) + timedelta(minutes=30 + 91), ["POI001"])
        conn.commit()
        assert row(conn, "POI001", TODAY, 9)[6] is True


def test_refresh_builds_rows_and_logs_three_days_ahead_once():
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        write(conn)
        first = forecast.refresh_recommendations(conn, STARTED, TODAY)
        conn.commit()
        # 2 A1 places x 3 purposes + 1 A2 place, 3 tolerances, 8 dates
        assert first["rows"] == (2 * 3 + 1) * 3 * 8
        assert conn.execute("select count(*) from recommendations").fetchone()[0] == first["rows"]
        state, windows, hours = conn.execute(
            "select state, windows, hours from recommendations "
            "where place_id = 'POI001' and date = %s and tolerance = 'moderate' and purpose = 'sight'",
            (TODAY + timedelta(days=2),),
        ).fetchone()
        assert state == "on" and len(hours) == 15 and 1 <= len(windows) <= 3
        assert all(cell["reason"] == "fit" and cell["crowd"] == 1 for cell in hours)

        assert forecast._insert_logs(conn, [], first["log_rows"]) > 0
        conn.commit()
        logged = conn.execute(
            "select count(*), min(date - issued_date), max(date - issued_date) from recommendation_log"
        ).fetchone()
        assert logged[1] == 3 and logged[2] == 3

        second = forecast.refresh_recommendations(conn, STARTED + timedelta(minutes=5), TODAY)
        forecast._insert_logs(conn, [], second["log_rows"])
        conn.commit()
        assert (
            conn.execute(
                "select count(*), min(date - issued_date), max(date - issued_date) from recommendation_log"
            ).fetchone()
            == logged
        )
        assert conn.execute("select count(*) from recommendations").fetchone()[0] == first["rows"]


def test_today_only_picks_hours_still_ahead():
    with schema() as dsn, psycopg.connect(dsn, connect_timeout=5) as conn:
        seed(conn)
        write(conn)
        forecast.refresh_recommendations(conn, STARTED, TODAY)
        conn.commit()
        late = at(TODAY, 21) + timedelta(minutes=5)
        forecast.refresh_recommendations(conn, late, TODAY, place_ids=["POI001"], only_today=True)
        conn.commit()
        windows = conn.execute(
            "select windows from recommendations where place_id = 'POI001' and date = %s and "
            "tolerance = 'moderate' and purpose = 'sight'",
            (TODAY,),
        ).fetchone()[0]
        assert windows and all(window["hours"][0] >= 21 for window in windows)
        # other dates and other places keep the rows of the full run
        untouched = conn.execute(
            "select count(*) from recommendations where generated_at = %s", (STARTED,)
        ).fetchone()[0]
        assert untouched == (2 * 3 + 1) * 3 * 8 - 3 * 3
