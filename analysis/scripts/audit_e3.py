"""Reliability / validity audit for the final recommendation config (rows from exp_e3c_calm.py).

  - tautology check: 'busy_ok' tolerance allows every level, so its crowd_ok is 100% by construction;
    report crowd_ok with and without it
  - chance baseline: share of 09-23h that are actually lively (what a random pick would get), and lift
  - place-level bootstrap 95% CI for lively_ok and crowd_ok (hours inside a place are correlated)
  - month stability (Aug vs Sep) and per-place spread (how many places fall below the bar)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402

RNG = np.random.default_rng(0)


def ci(df, col, B=1000):
    places = df.poi.unique()
    g = {p: x[col].values for p, x in df.groupby("poi")}
    vals = []
    for _ in range(B):
        s = RNG.choice(places, len(places), replace=True)
        v = np.concatenate([g[p] for p in s])
        vals.append(v.mean() * 100)
    return np.percentile(vals, [2.5, 97.5])


def main():
    r = pd.read_csv(D / "e3c_rows.csv")
    base = pd.read_csv(D / "e3c_base.csv")
    f = r[((r.tol != "calm") & (r.rule == "final")) | ((r.tol == "calm") & (r.rule == "c0"))]
    print(f"final-config rows: {len(f):,} hours, places {f.poi.nunique()}, days {f.day.nunique()}")

    print("\n== crowd_ok: with vs without the tautological 'busy_ok' tolerance ==")
    for p, g in f.groupby("purpose"):
        print(f"{p:>5}: all tolerances {g.crowd_ok.mean() * 100:.1f}%  |  calm+lively only {g[g.tol != 'busy_ok'].crowd_ok.mean() * 100:.1f}%")

    print("\n== lively_ok vs chance (share of 09-23h actually lively) ==")
    for p, g in f.groupby("purpose"):
        b = base[base.purpose == p].base_rate.mean() * 100
        lo, hi = ci(g, "lively_ok")
        print(f"{p:>5}: recommended {g.lively_ok.mean() * 100:.1f}% [95% CI {lo:.1f}, {hi:.1f}]  chance {b:.1f}%  lift x{g.lively_ok.mean() * 100 / b:.2f}")

    print("\n== crowd_ok (excluding busy_ok) with place-level 95% CI ==")
    for p, g in f[f.tol != "busy_ok"].groupby("purpose"):
        lo, hi = ci(g, "crowd_ok")
        print(f"{p:>5}: {g.crowd_ok.mean() * 100:.1f}% [{lo:.1f}, {hi:.1f}]")
    for tol in ("calm", "lively"):
        g = f[f.tol == tol]
        lo, hi = ci(g, "crowd_ok")
        print(f"  tol={tol}: {g.crowd_ok.mean() * 100:.1f}% [{lo:.1f}, {hi:.1f}]")

    print("\n== month stability (lively_ok / crowd_ok excl. busy_ok) ==")
    t = f.groupby(["purpose", "month"]).agg(lively=("lively_ok", "mean"))
    t["crowd"] = f[f.tol != "busy_ok"].groupby(["purpose", "month"]).crowd_ok.mean()
    print((t * 100).round(1).unstack("month").to_string())

    print("\n== per-place spread (lively_ok) ==")
    pp = f.groupby(["purpose", "poi"]).lively_ok.mean() * 100
    for p, s in pp.groupby(level=0):
        print(f"{p:>5}: places {len(s)}, median {s.median():.0f}%, below 85%: {(s < 85).mean() * 100:.0f}%, below 70%: {(s < 70).mean() * 100:.0f}%")
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    worst = pp.xs("food").nsmallest(5)
    print("worst food places:", {names.get(k, k): round(v) for k, v in worst.items()})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
