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
    assert thresholds_for(frame, rule="min")[:3] == (15.0, 40.0, float("inf"))
    t1, t2, t3, days, ready = thresholds_for(frame)
    assert (t1, t2, t3) == (15.0, 40.0, float("inf"))
    assert days == 4
    assert ready


def test_one_low_outlier_moves_min_but_not_split():
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2026-08-01", periods=9, freq="h"),
            "value": [10, 10, 30, 30, 50, 50, 12, 80, 80],
            "level": [0, 0, 1, 1, 2, 2, 3, 3, 3],
        }
    )
    assert thresholds_for(frame, rule="min")[2] == 12
    assert thresholds_for(frame)[2] == 80


def test_a_tie_keeps_the_lowest_candidate():
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2026-08-01", periods=4, freq="h"),
            "value": [5, 15, 5, 15],
            "level": [0, 0, 1, 1],
        }
    )
    assert thresholds_for(frame)[0] == 5


def test_empty_sides():
    high_only = pd.DataFrame(
        {"ts": pd.date_range("2026-08-01", periods=2, freq="D"), "value": [4.0, 8.0], "level": [2, 2]}
    )
    assert thresholds_for(high_only)[0] == 4.0
    no_top = pd.DataFrame(
        {"ts": pd.date_range("2026-08-01", periods=2, freq="D"), "value": [4.0, 8.0], "level": [0, 1]}
    )
    assert thresholds_for(no_top)[2] == float("inf")


def test_split_cuts_are_monotone():
    rng = random.Random(1)
    for _ in range(40):
        size = rng.randint(4, 30)
        frame = pd.DataFrame(
            {
                "ts": pd.date_range("2026-01-01", periods=size, freq="h"),
                "value": [rng.uniform(1, 100) for _ in range(size)],
                "level": [rng.randint(0, 3) for _ in range(size)],
            }
        )
        t1, t2, t3, _, _ = thresholds_for(frame)
        assert t1 <= t2 <= t3


def test_split_matches_a_direct_error_count():
    rng = random.Random(2)
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=80, freq="h"),
            "value": [rng.uniform(1, 100) for _ in range(80)],
            "level": [rng.randint(0, 3) for _ in range(80)],
        }
    )
    hi = frame.loc[frame["level"] >= 1, "value"]
    lo = frame.loc[frame["level"] < 1, "value"]
    best_value = None
    best_errors = None
    for candidate in sorted(set(hi).union(set(lo))):
        errors = int((hi < candidate).sum() + (lo >= candidate).sum())
        if best_errors is None or errors < best_errors:
            best_errors = errors
            best_value = float(candidate)
    assert thresholds_for(frame)[0] == best_value


def test_level_of_is_monotone_in_pop():
    rng = random.Random(0)
    for _ in range(50):
        cuts = sorted(rng.uniform(0, 100) for _ in range(3))
        pops = sorted(rng.uniform(0, 150) for _ in range(8))
        levels = [level_of(pop, *cuts) for pop in pops]
        assert levels == sorted(levels)
        assert levels[0] <= levels[-1]
