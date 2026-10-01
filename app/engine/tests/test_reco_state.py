"""The five state rules, in order, and null computed columns on an off row."""

from datetime import date

from engine.flags import load
from engine.reco import build_row, purposes_for

DAY = date(2026, 10, 1)


def test_state_rules_in_order():
    flags = load()
    ready = _ready()
    preparing = _place("on")
    preparing["serve_state"] = "preparing"
    assert _reason(preparing, ready, flags, "weekday") == "preparing"
    thin = _ready()
    del thin[12]
    assert _reason(_place("on"), thin, flags, "weekday") == "preparing"
    assert _reason(_place("on"), _ready(), flags, "myeongjeol") == "myeongjeol"
    calm = build_row(_place("on"), DAY, "calm", "sight", _ready(), flags, "weekday")
    assert calm["state"] == "off" and calm["off_reason"] == "failed"
    moderate = build_row(_place("on"), DAY, "moderate", "sight", _ready(), flags, "weekday")
    assert moderate["state"] == "on"
    assert moderate["strip_mode"] == "windows_only"
    for key in ("windows", "no_window", "hours", "strip_mode", "alt_dates", "alt_places"):
        assert calm[key] is None


def test_myeongjeol_turns_off_all_nine_a1_combinations():
    flags = load()
    place = _place("on")
    seen = []
    for purpose in purposes_for("A1"):
        for tolerance in ("calm", "moderate", "busy_ok"):
            row = build_row(place, DAY, tolerance, purpose, _ready(), flags, "myeongjeol")
            seen.append((purpose, tolerance, row["state"], row["off_reason"]))
    assert len(seen) == 9
    assert all(state == "off" and reason == "myeongjeol" for _, _, state, reason in seen)


def _reason(place, hourly, flags, kind: str) -> str:
    row = build_row(place, DAY, "moderate", "sight", hourly, flags, kind)
    return row["off_reason"]


def _place(state: str) -> dict:
    return {
        "id": "POI001",
        "tier": "A1",
        "foreign_heavy": False,
        "serve_state": state,
        "open_hours": None,
    }


def _ready() -> dict:
    return {
        hour: {"ready": True, "level": 1, "a_all": 1.0, "a_food": 1.0, "a_shop": 1.0} for hour in range(9, 24)
    }
