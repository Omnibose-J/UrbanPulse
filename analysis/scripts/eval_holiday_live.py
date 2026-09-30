"""Check the multi-year place model against REAL live population (not the 생활인구 proxy)
on 2026 public holidays inside the live window (5/12 ~ 7/31).

The model lives in proxy units, live data in its own units (scale differs by place), so we
transfer the model's predicted deviation instead of its level:
  live_prof  : mean live at T-7k days (k >= kmin, up to 3 available weeks)   <- baseline
  model      : live_prof x (gbm / prof3_proxy)                                <- baseline + model's holiday shift
  last_wk    : live at T-7*kmin days
kmin = 1 if h < 7 else 2 (only data known at issue time).
Inputs: data/place_pred_2026.parquet (eval_days_ahead.py place), live via eval_fill_gap.live_hourly
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D, live_hourly  # noqa: E402

HOLS = {"2026-05-24": "부처님오신날(일)", "2026-05-25": "대체공휴일(월)", "2026-06-03": "지방선거(수)", "2026-06-06": "현충일(토)"}


def main():
    p = pd.read_parquet(D / "place_pred_2026.parquet")
    p = p[p["T"] >= "2026-05-12"]
    live = live_hourly().set_index(["poi", "dt"]).live
    look = lambda poi, t: live.reindex(pd.MultiIndex.from_arrays([poi, t])).values

    p["live"] = look(p.poi, p["T"])
    kmin = np.where(p.h < 7, 1, 2)
    wk = np.stack([look(p.poi, p["T"] - pd.to_timedelta(7 * (kmin + i), unit="D")) for i in range(3)])
    p["live_last"] = wk[0]
    p["live_prof"] = np.nanmean(wk, axis=0)
    p["model"] = p.live_prof * np.clip(p.gbm / p.prof3, 0.3, 3)
    p = p.dropna(subset=["live", "live_prof", "model"])
    p["day"] = p["T"].dt.strftime("%Y-%m-%d")
    p["hol"] = p.day.isin(HOLS)
    print(f"places {p.poi.nunique()}, target range {p['T'].min()} ~ {p['T'].max()}")

    cols = ["live_last", "live_prof", "model"]
    wape = lambda g: pd.Series({c: np.abs(g[c] - g.live).sum() / g.live.sum() * 100 for c in cols} | {"n": len(g)})
    for name, sub in [("holidays (all 4)", p[p.hol]), ("normal days", p[~p.hol])]:
        print(f"\n== {name}: WAPE % vs LIVE population, by horizon (days) ==")
        print(sub.groupby("h").apply(wape, include_groups=False).round(1).to_string())
    print("\n== per holiday (h=3) ==")
    g3 = p[p.hol & (p.h == 3)]
    t = g3.groupby("day").apply(wape, include_groups=False).round(1)
    t.index = [f"{d} {HOLS[d]}" for d in t.index]
    print(t.to_string())
    print("\n== service hours 10-22 only, h=3 ==")
    s = p[(p.h == 3) & p["T"].dt.hour.between(10, 22)]
    print(pd.DataFrame({"holidays": wape(s[s.hol]), "normal": wape(s[~s.hol])}).round(1).to_string())

    # direction check: on holidays, does the model move the baseline the right way?
    h = p[p.hol & (p.h == 3)]
    true_dir = np.sign(h.live - h.live_prof)
    pred_dir = np.sign(h.model - h.live_prof)
    big = (h.live / h.live_prof - 1).abs() > 0.2
    print(f"\nholiday hours where live deviates >20% from baseline: {big.mean():.0%}; model gets the direction right on {(true_dir[big] == pred_dir[big]).mean():.0%} of them")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
