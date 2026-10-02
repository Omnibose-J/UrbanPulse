"""`evaluate` on a private schema: the three tables it writes, re-runs, and the warning bar."""

from datetime import date, datetime, timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb

from engine.jobs import evaluate
from engine.parsers import KST
from engine.tests.tempdb import schema

DAY = date(2026, 9, 30)  # a Wednesday, not a holiday
CATS = {
    "음식·음료": 0,
    "유통": 0,
    "패션·뷰티": 0,
    "여가·오락": 0,
    "생활서비스": 0,
    "의료·건강": 0,
    "교육": 0,
    "숙박": 0,
}


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=KST) + timedelta(
        hours=hour, minutes=minute
    )


def cell(hour: int, rating: int, reason: str) -> dict:
    return {"h": hour, "rating": rating, "in_window": False, "reason": reason, "crowd": 1, "act": None}


def seed(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "insert into places (id, tier, name, foreign_heavy, serve_state) values "
            "('POI001', 'A1', 'Street', false, 'on'), ('POI002', 'A2', 'Park', false, 'on')"
        )
        # what happened: POI001 10h 8 people level 1, 11h 20 people level 3; POI002 10h level 1
        cur.execute(
            "insert into live_obs (place_id, ts, pop_min, pop_max, level) values "
            "('POI001', %s, 8, 8, 1), ('POI001', %s, 20, 20, 3), ('POI002', %s, 5, 5, 1)",
            (at(DAY, 10, 30), at(DAY, 11, 30), at(DAY, 10)),
        )
        # payments: 10h 60 (lively against p90 100), 11h 30 (not lively)
        cur.execute(
            "insert into commerce_obs (place_id, ts, level, pay_cnt, cat_counts) values "
            "('POI001', %s, 1, 60, %s), ('POI001', %s, 1, 30, %s)",
            (at(DAY, 10, 10), Jsonb(CATS), at(DAY, 11, 10), Jsonb(CATS)),
        )
        # what was forecast one day ahead
        cur.execute(
            "insert into forecast_log (place_id, issued_date, target_ts, horizon_d, pred, baseline, "
            "model_version) values "
            "('POI001', %s, %s, 1, 10, 9, 'v'), ('POI001', %s, %s, 1, 20, 20, 'v')",
            (DAY - timedelta(days=1), at(DAY, 10), DAY - timedelta(days=1), at(DAY, 11)),
        )
        street = [cell(9, 0, "outside_hours"), cell(10, 1, "fit"), cell(11, 0, "closed"), cell(12, 1, "fit")]
        park = [cell(10, 1, "fit"), cell(21, 0, "outside_hours")]
        logs = [
            ("POI001", "moderate", "sight", [{"hours": [10]}], street, 100.0),
            ("POI001", "busy_ok", "sight", [{"hours": [10]}], street, 100.0),
            ("POI001", "moderate", "food", [{"hours": [15]}], [cell(15, 1, "fit")], 100.0),
            ("POI002", "moderate", "none", [{"hours": [10]}], park, None),
        ]
        cur.executemany(
            "insert into recommendation_log (place_id, issued_date, date, tolerance, purpose, state, "
            "windows, hours, p90, lively_min) "
            "values (%s, %s, %s, %s, %s, 'on', %s, %s, %s, 0.5)",
            [
                (p, DAY - timedelta(days=3), DAY, tol, pur, Jsonb(w), Jsonb(h), p90)
                for p, tol, pur, w, h, p90 in logs
            ],
        )
    conn.commit()


def run_evaluate(monkeypatch, dsn: str, day: date) -> dict:
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    monkeypatch.setenv("DATABASE_URL", dsn)
    assert evaluate.run(day) == 0
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        return conn.execute(
            "select status, detail from job_runs where job = 'evaluate' order by id desc limit 1"
        ).fetchone()


