"""Is there a 'lively but not crowded' hour at hot places, or are calm hours just closed hours?

Per place x weekend/holiday hour (09-23):
  crowd    L = live congestion level (0 여유 .. 3 붐빔)
  activity A = card payment count / that place's weekend p90 payment count
  sweet  : L <= 1 and A >= ACT   (open and lively, not crowded)
  dead   : L <= 1 and A <  ACT   (calm because little is going on)
Inputs: data/obs*.csv (crowd), data/cmrcl.csv (collect_cmrcl.py)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent.parent / "data"
LV = {"여유": 0, "보통": 1, "약간 붐빔": 2, "붐빔": 3}
ACT = 0.5
HOT = ["발달상권", "관광특구"]


def main():
    o = pd.concat([pd.read_csv(D / f, parse_dates=["ppltn_time"]) for f in ("obs_hist.csv", "obs.csv")])
    o["h"] = o.ppltn_time.dt.round("h")
    o = o.drop_duplicates(["poi", "h"])[["poi", "h", "lvl", "pmin", "pmax"]]
    o["L"] = o.lvl.map(LV)

    c = pd.read_csv(D / "cmrcl.csv", dtype={"cmrcl_time": str})
    c["h"] = pd.to_datetime(c.cmrcl_time, format="%Y%m%d %H%M").dt.round("h")
    c = c.drop_duplicates(["poi", "h"])
    c["pay"] = pd.to_numeric(c.pay_cnt, errors="coerce")

    cat = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0)[["AREA_NM", "CATEGORY"]]
    j = o.merge(c[["poi", "h", "pay", "cat_음식·음료", "cat_패션·뷰티", "cat_유통"]], on=["poi", "h"]).merge(cat, left_on="poi", right_index=True)
    j = j[j.h.dt.hour.between(9, 23)]
    j["A"] = j.pay / j.groupby("poi").pay.transform(lambda s: s.quantile(.9))
    j["d"], j["hr"] = j.h.dt.normalize(), j.h.dt.hour
    hot = j[j.CATEGORY.isin(HOT)].copy()
    print(f"hot places {hot.poi.nunique()}, weekend/holiday days {hot.d.nunique()}, place-hours {len(hot):,}")

    calm = hot[hot.L <= 1]
    print(f"\ncalm hours (여유/보통): {len(calm):,}  -> lively (A>={ACT}) {(calm.A >= ACT).mean():.0%}, dead {(calm.A < ACT).mean():.0%}")
    print("dead share of calm hours by hour:", (calm.assign(dead=calm.A < ACT).groupby("hr").dead.mean() * 100).round(0).astype(int).to_dict())

    rows, days = [], []
    for (p, d), x in hot.groupby(["poi", "d"]):
        if x.L.max() < 2 or len(x) < 10:
            continue
        sweet = x[(x.L <= 1) & (x.A >= ACT)].hr.values
        calm_any = x[x.L <= 1].hr.values
        days.append((len(sweet) > 0, len(calm_any) > 0))
        for hr in x[x.L >= 2].hr:
            rows.append((np.abs(sweet - hr).min() if len(sweet) else 99, np.abs(calm_any - hr).min() if len(calm_any) else 99))
    days, rows = np.array(days), np.array(rows)
    print(f"\nbusy place-days: {len(days)}; with any calm hour {days[:, 1].mean():.0%}; with a SWEET hour {days[:, 0].mean():.0%}")
    for k in (1, 2, 3):
        print(f"busy hour -> nearest calm within {k}h {np.mean(rows[:, 1] <= k):.0%} | nearest SWEET within {k}h {np.mean(rows[:, 0] <= k):.0%}")

    # does crowd track activity 1:1? people per payment by hour (low = shopping-heavy hours)
    hot["ppl"] = (hot.pmin + hot.pmax) / 2
    prof = hot.groupby("hr").agg(L=("L", "mean"), A=("A", "mean"), sweet=("A", lambda s: 0))
    prof["sweet"] = hot.assign(s=(hot.L <= 1) & (hot.A >= ACT)).groupby("hr").s.mean()
    prof["dead"] = hot.assign(s=(hot.L <= 1) & (hot.A < ACT)).groupby("hr").s.mean()
    print("\n== hot places, weekend/holiday profile by hour (mean) ==")
    print(prof.round(2).to_string())

    print("\n== per place: sweet-hour share and its typical hours ==")
    per = []
    for p, x in hot.groupby("poi"):
        s = x[(x.L <= 1) & (x.A >= ACT)]
        top = s.hr.value_counts().head(3).index.tolist()
        per.append((cat.loc[p, "AREA_NM"], round((x.L >= 2).mean(), 2), round(len(s) / len(x), 2), sorted(top)))
    print(pd.DataFrame(per, columns=["place", "busy_share", "sweet_share", "common_sweet_hours"]).sort_values("busy_share", ascending=False).head(15).to_string(index=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
