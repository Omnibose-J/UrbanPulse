"""Cell reasons, in the order the definition gives them."""

from datetime import date

from engine.flags import load
from engine.reco import build_row

DAY = date(2026, 10, 6)  # Tuesday


def test_reason_priority_and_rating():
    flags = load()
    place = _place("A1")
    hourly = _ready()
    hourly[10]["level"] = 3
    hourly[10]["a_all"] = 0.1
    row = build_row(place, DAY, "moderate", "sight", hourly, flags, "weekday")
    reasons = {cell["h"]: cell["reason"] for cell in row["hours"]}
    assert reasons[10] == "closed"
    assert all((cell["rating"] == 0) == (cell["reason"] != "fit") for cell in row["hours"])
    assert [cell["h"] for cell in row["hours"]] == list(range(9, 24))


def test_outside_hours_wins_over_too_busy_and_a2_act_is_null():
    flags = load()
    place = _place("A2")
    hourly = _ready()
    hourly[21]["level"] = 3
    row = build_row(place, DAY, "calm", "none", hourly, flags, "weekday")
    by_hour = {cell["h"]: cell for cell in row["hours"]}
    assert by_hour[21]["reason"] == "outside_hours"
    assert all(cell["act"] is None for cell in row["hours"])


def test_closed_weekday_is_fifteen_outside_hours():
    flags = load()
    place = _place("A2")
    place["open_hours"] = {"hours": {day: None for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}
    place["open_hours"]["hours"]["wed"] = "09:00-18:00"
    row = build_row(place, DAY, "moderate", "none", _ready(), flags, "weekday")
    assert row["state"] == "on"
    assert [cell["reason"] for cell in row["hours"]] == ["outside_hours"] * 15
    assert row["no_window"] is True
    assert row["windows"] == []


def _place(tier: str) -> dict:
    return {
        "id": "POI008",
        "tier": tier,
        "foreign_heavy": False,
        "serve_state": "on",
        "open_hours": None,
    }


def _ready() -> dict:
    return {
        hour: {"ready": True, "level": 1, "a_all": 1.0, "a_food": 1.0, "a_shop": 1.0} for hour in range(9, 24)
    }
