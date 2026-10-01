"""Which source a forecast hour is served from, before the live/seoul overlay."""

from engine.jobs.forecast import activity_for, served_pop, served_source


def test_horizon_within_the_gate_is_model_and_beyond_it_is_profile():
    passing = set(range(7))
    assert served_source(True, 3, passing) == "model"
    assert served_source(True, 7, passing) == "profile"
    assert served_pop(10.0, "profile", 0.5) == 10.0
    assert served_pop(10.0, "model", 0.0) == 10.0


def test_place_outside_the_index_stays_on_the_profile():
    assert served_source(False, 3, set(range(7))) == "profile"


def test_a2_activity_is_null():
    stored = (1.0, 0.5, 0.2)
    assert activity_for("A2", stored) == (None, None, None)
    assert activity_for("A1", stored) == stored
