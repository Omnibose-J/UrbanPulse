"""Measured activity replaces the profile only on an A1 hour that has commerce."""

from engine.lively import activity_update


def test_commerce_hour_is_measured_and_a_missing_hour_is_not():
    assert activity_update("A1", True, 10.0, 20.0) == (0.5, True)
    assert activity_update("A1", False, 10.0, 20.0) is None


def test_zero_p90_is_null_and_a2_is_never_actual():
    assert activity_update("A1", True, 10.0, 0.0) == (None, True)
    assert activity_update("A1", True, 10.0, None) == (None, True)
    assert activity_update("A2", True, 10.0, 20.0) is None
