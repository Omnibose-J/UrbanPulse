"""Thresholds and monotone level_of."""

import random

import pandas as pd

from engine.levels import level_of, thresholds_for


def test_missing_level_is_infinity_and_three_levels_are_ready():
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2026-08-01", periods=4, freq="D"),
            "value": [10.0, 20.0, 40.0, 15.0],
            "level": [0, 1, 2, 1],
        }
    )
    t1, t2, t3, days, ready = thresholds_for(frame)
    assert (t1, t2, t3) == (15.0, 40.0, float("inf"))
    assert days == 4
    assert ready


def test_level_of_is_monotone_in_pop():
    rng = random.Random(0)
    for _ in range(50):
        cuts = sorted(rng.uniform(0, 100) for _ in range(3))
        pops = sorted(rng.uniform(0, 150) for _ in range(8))
        levels = [level_of(pop, *cuts) for pop in pops]
        assert levels == sorted(levels)
        assert levels[0] <= levels[-1]