def test_one_day_is_scored_into_the_three_tables_and_a_rerun_replaces_it(monkeypatch):
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            seed(conn)
        status, detail = run_evaluate(monkeypatch, dsn, DAY)
        assert status == "ok"
        assert detail["warn_skipped"] == "fewer than 14 days"

        def tables():
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                forecast = conn.execute(
                    "select horizon_d, segment, wape_model, wape_baseline, n from eval_daily"
                ).fetchall()
                reco = conn.execute(
                    "select place_id, purpose, tolerance, n_hours, n_lively, n_crowd_ok, "
                    "chance_hours, chance_lively "
                    "from reco_eval_daily order by 1, 2, 3"
                ).fetchall()
                strip = conn.execute(
                    "select place_id, purpose, tolerance, n_ok, n_ok_lively, n_ok_crowd_ok, n_avoid, "
                    "n_avoid_unfit "
                    "from strip_eval_daily order by 1, 2, 3"
                ).fetchall()
            return forecast, reco, strip

        forecast, reco, strip = tables()
        # |10-8| + |20-20| over 28 for the model; |9-8| over 28 for the baseline
        assert len(forecast) == 1
        horizon, segment, model, baseline, n = forecast[0]
        assert (horizon, segment, n) == (1, "normal", 2)
        assert model == pytest.approx(2 / 28 * 100, rel=1e-5)
        assert baseline == pytest.approx(1 / 28 * 100, rel=1e-5)
        # the window hour 10 was lively and within tolerance; chance = the two scorable hours, one lively.
        # busy_ok has no crowd promise (null). The food row has no scorable hour and writes nothing.
        assert reco == [
            ("POI001", "sight", "busy_ok", 1, 1, None, 2, 1),
            ("POI001", "sight", "moderate", 1, 1, 1, 2, 1),
        ]
        # hour 12 has no actuals and hour 9 / 21 are outside hours: not counted. A2 has no lively column.
        assert strip == [
            ("POI001", "sight", "busy_ok", 1, 1, None, 1, 1),
            ("POI001", "sight", "moderate", 1, 1, 1, 1, 1),
            ("POI002", "none", "moderate", 1, None, 1, 0, 0),
        ]
        assert (
            detail["eval_daily"] == 1 and detail["reco_eval_daily"] == 2 and detail["strip_eval_daily"] == 3
        )

        run_evaluate(monkeypatch, dsn, DAY)
        assert tables() == (forecast, reco, strip)


def test_a_holiday_is_scored_in_its_own_segment(monkeypatch):
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            seed(conn)
            conn.execute("insert into holidays (date, name, kind) values (%s, 'test', 'holiday')", (DAY,))
            conn.commit()
        run_evaluate(monkeypatch, dsn, DAY)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            assert conn.execute("select segment from eval_daily").fetchall() == [("holiday",)]


def seed_month(conn, days: int, model_error: float) -> date:
    """`days` normal days, one hour each: actual 1000, baseline 6 % off, model `model_error` % off."""
    last = date(2026, 9, 18)
    with conn.cursor() as cur:
        cur.execute(
            "insert into places (id, tier, name, foreign_heavy, serve_state) values ('POI001', 'A1', "
            "'Street', false, 'on')"
        )
        for back in range(days):
            day = last - timedelta(days=back)
            cur.execute(
                "insert into live_obs (place_id, ts, pop_min, pop_max, level) values ('POI001', %s, "
                "1000, 1000, 1)",
                (at(day, 14),),
            )
            cur.execute(
                "insert into forecast_log (place_id, issued_date, target_ts, horizon_d, pred, "
                "baseline, model_version) "
                "values ('POI001', %s, %s, 1, %s, 1060, 'v')",
                (day - timedelta(days=1), at(day, 14), 1000 + model_error * 10),
            )
    conn.commit()
    return last


@pytest.mark.parametrize(
    ("days", "model_error", "expected"),
    [
        (14, 6.31, "warn"),  # 0.31 %p worse than the baseline over 14 days: warn
        (14, 6.29, "ok"),  # 0.29 %p worse: inside the bar
        (13, 9.0, "skipped"),  # much worse, but 13 days are not enough to say
    ],
)
def test_the_warning_bar_is_three_tenths_of_a_point_over_fourteen_days(
    monkeypatch, days, model_error, expected
):
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            last = seed_month(conn, days, model_error)
        status, detail = run_evaluate(monkeypatch, dsn, last)
        if expected == "warn":
            assert status == "warn"
            assert [entry["horizon_d"] for entry in detail["warn"]] == [1]
            assert detail["warn"][0]["model"] == pytest.approx(model_error, abs=1e-3)
            assert detail["warn"][0]["baseline"] == pytest.approx(6.0, abs=1e-3)
        elif expected == "ok":
            assert status == "ok" and "warn" not in detail and "warn_skipped" not in detail
        else:
            assert status == "ok" and detail["warn_skipped"] == "fewer than 14 days"


def test_a_date_with_nothing_logged_writes_nothing(monkeypatch):
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into places (id, tier, name, foreign_heavy, serve_state) values ('POI001', "
                "'A1', 'Street', false, 'on')"
            )
            conn.commit()
        status, detail = run_evaluate(monkeypatch, dsn, DAY)
        assert status == "ok"
        assert (detail["eval_daily"], detail["reco_eval_daily"], detail["strip_eval_daily"]) == (0, 0, 0)
