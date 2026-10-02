"""Serve-form WAPE of ratio_v1 on live hours 2026-08-01 .. 2026-09-29.

`python -m engine.train.evaluate_ratio --model <dir> --grid {research|floor}`
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.hourly import hourly_frame
from engine.log import log
from engine.ratio_model import load, load_calendar

TEST_START = pd.Timestamp("2026-08-01", tz="Asia/Seoul")
TEST_END = pd.Timestamp("2026-09-29 23:00", tz="Asia/Seoul")
HOLIDAYS = {
    date(2026, 8, 15),
    date(2026, 8, 17),
    date(2026, 9, 24),
    date(2026, 9, 25),
    date(2026, 9, 26),
}
TARGETS = {3: (21.6, 17.4), 7: (21.6, 18.2)}
TOLERANCE = 0.5
EQUIVALENCE_PATH = settings.REPO_ROOT / "data" / "ratio_equivalence.json"


def _live_wide(grid: str) -> pd.DataFrame:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("set time zone 'Asia/Seoul'")
            cur.execute(
                """
                select place_id, ts, (pop_min + pop_max) / 2.0, level
                from live_obs
                where ts >= '2026-07-01 00:00:00+09' and ts < '2026-09-30 00:00:00+09'
                """
            )
            frame = pd.DataFrame(cur.fetchall(), columns=["place_id", "ts", "value", "level"])
    hourly = hourly_frame(frame, grid)
    wide = hourly.pivot(index="hour", columns="place_id", values="value").asfreq("h")
    wide.index = pd.DatetimeIndex(wide.index)
    return wide


def _wape(pred: pd.Series, live: pd.Series) -> float:
    return float((pred - live).abs().sum() / live.sum() * 100)


def evaluate(model_dir: Path, grid: str) -> tuple[list[dict], bool]:
    model = load(model_dir)
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    with db.connect(env["DATABASE_URL"]) as conn:
        holidays, seol_starts, chuseok_starts = load_calendar(conn)
    wide = _live_wide(grid)
    places = [place for place in wide.columns if place in model.place_index]
    wide = wide[places]
    rows: list[dict] = []
    missed = False
    for horizon in range(0, 8):
        kmin = 1 if horizon < 7 else 2
        weeks = [wide.shift(7 * 24 * k) for k in range(kmin, kmin + 3)]
        profile = pd.concat(weeks).groupby(level=0).mean()
        last = weeks[0]
        targets = wide.index[(wide.index >= TEST_START) & (wide.index <= TEST_END)]
        records = []
        for place in places:
            frame = pd.DataFrame(
                {
                    "live": wide.loc[targets, place],
                    "prof": profile.loc[targets, place],
                    "last": last.loc[targets, place],
                }
            ).dropna()
            if frame.empty:
                continue
            ratio = model.ratio(place, frame.index, horizon, holidays, seol_starts, chuseok_starts)
            frame["model"] = frame["prof"].to_numpy() * np.exp(ratio)
            frame["place"] = place
            records.append(frame)
        if not records:
            continue
        scored = pd.concat(records)
        scored["day"] = scored.index.tz_convert("Asia/Seoul").date
        for segment, mask in (("holiday", scored.day.isin(HOLIDAYS)), ("normal", ~scored.day.isin(HOLIDAYS))):
            part = scored[mask]
            if part.empty:
                continue
            baseline = _wape(part["prof"], part["live"])
            learned = _wape(part["model"], part["live"])
            rows.append(
                {
                    "horizon": horizon,
                    "segment": segment,
                    "baseline": round(baseline, 4),
                    "model": round(learned, 4),
                    "n": int(len(part)),
                }
            )
    if grid == "research":
        for horizon, (base_target, model_target) in TARGETS.items():
            found = next(
                (row for row in rows if row["horizon"] == horizon and row["segment"] == "holiday"),
                None,
            )
            if found is None:
                missed = True
                continue
            baseline_off = abs(found["baseline"] - base_target) > TOLERANCE
            model_off = abs(found["model"] - model_target) > TOLERANCE
            if baseline_off or model_off:
                missed = True
    return rows, missed


def _passes(rows: list[dict]) -> list[int]:
    by_h: dict[int, dict[str, float]] = {}
    for row in rows:
        by_h.setdefault(row["horizon"], {})[row["segment"]] = row
    passing = []
    for horizon, parts in sorted(by_h.items()):
        holiday = parts.get("holiday")
        normal = parts.get("normal")
        if not holiday or not normal or holiday["baseline"] <= 0:
            continue
        relative = holiday["model"] <= holiday["baseline"] * 0.9
        not_worse = normal["model"] <= normal["baseline"] + 0.3
        if relative and not_worse:
            passing.append(horizon)
    return passing


def _register(model_dir: Path, served: list[dict], passing: list[int]) -> None:
    equivalence = []
    if EQUIVALENCE_PATH.exists():
        equivalence = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("update model_registry set active = false where name = 'ratio_v1' and active")
            cur.execute(
                """
                insert into model_registry
                  (name, version, trained_range, horizons, metrics, artifact_uri, active)
                values ('ratio_v1', %s, %s, %s, %s, 'models/ratio_v1', %s)
                """,
                (
                    meta["created_at"],
                    meta["trained_range"],
                    passing,
                    Jsonb({"equivalence": equivalence, "served": served}),
                    bool(passing),
                ),
            )
        conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.train.evaluate_ratio")
    parser.add_argument("--model", required=True)
    parser.add_argument("--grid", choices=("research", "floor"), required=True)
    args = parser.parse_args(argv)
    rows, missed = evaluate(Path(args.model), args.grid)
    for row in rows:
        print(
            f"h={row['horizon']} {row['segment']} baseline={row['baseline']:.1f} "
            f"model={row['model']:.1f} n={row['n']}"
        )
    if args.grid == "research":
        EQUIVALENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EQUIVALENCE_PATH.write_text(json.dumps(rows), encoding="utf-8")
        log("evaluate_ratio", "equivalence", missed=missed)
        return 1 if missed else 0
    passing = _passes(rows)
    _register(Path(args.model), rows, passing)
    log("evaluate_ratio", "served", passing=passing, active=bool(passing))
    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())
