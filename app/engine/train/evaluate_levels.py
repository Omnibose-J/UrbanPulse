"""Agreement of the old and new level cuts with Seoul's own levels.

`python -m engine.train.evaluate_levels`
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from engine import db, settings
from engine.levels import level_of, thresholds_for
from engine.parsers import KST

TRAIN_START = datetime(2026, 6, 3, tzinfo=KST)
TRAIN_END = datetime(2026, 9, 1, tzinfo=KST)
TEST_START = datetime(2026, 9, 1, tzinfo=KST)
TEST_END = datetime(2026, 9, 30, tzinfo=KST)
TARGETS = {
    "min": (48.6, 51.3, 0.2, 21.5, 3.2),
    "split": (79.6, 9.0, 11.4, 2.6, 3.2),
}
TOLERANCE = 1.0


def _metrics(frame: pd.DataFrame, cuts: tuple[float, float, float]) -> np.ndarray | None:
    hours = pd.to_datetime(frame["ts"]).dt.tz_convert(KST).dt.hour
    sample = frame.loc[hours.between(9, 23)]
    if sample.empty:
        return None
    predicted = sample["value"].map(lambda value: level_of(float(value), *cuts)).to_numpy()
    actual = sample["level"].to_numpy()
    return np.array(
        [
            (predicted == actual).mean(),
            (predicted > actual).mean(),
            (predicted < actual).mean(),
            (predicted == 3).mean(),
            (actual == 3).mean(),
        ]
    )


def main() -> int:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    with db.connect(url) as conn:
        places = [
            row[0]
            for row in conn.execute("select id from places where serve_state = 'on' order by id").fetchall()
        ]
        raw = pd.DataFrame(
            conn.execute(
                """
                select place_id, ts, (pop_min + pop_max) / 2.0 as value, level
                from live_obs
                where ts >= %s and ts < %s
                """,
                (TRAIN_START, TEST_END),
            ).fetchall(),
            columns=["place_id", "ts", "value", "level"],
        )
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True).dt.tz_convert(KST)
    scored = {"min": [], "split": []}
    used = 0
    for place_id in places:
        part = raw.loc[raw["place_id"] == place_id]
        train = part.loc[part["ts"] < TRAIN_END]
        test = part.loc[part["ts"] >= TEST_START]
        if test.empty:
            continue
        used += 1
        for rule in ("min", "split"):
            cuts = thresholds_for(train, rule=rule)[:3]
            metrics = _metrics(test, cuts)
            if metrics is not None:
                scored[rule].append(metrics)
    print(f"places {used}")
    print(f"{'rule':<8} {'exact':>8} {'higher':>8} {'lower':>8} {'pred3':>8} {'actual3':>8} verdict")
    failed = False
    for rule, target in TARGETS.items():
        mean = np.vstack(scored[rule]).mean(axis=0) * 100
        misses = [abs(float(value) - goal) > TOLERANCE for value, goal in zip(mean, target, strict=True)]
        verdict = "FAIL" if any(misses) else "PASS"
        failed = failed or verdict == "FAIL"
        cells = " ".join(f"{float(value):8.1f}" for value in mean)
        print(f"{rule:<8} {cells} {verdict}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
