"""Tier B rel, open-hours shape, holiday ledger, and unscored rows."""

from datetime import date, datetime

import httpx
import pandas as pd
import psycopg
import pytest

from engine.jobs import sync_holidays
from engine.jobs.evaluate import _reco_rows
from engine.jobs.forecast import _write_tier_b_forecasts
from engine.jobs.load_places import _hours_for
from engine.parsers import KST
from engine.reco import open_hours_for
from engine.tests.tempdb import schema

WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def test_tier_b_forecast_stores_rel():
    started = datetime(2026, 10, 2, 5, 0, tzinfo=KST)
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                """
                insert into places (id, tier, name, serve_state)
                values ('STN001', 'B', 'One', 'experimental')
                """
            )
            conn.execute(
                """
                insert into tier_b_profile (place_id, day_type, hour, rel)
                values ('STN001', 'weekday', 12, 0.42)
                """
            )
            _write_tier_b_forecasts(conn, started, date(2026, 10, 2))
            conn.commit()
            stored = conn.execute(
                """
                select rel from forecast_hourly
                where place_id = 'STN001' and target_ts = %s
                """,
                (datetime(2026, 10, 2, 12, tzinfo=KST),),
            ).fetchone()[0]
    assert stored == pytest.approx(0.42)


def test_a_bad_open_hours_span_raises():
    from engine.reco import OpenHoursError

    hours = {day: "09:00-18:00" for day in WEEK}
    hours["mon"] = "9-18"
    spec = {"hours": hours, "source": "board", "checked": "2026-10-01"}
    with pytest.raises(OpenHoursError):
        _hours_for("POI001", "A2", "고궁·문화유산", {"POI001": spec})
    with pytest.raises(OpenHoursError):
        open_hours_for("A2", {"hours": {"fri": "9-18"}}, date(2026, 10, 2))


def test_sync_holidays_writes_a_ledger_row(monkeypatch):
    def fetched(_client, _key, year, month):
        if (year, month) != (2026, 10):
            return []
        return [{"date": date(2026, 10, 3), "name": "개천절", "is_holiday": "Y", "kind": "holiday"}]

    monkeypatch.setattr(sync_holidays, "_fetch_month", fetched)
    with schema() as dsn:
        monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
        monkeypatch.setenv("DATABASE_URL", dsn)
        monkeypatch.setenv("KASI_API_KEY", "dummy-kasi")
        code = sync_holidays.run(client=httpx.Client(), pause_s=0)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            rows = conn.execute(
                "select status from job_runs where job = 'sync_holidays'"
            ).fetchall()
    assert code == 0
    assert [row[0] for row in rows] == ["ok"]


def test_unscored_counts_rows_the_old_branches_dropped():
    logs = [
        {
            "place_id": "P",
            "purpose": "none",
            "hours": [{"h": 12, "reason": "outside_hours"}],
            "windows": [],
            "tolerance": "calm",
            "date": date(2026, 10, 2),
        },
        {
            "place_id": "P",
            "purpose": "sight",
            "hours": [{"h": 12, "reason": "fit"}],
            "windows": [],
            "tolerance": "calm",
            "date": date(2026, 10, 2),
        },
    ]
    live = pd.DataFrame(
        [
            {
                "place_id": "P",
                "hour": pd.Timestamp("2026-10-02 12:00", tz="Asia/Seoul"),
                "level": 1,
            }
        ]
    )
    commerce = pd.DataFrame(columns=["place_id", "hour"])
    _reco, _strip, unscored = _reco_rows(logs, {"P": "A2"}, live, commerce)
    assert unscored == 2
