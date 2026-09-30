"""Out-of-sample re-check of the fill-gap findings on other months (rules frozen from July 2026).

Per month:
  all places     : weekly-profile r of 행정동 vs 집계구 area-weighted estimates
  station places : 집계구 only vs station only vs the frozen agreement rule
                   (use the station estimate when corr(집계구 est, station est) < AGREE_THR)
usage: python validate_months.py 202605 202606 [202607]
"""
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D, area_weights, live_hourly  # noqa: E402
from eval_fill_gap_oa import MIN_COVER, oa_weights, read_oa, shape_metrics  # noqa: E402
from eval_station_fill import build, norm, station_estimates  # noqa: E402

AGREE_THR = 0.2  # frozen from July


def summarize(label, s):
    s = s.astype(float).dropna()
    return f"{label:<22} median {s.median():.2f}  r>=0.8 {(s >= .8).mean():4.0%}  r<0.3 {(s < .3).mean():4.0%}  (n={len(s)})"


def run(ym):
    start = pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01")
    end = start + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23)
    z = zipfile.ZipFile(D / f"lp_oa/oa_{ym}.zip")
    codes = set(pd.read_csv(z.open(z.namelist()[0]), encoding="cp949", usecols=[3], dtype=str, index_col=False).iloc[:, 0])
    w_oa, cover = oa_weights(codes)
    ok = cover[cover >= MIN_COVER].index
    oa = read_oa(set(w_oa.TOT_OA_CD), ym)
    e = w_oa.merge(oa, left_on="TOT_OA_CD", right_on="oa")
    e_oa = (e["pop"] * e.w).groupby([e.AREA_CD, e.dt]).sum().rename("est_oa")

    w_d, _ = area_weights()
    lp = pd.read_parquet(D / "lp_dong.parquet")
    lp = lp[(lp.dt >= start) & (lp.dt <= end)]
    ed = w_d.merge(lp, on="dong")
    e_d = (ed["pop"] * ed.w).groupby([ed.AREA_CD, ed.dt]).sum().rename("est_dong")

    live = live_hourly()
    live = live[(live.dt >= start) & (live.dt <= end)]
    est = pd.concat([e_oa, e_d], axis=1).reset_index().rename(columns={"AREA_CD": "poi"})
    j = live.merge(est, on=["poi", "dt"]).dropna()
    j = j[j.poi.isin(ok)]
    j = j[j.groupby("poi").dt.transform("size") >= 24 * 10]  # May overlap starts 5/12
    print(f"\n######## {ym}: places {j.poi.nunique()}, hours {j.dt.nunique()} ########")
    print(summarize("all  행정동", shape_metrics(j, "est_dong").r_week))
    print(summarize("all  집계구", shape_metrics(j, "est_oa").r_week))

    daily, share_month, share_2025 = station_estimates(int(ym))
    names = w_d.drop_duplicates("AREA_CD").set_index("AREA_CD").AREA_NM
    known = set(daily.index.get_level_values(0))
    poi_st = {}
    for poi, nm in names.items():
        parts = [norm(p) for p in re.split(r"[·,]", nm) if p.strip().endswith("역")]
        parts = [p for p in parts if p in known]
        if parts and poi in set(j.poi):
            poi_st[poi] = parts
    st = build(poi_st, daily, share_month, share_2025, pd.date_range(start, end, freq="h"))
    js = j.merge(st, on=["poi", "dt"]).dropna(subset=["est_month"])
    js = js[js.est_month > 0]
    r_oa = shape_metrics(js, "est_oa").r_week.astype(float)
    r_st = shape_metrics(js, "est_month").r_week.astype(float)
    agree = shape_metrics(js.assign(live=js.est_month), "est_oa").r_week.astype(float)  # live-free
    rule = pd.Series(np.where(agree < AGREE_THR, r_st, r_oa), index=agree.index)
    print(summarize("station 집계구", r_oa))
    print(summarize("station 역승하차", r_st))
    print(summarize(f"station rule(<{AGREE_THR})", rule))
    switched = agree[agree < AGREE_THR].index
    t = pd.DataFrame({"name": names.reindex(switched), "agree": agree[switched], "r_oa": r_oa[switched], "r_st": r_st[switched]})
    print("switched to station:\n" + t.round(2).to_string())
    return pd.DataFrame({"ym": ym, "r_oa": r_oa, "r_st": r_st, "rule": rule, "agree": agree})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = pd.concat([run(ym) for ym in sys.argv[1:]])
    out.to_csv(D / "validate_months_station.csv", encoding="utf-8-sig")
