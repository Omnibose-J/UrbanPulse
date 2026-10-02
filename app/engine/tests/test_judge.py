"""Verdicts and the bootstrap interval."""

import numpy as np

from engine.judge import boot, reset_rng, state_for, verdict, worse


def test_verdict_bands():
    assert verdict("high", 90, (86, 94), 85) == "PASS"
    assert verdict("point only", 90, (80, 94), 85) == "BORDERLINE"
    assert verdict("miss", 70, (60, 80), 85) == "FAIL"
    assert worse("PASS", "FAIL") == "FAIL"
    assert state_for("BORDERLINE") == "reference"


def test_bootstrap_is_deterministic_for_seed_zero():
    groups = {place: np.array([1.0, 0.0]) for place in ("a", "b", "c")}

    def stat(samples):
        return np.concatenate(samples).mean()

    reset_rng()
    first = boot(groups, stat)
    reset_rng()
    second = boot(groups, stat)
    assert np.allclose(first, second)

