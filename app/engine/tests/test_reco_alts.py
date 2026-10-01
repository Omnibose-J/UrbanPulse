"""Alternative dates and places."""

from datetime import date

from engine.reco import fill_alternatives


def test_alt_dates_keep_only_better_dates_and_at_most_two():
    origin = date(2026, 10, 1)
    rows = [
        _row("POI001", origin, 0.4, crowd=2),
        _row("POI001", date(2026, 10, 2), 0.9, crowd=1),
        _row("POI001", date(2026, 10, 3), 0.7, crowd=1),
        _row("POI001", date(2026, 10, 4), 0.5, crowd=1),
        _row("POI001", date(2026, 10, 5), 0.2, crowd=1),
    ]
    fill_alternatives(rows, rows, {}, {})
    assert [item["date"] for item in rows[0]["alt_dates"]] == ["2026-10-02", "2026-10-03"]


def test_no_window_lists_any_date_that_has_one():
    origin = date(2026, 10, 1)
    empty = _row("POI001", origin, None, crowd=None)
    other = _row("POI001", date(2026, 10, 2), 0.3, crowd=2)
    fill_alternatives([empty], [empty, other], {}, {})
    assert empty["alt_dates"] == [{"date": "2026-10-02", "hours": [12], "score": 0.3}]


def test_alt_places_respect_distance_crowd_and_a2():
    origin = date(2026, 10, 1)
    here = _row("POI001", origin, 0.5, crowd=2, tier="A1")
    near_quieter = _row("POI045", origin, 0.4, crowd=1, tier="A1")
    near_same = _row("POI046", origin, 0.4, crowd=2, tier="A1")
    far = _row("POI047", origin, 0.9, crowd=0, tier="A1")
    third = _row("POI048", origin, 0.2, crowd=0, tier="A1")
    fourth = _row("POI049", origin, 0.2, crowd=0, tier="A1")
    rows = [here, near_quieter, near_same, far, third, fourth]
    coords = {
        "POI001": (37.50, 127.00),
        "POI045": (37.50, 127.01),
        "POI046": (37.51, 127.00),
        "POI047": (37.50, 127.20),
        "POI048": (37.49, 127.00),
        "POI049": (37.48, 127.01),
    }
    similar = {"POI001": ["POI047", "POI045", "POI046", "POI048", "POI049"]}
    fill_alternatives(rows, rows, similar, coords)
    assert [item["place_id"] for item in here["alt_places"]] == ["POI045", "POI048", "POI049"]
    a2 = _row("POI008", origin, 0.5, crowd=2, tier="A2")
    fill_alternatives([a2], [a2, near_quieter], {"POI008": ["POI045"]}, coords)
    assert a2["alt_places"] == []


def _row(place_id, day, score, crowd, tier="A1"):
    windows = [] if score is None else [{"hours": [12], "score": score, "crowd": crowd}]
    return {
        "place_id": place_id,
        "date": day,
        "tolerance": "moderate",
        "purpose": "sight" if tier == "A1" else "none",
        "tier": tier,
        "state": "on",
        "windows": windows,
        "no_window": score is None,
        "alt_dates": [],
        "alt_places": [],
    }
