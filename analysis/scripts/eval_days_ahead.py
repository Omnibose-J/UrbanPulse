"""Experiment A: does multi-year history make 1-7 day-ahead hourly population forecasts
better than short-history baselines (what Google 'popular times' / a 3-week average gives)?

Data : data/lp_dong.parquet (행정동 hourly 생활인구, 2023-01 ~ 2026-07)
Issue: 00:00 of day(T) - h days, i.e. data known up to the previous hour.
Train: targets in 2023-2025; Test: targets 2026-01-01 ~ 2026-07-31 (contains 설 2026).
Holiday calendar below is hand-entered (public holidays incl. substitute/temporary ones).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

D = Path(__file__).resolve().parent.parent / "data"
HORIZONS = [1, 3, 7]

HOLIDAYS = pd.to_datetime("""
2023-01-01 2023-01-21 2023-01-22 2023-01-23 2023-01-24 2023-03-01 2023-05-05 2023-05-27 2023-05-29 2023-06-06
2023-08-15 2023-09-28 2023-09-29 2023-09-30 2023-10-02 2023-10-03 2023-10-09 2023-12-25
2024-01-01 2024-02-09 2024-02-10 2024-02-11 2024-02-12 2024-03-01 2024-04-10 2024-05-05 2024-05-06 2024-05-15
2024-06-06 2024-08-15 2024-09-16 2024-09-17 2024-09-18 2024-10-01 2024-10-03 2024-10-09 2024-12-25
2025-01-01 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-03-01 2025-03-03 2025-05-05 2025-05-06 2025-06-03
2025-06-06 2025-08-15 2025-10-03 2025-10-05 2025-10-06 2025-10-07 2025-10-08 2025-10-09 2025-12-25
2026-01-01 2026-02-16 2026-02-17 2026-02-18 2026-03-01 2026-03-02 2026-05-05 2026-05-24 2026-05-25 2026-06-03
2026-06-06 2026-08-15 2026-08-17 2026-09-24 2026-09-25 2026-09-26
""".split())
# first day of each 설/추석 block, for aligning "same position in last year's holiday"
BIG = {"seol": pd.to_datetime(["2023-01-21", "2024-02-09", "2025-01-27", "2026-02-16"]),
       "chuseok": pd.to_datetime(["2023-09-28", "2024-09-16", "2025-10-03", "2026-09-24"])}
WIN = range(-3, 7)  # days around the block start treated as holiday-affected


def load(unit):
    """long frame (dt, dong, pop); 'dong' is the unit id (행정동 code or place code)."""
    if unit == "place":  # 집계구 area-weighted place estimates from build_place_oa.py
        lp = pd.concat(pd.read_parquet(p) for p in sorted((D / "place_oa").glob("20*.parquet")))
        cover = pd.read_csv(D / "place_oa/cover.csv", index_col=0).iloc[:, 0]
        lp = lp[lp.poi.isin(cover[cover >= 0.8].index)]
        return lp.rename(columns={"poi": "dong", "est_oa": "pop"})
    return pd.read_parquet(D / "lp_dong.parquet")


def main(unit="dong"):
    lp = load(unit)
    P = lp.pivot(index="dt", columns="dong", values="pop").asfreq("h")
    times, dongs, X = P.index, P.columns.values, P.values  # X[t, dong]
    t0 = times[0]
    idx = lambda ts: ((ts - t0) // pd.Timedelta(hours=1)).astype(int)

    day = times.normalize()
    hol = day.isin(HOLIDAYS)
    offday = hol | (times.dayofweek >= 5)
    # big-holiday alignment: for each target hour, the hour at the same offset in last year's block
    big_kind = np.full(len(times), "", dtype=object)
    aligned = np.full(len(times), -1)
    for kind, starts in BIG.items():
        for i, s in enumerate(starts[1:], 1):
            for o in WIN:
                m = day == s + pd.Timedelta(days=o)
                big_kind[m] = kind
                src = times[m] - (s - starts[i - 1])
                aligned[m] = np.where(src >= t0, idx(src), -1)
    ly364 = np.arange(len(times)) - 364 * 24
    aligned = np.where(aligned >= 0, aligned, ly364)

    def get(ti):
        out = np.full((len(ti), X.shape[1]), np.nan, dtype="float32")
        ok = (ti >= 0) & (ti < len(times))
        out[ok] = X[ti[ok]]
        return out

    target_i = np.arange(len(times))
    rows = []
    for h in HORIZONS:
        kmin = 1 if h < 7 else 2
        weeks = [get(target_i - 7 * 24 * k) for k in range(kmin, kmin + 4)]
        prof3 = np.nanmean(weeks[:3], axis=0)          # 3-week average (short-history baseline)
        last_wk = weeks[0]
        # recent level: mean of the last 7 days before issue vs their own values a year earlier
        issue_i = idx(day - pd.Timedelta(days=h))
        recent = np.nanmean([get(issue_i - 24 * d) for d in range(1, 8)], axis=0)
        recent_ly = np.nanmean([get(issue_i - 24 * d - 364 * 24) for d in range(1, 8)], axis=0)
        f = {
            "h": np.full(X.shape, h), "hour": np.repeat(times.hour.values[:, None], X.shape[1], 1),
            "dow": np.repeat(times.dayofweek.values[:, None], X.shape[1], 1),
            "month": np.repeat(times.month.values[:, None], X.shape[1], 1),
            "hol": np.repeat(hol[:, None], X.shape[1], 1), "off": np.repeat(offday[:, None], X.shape[1], 1),
            "big": np.repeat(pd.Series(big_kind).map({"": 0, "seol": 1, "chuseok": 2}).values[:, None], X.shape[1], 1),
            "dong_i": np.repeat(np.arange(X.shape[1])[None, :], len(times), 0),
            "prof3": prof3, "last_wk": last_wk, "ly_aligned": get(aligned),
            "trend": recent / recent_ly, "act": X,
        }
        df = pd.DataFrame({k: v.ravel() for k, v in f.items()})
        df["T"] = np.repeat(times.values, X.shape[1])
        rows.append(df.dropna(subset=["act", "prof3", "last_wk"]))
    df = pd.concat(rows, ignore_index=True)
    df["ly_scaled"] = df.ly_aligned * df.trend.clip(0.7, 1.4)

    tr = df[(df["T"] >= "2024-01-15") & (df["T"] < "2026-01-01")]
    te = df[df["T"] >= "2026-01-01"].copy()
    tr = tr.sample(n=min(3_000_000, len(tr)), random_state=0)
    feats = ["dong_i", "h", "hour", "dow", "month", "hol", "off", "big", "prof3", "last_wk", "ly_aligned", "trend"]
    m = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=63,
                                      categorical_features=[7], random_state=0)
    m.fit(tr[feats], np.log1p(tr.act))
    te["gbm"] = np.expm1(m.predict(te[feats]))
    if unit == "place":  # kept for the live-truth check (eval_holiday_live.py)
        te.assign(poi=dongs[te.dong_i.astype(int)])[["poi", "T", "h", "act", "prof3", "last_wk", "gbm"]] \
            .to_parquet(D / "place_pred_2026.parquet", index=False)

    models = ["last_wk", "prof3", "ly_scaled", "gbm"]
    te["bigwin"] = te.big > 0
    te["plainhol"] = te.hol.astype(bool) & ~te.bigwin

    def wape(g):
        return pd.Series({m_: np.abs(g[m_] - g.act).sum() / g.act.sum() * 100 for m_ in models} | {"n": len(g)})

    print(f"train rows {len(tr):,}  test rows {len(te):,}  dongs {len(dongs)}")
    for name, sub in [("all test (2026-01~07)", te), ("normal days", te[~te.bigwin & ~te.hol.astype(bool)]),
                      ("설 window (-3..+6d)", te[te.bigwin]), ("other public holidays", te[te.plainhol])]:
        print(f"\n== {name}: WAPE % by horizon (days) ==")
        print(sub.groupby("h").apply(wape, include_groups=False).round(1).to_string())

    # peak-hour ranking: does the model get the busiest 3 hours of each dong-day right?
    g = te[te.h == 3].copy()
    g["d"] = g["T"].dt.normalize()
    def top3_hit(x, col):
        a = set(x.nlargest(3, "act").hour); p = set(x.nlargest(3, col).hour)
        return len(a & p) / 3
    print("\n== busiest-3-hours overlap per dong-day (h=3d) ==")
    samp = g[g.dong_i.isin(np.random.default_rng(0).choice(len(dongs), 60, replace=False))]
    for col in models:
        print(f"{col:>10}: {samp.groupby(['dong_i', 'd']).apply(top3_hit, col, include_groups=False).mean()*100:.1f}%")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:2])
