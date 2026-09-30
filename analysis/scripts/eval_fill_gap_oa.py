"""Experiment B2: does the finer 집계구 unit fix the 행정동 mismatch (e.g. station areas
inside residential dongs)? Same places, same period (2026-07), both units side by side.

집계구 boundary = 2016 SGIS file (cubensys/Korea_District); ~82% of codes match the
생활인구 file, so a place is scored only if matched tracts cover >= 80% of its area.
"""
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D, area_weights, live_hourly  # noqa: E402

MIN_COVER = 0.8


def oa_weights(codes_in_data):
    poi = gpd.read_file(D / "poi/서울시 주요 121장소 영역/서울시 주요 121장소 영역.shp").to_crs(5179)
    oa = gpd.read_file(D / "poi/oa2016.geojson").to_crs(5179)
    oa = oa[oa.TOT_OA_CD.isin(codes_in_data)]
    oa["oa_area"] = oa.area
    ov = gpd.overlay(poi[["AREA_CD", "geometry"]], oa[["TOT_OA_CD", "oa_area", "geometry"]], how="intersection")
    ov["w"] = ov.area / ov.oa_area
    cover = (ov.assign(a=ov.area).groupby("AREA_CD").a.sum() / poi.set_index("AREA_CD").area).fillna(0)
    return ov[["AREA_CD", "TOT_OA_CD", "w"]], cover


def read_oa(codes, ym="202607"):
    z = zipfile.ZipFile(D / f"lp_oa/oa_{ym}.zip")  # one CSV per day
    parts = []
    for name in z.namelist():
        ch = pd.read_csv(z.open(name), encoding="cp949", usecols=[0, 1, 3, 4], dtype=str, index_col=False)
        ch.columns = ["day", "hour", "oa", "pop"]
        parts.append(ch[ch.oa.isin(codes)])
    df = pd.concat(parts)
    df["pop"] = pd.to_numeric(df["pop"].str.replace("*", "", regex=False), errors="coerce")
    df["dt"] = pd.to_datetime(df.day, format="%Y%m%d") + pd.to_timedelta(df.hour.astype(int), unit="h")
    return df[["dt", "oa", "pop"]]


def shape_metrics(j, col):
    out = {}
    for poi, g in j.groupby("poi"):
        g = g.assign(d=g.dt.dt.normalize(), hour=g.dt.dt.hour, how=g.dt.dt.dayofweek * 24 + g.dt.dt.hour)
        pl, pe = g.groupby("how").live.mean(), g.groupby("how")[col].mean()
        hits = [len(set(x.nlargest(3, "live").hour) & set(x.nlargest(3, col).hour)) / 3
                for _, x in g.groupby("d") if len(x) >= 20]
        out[poi] = {"r_hourly": g.live.corr(g[col]), "r_week": pl.corr(pe), "top3": np.mean(hits),
                    "ratio": g.live.mean() / g[col].mean()}
    return pd.DataFrame(out).T


def main():
    z = zipfile.ZipFile(D / "lp_oa/oa_202607.zip")
    head = pd.read_csv(z.open(z.namelist()[0]), encoding="cp949", usecols=[3], dtype=str, index_col=False, nrows=40000)
    codes_in_data = set(head.iloc[:, 0])
    w_oa, cover = oa_weights(codes_in_data)
    ok = cover[cover >= MIN_COVER].index
    print(f"places with >= {MIN_COVER:.0%} tract coverage: {len(ok)} / {len(cover)}")

    oa = read_oa(set(w_oa.TOT_OA_CD))
    e_oa = w_oa.merge(oa, left_on="TOT_OA_CD", right_on="oa")
    e_oa = (e_oa["pop"] * e_oa.w).groupby([e_oa.AREA_CD, e_oa.dt]).sum().rename("est_oa")

    w_d, _ = area_weights()
    lp = pd.read_parquet(D / "lp_dong.parquet")
    lp = lp[lp.dt >= "2026-07-01"]
    e_d = w_d.merge(lp, on="dong")
    e_d = (e_d["pop"] * e_d.w).groupby([e_d.AREA_CD, e_d.dt]).sum().rename("est_dong")

    est = pd.concat([e_oa, e_d], axis=1).reset_index().rename(columns={"AREA_CD": "poi"})
    j = live_hourly().merge(est, on=["poi", "dt"]).dropna()
    j = j[j.poi.isin(ok) & (j.dt >= "2026-07-01")]
    print(f"rows {len(j):,}, places {j.poi.nunique()}, {j.dt.min()} ~ {j.dt.max()}")

    m_oa, m_d = shape_metrics(j, "est_oa"), shape_metrics(j, "est_dong")
    names = w_d.drop_duplicates("AREA_CD").set_index("AREA_CD")[["AREA_NM", "CATEGORY"]]
    cmp = m_d.add_suffix("_dong").join(m_oa.add_suffix("_oa")).join(names)

    print("\n== median across places (July 2026) ==")
    for c in ["r_hourly", "r_week", "top3"]:
        print(f"{c:>9}: 행정동 {cmp[c+'_dong'].median():.2f}  ->  집계구 {cmp[c+'_oa'].median():.2f}")
    print(f"share with r_week >= 0.8: 행정동 {(cmp.r_week_dong >= .8).mean()*100:.0f}%  ->  집계구 {(cmp.r_week_oa >= .8).mean()*100:.0f}%")
    print(f"share with r_week < 0.3 : 행정동 {(cmp.r_week_dong < .3).mean()*100:.0f}%  ->  집계구 {(cmp.r_week_oa < .3).mean()*100:.0f}%")
    for u in ["dong", "oa"]:
        r = cmp[f"ratio_{u}"].astype(float)
        print(f"level ratio live/est {u}: median {r.median():.2f}, 10-90% [{r.quantile(.1):.2f}, {r.quantile(.9):.2f}]")

    print("\n== by category (median r_week) ==")
    print(cmp.groupby("CATEGORY")[["r_week_dong", "r_week_oa", "top3_dong", "top3_oa"]].median().round(2)
          .assign(n=cmp.groupby("CATEGORY").size()).to_string())
    print("\n== previously worst places ==")
    worst = cmp.nsmallest(10, "r_week_dong")
    print(worst[["AREA_NM", "CATEGORY", "r_week_dong", "r_week_oa", "top3_dong", "top3_oa"]].round(2).to_string())
    print("\n== still bad at 집계구 (r_week_oa < 0.5) ==")
    print(cmp[cmp.r_week_oa < .5][["AREA_NM", "CATEGORY", "r_week_oa"]].round(2).to_string())
    cmp.to_csv(D / "fill_gap_oa_vs_dong.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
