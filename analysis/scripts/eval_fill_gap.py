"""Experiment B: can 행정동 생활인구 stand in for a place that has no live feed?

For each of the 121 city-data places we build an area-weighted estimate from the
행정동 hourly 생활인구 (uniform density inside a dong) and compare it with the place's
real live population (city data, recovered 2026-05-12 ~ 2026-07-31 overlap).

Questions:
  shape : does the estimate rise/fall at the same hours? (Pearson r of hourly series,
          and overlap of each day's busiest 3 hours)
  level : is actual/estimate stable across places? (if not, absolute headcount for an
          unseen place cannot be recovered and the service must speak in relative terms)
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent.parent / "data"


def area_weights():
    poi = gpd.read_file(D / "poi/서울시 주요 121장소 영역/서울시 주요 121장소 영역.shp").to_crs(5179)
    dong = gpd.read_file(D / "poi/dong.geojson")
    dong = dong[dong.sido == "11"].to_crs(5179)
    dong["dong"] = dong.adm_cd2.str[:8].astype(int)
    dong["dong_area"] = dong.area
    ov = gpd.overlay(poi[["AREA_CD", "AREA_NM", "CATEGORY", "geometry"]], dong[["dong", "dong_area", "geometry"]], how="intersection")
    ov["w"] = ov.area / ov.dong_area
    poi_area = poi.set_index("AREA_CD").area / 1e6
    return ov[["AREA_CD", "AREA_NM", "CATEGORY", "dong", "w"]], poi_area


def live_hourly():
    o = pd.concat([pd.read_csv(D / f, parse_dates=["ppltn_time"]) for f in ("obs_hist.csv", "obs_hist_aug.csv", "obs.csv")])
    o["mid"] = (o.pmin + o.pmax) / 2
    o = o.drop_duplicates(["poi", "ppltn_time"])
    o["dt"] = o.ppltn_time.dt.round("h")
    return o.groupby(["poi", "dt"]).mid.mean().rename("live").reset_index()


def main():
    w, poi_area = area_weights()
    lp = pd.read_parquet(D / "lp_dong.parquet")
    lp = lp[lp.dt >= "2026-05-01"]
    est = w.merge(lp, on="dong")
    est["pop_w"] = est["pop"] * est.w
    est = est.groupby(["AREA_CD", "dt"]).pop_w.sum().rename("est").reset_index().rename(columns={"AREA_CD": "poi"})

    j = live_hourly().merge(est, on=["poi", "dt"])
    meta = w.drop_duplicates("AREA_CD").set_index("AREA_CD")[["AREA_NM", "CATEGORY"]]
    print(f"overlap hours: {j.dt.min()} ~ {j.dt.max()}, places {j.poi.nunique()}, rows {len(j):,}")

    res = []
    for poi, g in j.groupby("poi"):
        if len(g) < 24 * 14:
            continue
        g = g.assign(d=g.dt.dt.normalize(), hour=g.dt.dt.hour)
        # hour-of-week mean profiles: the "typical week" a service would show for an unseen place
        g["how"] = g.dt.dt.dayofweek * 24 + g.hour
        pl, pe = g.groupby("how").live.mean(), g.groupby("how").est.mean()
        hits = []
        for _, x in g.groupby("d"):
            if len(x) >= 20:
                hits.append(len(set(x.nlargest(3, "live").hour) & set(x.nlargest(3, "est").hour)) / 3)
        res.append({"poi": poi, "r_hourly": g.live.corr(g.est), "r_week_profile": pl.corr(pe),
                    "top3_hit": np.mean(hits), "ratio": g.live.mean() / g.est.mean(), "n": len(g)})
    r = pd.DataFrame(res).set_index("poi").join(meta)

    print(f"\nplaces evaluated: {len(r)}")
    print("\n== shape agreement (median / IQR across places) ==")
    for c in ["r_hourly", "r_week_profile", "top3_hit"]:
        q = r[c].quantile([.25, .5, .75]).round(2).tolist()
        print(f"{c:>15}: median {q[1]}  IQR [{q[0]}, {q[2]}]")
    print(f"share of places with weekly-profile r >= 0.8: {(r.r_week_profile >= .8).mean()*100:.0f}%")
    print(f"(chance level for top3_hit ~ {3/24:.2f})")

    print("\n== by category (median) ==")
    print(r.groupby("CATEGORY")[["r_hourly", "r_week_profile", "top3_hit", "ratio"]].median().round(2).assign(n=r.groupby("CATEGORY").size()).to_string())

    lr = np.log10(r.ratio)
    print(f"\n== level: live/estimate ratio across places ==  median {r.ratio.median():.2f}, "
          f"10-90% [{r.ratio.quantile(.1):.2f}, {r.ratio.quantile(.9):.2f}], log10 sd {lr.std():.2f}")

    print("\n== worst shape agreement ==")
    print(r.nsmallest(8, "r_week_profile")[["AREA_NM", "CATEGORY", "r_hourly", "r_week_profile", "top3_hit"]].round(2).to_string())
    print("\n== best ==")
    print(r.nlargest(5, "r_week_profile")[["AREA_NM", "CATEGORY", "r_hourly", "r_week_profile", "top3_hit"]].round(2).to_string())
    r.to_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
