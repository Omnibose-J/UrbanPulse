"""Windows follow the research candidate order, on rating-1 hours only."""

import random
from datetime import date

from engine.flags import load
from engine.reco import build_row, choose_windows, purposes_for

DAY = date(2026, 10, 1)


def test_windows_match_a_hand_worked_case():
    # Candidates in research order, then stable sort by score.
    # (10,) 1.0, (12,) 0.9, (10, 11) 0.6, (11, 12) 0.55, (11,) 0.2
    # Greedy keeps (10,), (12,), (11,). The 2-hour candidates overlap those picks.
    scores = {10: 1.0, 11: 0.2, 12: 0.9}
    assert choose_windows(scores, {10, 11, 12}) == [((10,), 1.0), ((12,), 0.9), ((11,), 0.2)]
    # Equal scores: the 1-hour candidate was inserted before the 2-hour one.
    tied = choose_windows({14: 0.2, 15: 0.2}, {14, 15})
    assert tied == [((14,), 0.2), ((15,), 0.2)]


def test_windows_use_only_fit_hours_and_match_in_window():
    flags = load()
    place = _place("A1")
    hourly = _ready()
    hourly[9]["a_all"] = 0.1
    hourly[18]["level"] = 3
    row = build_row(place, DAY, "moderate", "sight", hourly, flags, "weekday")
    fit = {cell["h"] for cell in row["hours"] if cell["rating"] == 1}
    covered = [hour for window in row["windows"] for hour in window["hours"]]
    assert set(covered) <= fit
    assert all(cell["reason"] != "closed" for cell in row["hours"] if cell["h"] in covered)
    in_window = {cell["h"] for cell in row["hours"] if cell["in_window"]}
    assert in_window == set(covered)
    assert len(row["windows"]) <= 3
    used = []
    for window in row["windows"]:
        assert set(window["hours"]).isdisjoint(used)
        used.extend(window["hours"])


def test_today_windows_skip_hours_already_over():
    flags = load()
    hourly = _ready()
    for hour in range(9, 24):
        hourly[hour]["a_all"] = 0.1
        hourly[hour]["level"] = 2
    hourly[9]["a_all"] = 1.0
    hourly[9]["level"] = 1
    hourly[18]["a_all"] = 1.0
    hourly[18]["level"] = 1
    late = build_row(_place("A1"), DAY, "moderate", "sight", hourly, flags, "weekday", now_hour=21)
    assert late["no_window"] is True
    assert all(not cell["in_window"] for cell in late["hours"])
    assert late["hours"][0]["rating"] == 1
    still = build_row(_place("A1"), DAY, "moderate", "sight", hourly, flags, "weekday", now_hour=18)
    assert 18 in {hour for window in still["windows"] for hour in window["hours"]}
    assert all(cell["h"] >= 18 or not cell["in_window"] for cell in still["hours"])


def test_busy_ok_never_marks_too_busy():
    flags = load()
    hourly = _ready()
    for hour in range(9, 24):
        hourly[hour]["level"] = 3
    row = build_row(_place("A1"), DAY, "busy_ok", "sight", hourly, flags, "weekday")
    assert all(cell["reason"] != "too_busy" for cell in row["hours"])


def test_invariants_hold_for_random_on_rows():
    flags = load()
    rng = random.Random(0)
    for _ in range(200):
        tier = "A1" if rng.randrange(2) == 0 else "A2"
        place = _place(tier)
        hourly = {
            hour: {
                "ready": True,
                "level": rng.randrange(4),
                "a_all": rng.random() + 0.2,
                "a_food": rng.random() + 0.2,
                "a_shop": rng.random() + 0.2,
            }
            for hour in range(9, 24)
        }
        for purpose in purposes_for(tier):
            for tolerance in ("calm", "moderate", "busy_ok"):
                row = build_row(place, DAY, tolerance, purpose, hourly, flags, "weekday")
                if row["state"] == "off":
                    assert row["hours"] is None
                    continue
                cells = row["hours"]
                assert [cell["h"] for cell in cells] == list(range(9, 24))
                assert all((cell["rating"] == 0) == (cell["reason"] != "fit") for cell in cells)
                in_window = {cell["h"] for cell in cells if cell["in_window"]}
                covered = {hour for window in row["windows"] for hour in window["hours"]}
                assert in_window == covered


def _place(tier: str) -> dict:
    return {
        "id": "POI001",
        "tier": tier,
        "foreign_heavy": False,
        "serve_state": "on",
        "open_hours": None,
    }


def _ready() -> dict:
    return {
        hour: {"ready": True, "level": 1, "a_all": 1.0, "a_food": 1.0, "a_shop": 1.0} for hour in range(9, 24)
    }
