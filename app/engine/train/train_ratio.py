"""Train ratio_v1. Port of `train()` in analysis/scripts/eval_ratio_live.py.

`python -m engine.train.train_ratio --holidays {research|table} --out <dir>`
"""

from __future__ import annotations

import argparse
import json
import subprocess
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from engine import settings
from engine.calendar_feats import block_starts, calendar, load_research_calendar
from engine.log import log
from engine.parsers import KST
from engine.ratio_model import FEATURES

HORIZONS = list(range(0, 8))
SAMPLE_N = 3_000_000
RESEARCH_FILE = Path(__file__).resolve().parent / "research_holidays.txt"


def _proxy_frame(root: Path) -> pd.DataFrame:
    folder = root / "analysis" / "data" / "place_oa"
    frames = [pd.read_parquet(path) for path in sorted(folder.glob("20*.parquet"))]
    data = pd.concat(frames, ignore_index=True)
    cover = pd.read_csv(folder / "cover.csv", index_col=0).iloc[:, 0]
    keep = cover[cover >= 0.8].index.astype(str)
    data = data[data["poi"].isin(keep)]
    pivoted = data.pivot(index="dt", columns="poi", values="est_oa").asfreq("h")
    return pivoted.sort_index()


def _table_calendar(conn) -> tuple[list, list, list]:
    with conn.cursor() as cur:
        cur.execute("select date, kind from holidays")
        rows = cur.fetchall()
    holidays = [row[0] for row in rows]
    seol = block_starts([row[0] for row in rows if row[1] == "seol"])
    chuseok = block_starts([row[0] for row in rows if row[1] == "chuseok"])
    return holidays, seol, chuseok


def train(pivoted: pd.DataFrame, holidays, seol_starts, chuseok_starts):
    times = pivoted.index
    places = pivoted.columns.to_numpy()
    values = pivoted.to_numpy(dtype=float)
    cal = calendar(pd.DatetimeIndex(times), holidays, seol_starts, chuseok_starts).reset_index(drop=True)
    pieces = []
    for horizon in HORIZONS:
        kmin = 1 if horizon < 7 else 2
        shifted = []
        for k in range(kmin, kmin + 3):
            week = np.roll(values, 7 * 24 * k, axis=0)
            week = week.copy()
            week[: 7 * 24 * k] = np.nan
            shifted.append(week)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            profile = np.nanmean(shifted, axis=0)
        target = np.log((values / profile).ravel())
        frame = pd.DataFrame(
            {
                "y": target,
                "poi_i": np.tile(np.arange(len(places)), len(times)),
                "t": np.repeat(np.arange(len(times)), len(places)),
                "h": horizon,
            }
        )
        pieces.append(frame.replace([np.inf, -np.inf], np.nan).dropna())
    stacked = pd.concat(pieces, ignore_index=True)
    stacked = stacked[stacked.t >= 21 * 24]
    stacked = stacked.sample(n=SAMPLE_N, random_state=0)
    features = cal.iloc[stacked.t.to_numpy()].reset_index(drop=True)
    features["poi_i"] = stacked.poi_i.to_numpy()
    features["h"] = stacked.h.to_numpy()
    features = features[FEATURES]
    model = HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.05, max_leaf_nodes=63, random_state=0
    )
    model.fit(features, stacked.y.to_numpy())
    return model, places, times


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write_model(
    out: Path,
    model,
    places,
    times,
    holidays,
    seol_starts,
    chuseok_starts,
    source: str,
    root: Path,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    meta = {
        "place_index": {str(place): index for index, place in enumerate(places)},
        "features": FEATURES,
        "horizons_trained": HORIZONS,
        "holidays_source": source,
        "trained_range": f"{pd_date(times.min())}..{pd_date(times.max())}",
        "n_rows": SAMPLE_N,
        "sklearn_version": sklearn.__version__,
        "git_commit": _git_commit(root),
        "created_at": datetime.now(KST).isoformat(),
        "holidays": [day.isoformat() for day in holidays],
        "block_starts": {
            "seol": [day.isoformat() for day in seol_starts],
            "chuseok": [day.isoformat() for day in chuseok_starts],
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def pd_date(value) -> str:
    return pd.Timestamp(value).date().isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.train.train_ratio")
    parser.add_argument("--holidays", choices=("research", "table"), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = settings.REPO_ROOT
    log("train_ratio", "start", holidays=args.holidays)
    pivoted = _proxy_frame(root)
    if args.holidays == "research":
        holidays, seol_starts, chuseok_starts = load_research_calendar(RESEARCH_FILE)
    else:
        settings.load_env()
        from engine import db

        env = settings.require(("DATABASE_URL",))
        with db.connect(env["DATABASE_URL"]) as conn:
            holidays, seol_starts, chuseok_starts = _table_calendar(conn)
    model, places, times = train(pivoted, holidays, seol_starts, chuseok_starts)
    write_model(
        Path(args.out),
        model,
        places,
        times,
        holidays,
        seol_starts,
        chuseok_starts,
        args.holidays,
        root,
    )
    log(
        "train_ratio",
        "done",
        places=len(places),
        trained_range=f"{pd_date(times.min())}..{pd_date(times.max())}",
        out=args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
