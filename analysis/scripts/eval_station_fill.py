"""Experiment B3: can subway ridership rescue the station places where 집계구 생활인구 fails
(transfer hubs like 신도림/구로/대림)?  July 2026, station-named places only.

Station estimate for hour H of day d = daily on+off total (OA-12914, 2026) x hourly share,
where the share comes from either
  month : CardSubwayTime 2026-07 (month-aggregated, all lines; no weekday/weekend split)
  y2025 : 서울교통공사 daily x hourly 2025 file (lines 1-8), averaged per day type
Ridership is a flow; live population is a stock, so hour H uses the mean of bins H-1 and H.
"""
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D, live_hourly  # noqa: E402
from eval_fill_gap_oa import oa_weights, read_oa, shape_metrics  # noqa: E402

def norm(s):
    return re.sub(r"\(.*?\)|역$", "", str(s)).strip()


def daytype(ts):
    return np.where(ts.dt.dayofweek == 6, "sun", np.where(ts.dt.dayofweek == 5, "sat", "wk"))


def station_estimates(ym=202607):
    daily = pd.concat([pd.read_csv(p, encoding="utf-8-sig", index_col=False) for p in (D / "subway").glob("day_15*.csv")])
    daily["st"] = daily.역명.map(norm)
    daily["d"] = pd.to_datetime(daily.사용일자.astype(str))
    daily = daily.drop_duplicates(["d", "노선명", "역명"]).groupby(["st", "d"])[["승차총승객수", "하차총승객수"]].sum().sum(axis=1).rename("tot")

    m = pd.read_csv(D / "subway/hourly_month_2026.csv")
    m = m[m.USE_MM == ym].sort_values("JOB_YMD").drop_duplicates(["SBWY_ROUT_LN_NM", "STTN"], keep="last")
    m["st"] = m.STTN.map(norm)
    hrs = {h: m[[f"HR_{h}_GET_ON_NOPE", f"HR_{h}_GET_OFF_NOPE"]].sum(axis=1) for h in range(24)}
    mh = pd.DataFrame(hrs).assign(st=m.st).groupby("st").sum()
    share_month = mh.div(mh.sum(axis=1), axis=0)

    y = pd.read_csv(D / "subway/day_hour_2025.csv", encoding="cp949", index_col=False)
    y["st"] = y.역명.map(norm)
    y["dt"] = daytype(pd.to_datetime(y.수송일자))
    bins = [c for c in y.columns if "시" in c and c not in ("수송일자",)]
    # columns: 06시이전, 06-07시간대, ..., 23-24시간대, 24시이후 -> hour index of bin start
    def bin_hour(c):
        if c.startswith("06시이전"): return 5
        if c.startswith("24시이후"): return 0
        return int(c[:2])
    yh = y.groupby(["st", "dt"])[bins].sum()
    yh.columns = [bin_hour(c) for c in yh.columns]
    yh = yh.T.groupby(level=0).sum().T.reindex(columns=range(24), fill_value=0)
    share_2025 = yh.div(yh.sum(axis=1), axis=0)
    return daily, share_month, share_2025


def build(poi_st, daily, share_month, share_2025, hours):
    out = []
    for poi, sts in poi_st.items():
        for H in hours:
            d = H.normalize()
            dt_ = "sun" if H.dayofweek == 6 else "sat" if H.dayofweek == 5 else "wk"
            e_m = e_y = 0.0
            ok_m = ok_y = False
            for st in sts:
                tot = daily.get((st, d))
                if tot is None:
                    continue
                if st in share_month.index:
                    e_m += tot * share_month.loc[st, [(H.hour - 1) % 24, H.hour]].mean(); ok_m = True
                if (st, dt_) in share_2025.index:
                    e_y += tot * share_2025.loc[(st, dt_), [(H.hour - 1) % 24, H.hour]].mean(); ok_y = True
            out.append((poi, H, e_m if ok_m else np.nan, e_y if ok_y else np.nan))
    return pd.DataFrame(out, columns=["poi", "dt", "est_month", "est_2025"])


def main():
    daily, share_month, share_2025 = station_estimates()
    names = pd.read_csv(D / "fill_gap_oa_vs_dong.csv", encoding="utf-8-sig", index_col=0)
    known = set(daily.index.get_level_values(0))
    poi_st = {}
    for poi, nm in names.AREA_NM.items():
        parts = [norm(p) for p in re.split(r"[·,]", nm) if p.strip().endswith("역")]
        parts = [p for p in parts if p in known]
        if parts:
            poi_st[poi] = parts
    print(f"station places matched: {len(poi_st)}  e.g. {list(poi_st.items())[:4]}")

    hours = pd.date_range("2026-07-01", "2026-07-31 23:00", freq="h")
    st_est = build(poi_st, daily, share_month, share_2025, hours)

    codes = set(pd.read_csv(zipfile.ZipFile(D / "lp_oa/oa_202607.zip").open("LOCAL_PEOPLE_20260701.csv"),
                            encoding="cp949", usecols=[3], dtype=str, index_col=False).iloc[:, 0])
    w_oa, _ = oa_weights(codes)
    w_oa = w_oa[w_oa.AREA_CD.isin(poi_st)]
    oa = read_oa(set(w_oa.TOT_OA_CD))
    e = w_oa.merge(oa, left_on="TOT_OA_CD", right_on="oa")
    e_oa = (e["pop"] * e.w).groupby([e.AREA_CD, e.dt]).sum().rename("est_oa").reset_index().rename(columns={"AREA_CD": "poi"})

    j = live_hourly().merge(st_est, on=["poi", "dt"]).merge(e_oa, on=["poi", "dt"])
    j = j[j.dt >= "2026-07-01"].dropna(subset=["live", "est_oa", "est_month"])
    # combined: each source scaled to its own mean, then averaged (shape blend, no fitted weights)
    g = j.groupby("poi")
    j["est_combo"] = 0.5 * j.est_oa / g.est_oa.transform("mean") + 0.5 * j.est_2025.fillna(j.est_month) / g.est_2025.transform("mean").fillna(g.est_month.transform("mean"))
    print(f"rows {len(j):,} places {j.poi.nunique()}")

    res = {c: shape_metrics(j.dropna(subset=[c]), c)["r_week"] for c in ["est_oa", "est_month", "est_2025", "est_combo"]}
    r = pd.DataFrame(res).join(names[["AREA_NM"]]).astype({c: float for c in res})
    print("\n== weekly-profile r, station places (July 2026) ==")
    print(r.median(numeric_only=True).round(2).to_string())
    print("share r>=0.8:", {c: f"{(r[c] >= .8).mean()*100:.0f}%" for c in res})
    print("\n== per place ==")
    print(r.sort_values("est_oa")[["AREA_NM", "est_oa", "est_month", "est_2025", "est_combo"]].round(2).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
