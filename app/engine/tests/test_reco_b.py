"""Tier B recommendation rules."""

from datetime import date

from engine.flags import load
from engine.reco import build_row

DAY = date(2026, 10, 5)


def _place() -> dict:
    return {
        "id": "STN001",
        "tier": "B",
        "foreign_heavy": False,
        "serve_state": "experimental",
        "open_hours": None,
    }


def _hours(level: int) -> dict:
    return {
        hour: {"ready": True, "level": level, "a_all": None, "a_food": None, "a_shop": None}
        for hour in range(9, 24)
    }


def test_hour_23_is_outside_and_activity_is_absent():
    row = build_row(_place(), DAY, "moderate", "none", _hours(1), load(), "weekday")
    cells = {cell["h"]: cell for cell in row["hours"]}
    assert cells[23]["reason"] == "outside_hours"
    assert all(cell["act"] is None for cell in row["hours"])
    assert all(window["act"] is None for window in row["windows"])


def test_a_holiday_is_off_unverified():
    row = build_row(_place(), DAY, "moderate", "none", _hours(1), load(), "holiday")
    assert row["state"] == "off"
    assert row["off_reason"] == "unverified"


def test_a_station_today_skips_hours_already_over():
    row = build_row(_place(), DAY, "moderate", "none", _hours(1), load(), "weekday", now_hour=15)
    assert row["windows"]
    assert all(hour >= 15 for window in row["windows"] for hour in window["hours"])


def test_moderate_is_never_too_busy_when_levels_stop_at_two():
    row = build_row(_place(), DAY, "moderate", "none", _hours(2), load(), "weekday")
    assert all(cell["reason"] != "too_busy" for cell in row["hours"])
