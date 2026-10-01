"""Place state transitions from the refresh rules."""

from engine.jobs.forecast import next_place_state


def test_transitions():
    assert next_place_state(False, True, 3, False, False) == ("A2", "preparing")
    assert next_place_state(False, True, 20, True, True) == ("A2", "on")
    assert next_place_state(True, True, 20, True, True) == ("A1", "on")
    assert next_place_state(True, False, 30, True, True) == ("A1", "off")
    assert next_place_state(True, True, 20, False, True) == ("A1", "preparing")
    assert next_place_state(False, True, 20, True, False) == ("A2", "preparing")
