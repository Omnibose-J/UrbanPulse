"""Bootstrap interval and the pass / borderline / fail rule from analysis/scripts/rejudge.py."""

from __future__ import annotations

import numpy as np

RNG = np.random.default_rng(0)
B = 1000


def reset_rng() -> None:
    global RNG
    RNG = np.random.default_rng(0)


def boot(groups: dict, stat) -> np.ndarray:
    keys = list(groups)
    samples = [stat([groups[key] for key in RNG.choice(keys, len(keys))]) for _ in range(B)]
    return np.percentile(samples, [2.5, 97.5])


def verdict(name: str, point: float, ci, bar: float, higher_is_better: bool = True, unit: str = "%") -> str:
    ok_point = point >= bar if higher_is_better else point <= bar
    ok_ci = (ci[0] >= bar) if higher_is_better else (ci[1] <= bar)
    if ok_point and ok_ci:
        return "PASS"
    if ok_point:
        return "BORDERLINE"
    return "FAIL"


def worse(left: str, right: str) -> str:
    rank = {"FAIL": 0, "BORDERLINE": 1, "PASS": 2}
    return left if rank[left] <= rank[right] else right


def state_for(result: str) -> str:
    return {"PASS": "on", "BORDERLINE": "reference", "FAIL": "off"}[result]
