"""Profile level cuts."""

from engine.jobs.forecast import level_from_rel


def test_rel_cuts_at_half_and_nine_tenths():
    assert level_from_rel(0.49) == 0
    assert level_from_rel(0.5) == 1
    assert level_from_rel(0.89) == 1
    assert level_from_rel(0.9) == 2
