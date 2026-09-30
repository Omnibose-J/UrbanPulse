"""E1 (구현설계서 7.1): tier-B station estimate, served form, scored on live truth.

The 44 station-named live places stand in for tier-B stations:
  area      : 250m circle(s) around the station coordinate(s)  (not the POI polygon)
  oa flow   : 집계구 생활인구 2026-05..06, holidays excluded, day type (평일/토/일) x hour
  st flow   : ridership 2026-04..06 daily totals x monthly hourly share (May-Jun), holidays excluded
  rule      : corr(oa flow, st flow) < 0.2 -> st flow
  levels    : rel = flow / p90(flow, 09-23h); 0 <0.5, 1 0.5-0.9, 2 >=0.9
  holidays  : ratio_v1b = calendar + flow-shape features (no place id), trained on proxy
              WITHOUT these 44 places; target log(act / non-holiday same-day-type 3-week mean)
Truth: live population 2026-08-01..09-29 (after every input month).
Frozen pass bars: weekly-profile r median >= 0.8 and share r<0.3 <= 10%;
                  level agreement >= 60%; holiday rel-WAPE with adjustment < without.
"""
import re
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import HOLIDAYS, load  # noqa: E402
from eval_fill_gap import D, live_hourly  # noqa: E402
from eval_fill_gap_oa import read_oa  # noqa: E402
from eval_ratio_live import calendar  # noqa: E402
from eval_station_fill import norm  # noqa: E402

RADIUS = 250
HOURS = list(range(9, 24))
TEST_HOLS = ["2026-08-15", "2026-08-17", "2026-09-24", "2026-09-25", "2026-09-26"]


def dtype_of(idx):
    return np.where(idx.dayofweek == 6, "sun", np.where(idx.dayofweek == 5, "sat", "wk"))


def weekly(s):
    """Series indexed by hourly ts (non-holiday) -> (dtype, hour) mean vector."""
    s = s[~s.index.normalize().isin(HOLIDAYS)].dropna()
    w = s.groupby([dtype_of(s.index), s.index.hour]).mean()
    w.index.names = ["dtype", "hour"]  # sources carry different index names; unify for corr/align
    return w


def station_places():
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    st = pd.read_csv(D / "subway/stations.csv")
    st["n"] = st.BLDN_NM.map(norm)
    coords = st.groupby("n")[["LAT", "LOT"]].mean()
    out = {}
    for poi, nm in names.items():
        parts = [norm(p) for p in re.split(r"[·,]", nm) if p.strip().endswith("역")]
        parts = [p for p in parts if p in coords.index]
        if parts:
            out[poi] = parts
    return out, coords


def buffers(pl, coords):
    pts = [(poi, s, coords.loc[s, "LOT"], coords.loc[s, "LAT"]) for poi, ss in pl.items() for s in ss]
    g = gpd.GeoDataFrame({"poi": [p[0] for p in pts]}, geometry=gpd.points_from_xy([p[2] for p in pts], [p[3] for p in pts]), crs=4326)
    return g.to_crs(5179).assign(geometry=lambda x: x.buffer(RADIUS)).dissolve("poi").reset_index()


def oa_flow(buf):
    z = zipfile.ZipFile(D / "lp_oa/oa_202606.zip")
    codes = set(pd.read_csv(z.open(z.namelist()[0]), encoding="cp949", usecols=[3], dtype=str, index_col=False).iloc[:, 0])
    oa = gpd.read_file(D / "poi/oa2016.geojson").to_crs(5179)
    oa = oa[oa.TOT_OA_CD.isin(codes)]
    oa["oa_area"] = oa.area
    ov = gpd.overlay(buf[["poi", "geometry"]], oa[["TOT_OA_CD", "oa_area", "geometry"]], how="intersection")
    ov["w"] = ov.area / ov.oa_area
    pop = pd.concat([read_oa(set(ov.TOT_OA_CD), ym) for ym in ("202605", "202606")])
    e = ov.merge(pop, left_on="TOT_OA_CD", right_on="oa")
    return (e["pop"] * e.w).groupby([e.poi, e.dt]).sum().unstack(0)


def st_flow(pl):
    daily = pd.concat([pd.read_csv(D / f"subway/day_{s}.csv", encoding="utf-8-sig", index_col=False) for s in (153, 154, 155)])
    daily["st"], daily["d"] = daily.역명.map(norm), pd.to_datetime(daily.사용일자.astype(str))
    daily = daily.drop_duplicates(["d", "노선명", "역명"]).groupby(["st", "d"])[["승차총승객수", "하차총승객수"]].sum().sum(axis=1)
    m = pd.read_csv(D / "subway/hourly_month_2026.csv")
    m = m[m.USE_MM.isin([202605, 202606])].sort_values("JOB_YMD").drop_duplicates(["USE_MM", "SBWY_ROUT_LN_NM", "STTN"], keep="last")
    m["st"] = m.STTN.map(norm)
    mh = pd.DataFrame({h: m[[f"HR_{h}_GET_ON_NOPE", f"HR_{h}_GET_OFF_NOPE"]].sum(axis=1) for h in range(24)}).assign(st=m.st).groupby("st").sum()
    share = mh.div(mh.sum(axis=1), axis=0)
    share = (share + share[[(h - 1) % 24 for h in range(24)]].values) / 2  # stock ~ mean of bins H-1, H
    out = {}
    for poi, sts in pl.items():
        parts = []
        for s in sts:
            if s in share.index and s in daily.index.get_level_values(0):
                tot = daily.xs(s, level=0)
                idx = pd.date_range(tot.index.min(), tot.index.max() + pd.Timedelta(hours=23), freq="h")
                parts.append(pd.Series(tot.reindex(idx.normalize()).values * share.loc[s].values[idx.hour], index=idx))
        if parts:
            out[poi] = sum(parts)
    return pd.DataFrame(out)


def shape_feats(w):
    """flow-shape summary from a (dtype, hour) weekly vector."""
    wk = w.xs("wk")
    tot = wk.sum()
    return {"am": wk.loc[7:9].sum() / tot, "pm": wk.loc[18:20].sum() / tot, "night": wk.loc[[22, 23, 0, 1]].sum() / tot,
            "wkend": (w.xs("sat").mean() + w.xs("sun").mean()) / 2 / wk.mean()}


def train_ratio_v1b(exclude):
    P = load("place").pivot(index="dt", columns="dong", values="pop").asfreq("h")
    P = P[[c for c in P.columns if c not in exclude]]
    times = P.index
    hol_day = times.normalize().isin(HOLIDAYS)
    Pn = P.copy()
    Pn.loc[hol_day] = np.nan  # baseline weeks ignore holiday days
    base = pd.concat([Pn.shift(7 * 24 * k) for k in (1, 2, 3)]).groupby(level=0).mean()
    shp = {c: shape_feats(weekly(P[c][P.index >= "2025-01-01"])) for c in P.columns}
    cal = calendar(times).reset_index(drop=True)
    y = np.log(P / base)
    rows = []
    for j, c in enumerate(P.columns):
        f = cal.copy()
        for k, v in shp[c].items():
            f[k] = v
        f["y"] = y[c].values
        rows.append(f[21 * 24:])
    df = pd.concat(rows).replace([np.inf, -np.inf], np.nan).dropna().sample(n=2_000_000, random_state=0)
    feats = [c for c in df.columns if c != "y"]
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=63, random_state=0).fit(df[feats], df.y)
    print(f"ratio_v1b trained on {len(df):,} rows from {P.shape[1]} places (excluding {len(exclude)})")
    return m, feats


def main():
    pl, coords = station_places()
    buf = buffers(pl, coords)
    live = live_hourly().pivot(index="dt", columns="poi", values="live").asfreq("h")
    live = live[[p for p in pl if p in live.columns]]
    oa, st = oa_flow(buf), st_flow(pl)
    test = live[live.index >= "2026-08-01"]
    res, lv = [], []
    flows = {}
    for p in live.columns:
        if p not in oa.columns:
            continue
        w_oa = weekly(oa[p])
        w_st = weekly(st[p]) if p in st.columns else None
        agree = w_oa.corr(w_st) if w_st is not None else np.nan
        chosen = w_st if (w_st is not None and agree < 0.2) else w_oa
        flows[p] = chosen
        w_live = weekly(test[p])
        rel = chosen / chosen[chosen.index.get_level_values(1).isin(HOURS)].quantile(.9)
        res.append({"poi": p, "agree": agree, "use_st": w_st is not None and agree < 0.2,
                    "r_chosen": chosen.corr(w_live), "r_oa": w_oa.corr(w_live),
                    "r_st": w_st.corr(w_live) if w_st is not None else np.nan})
        # level agreement on non-holiday service hours (09-22)
        tl = test[p].dropna()
        tl = tl[~tl.index.normalize().isin(HOLIDAYS) & tl.index.hour.isin(range(9, 23))]
        live_rel = tl / tl.quantile(.9)
        pred_rel = pd.Series(rel.reindex(list(zip(dtype_of(tl.index), tl.index.hour))).values, index=tl.index)
        cut = lambda s: np.digitize(s, [0.5, 0.9])
        lv.append(pd.DataFrame({"poi": p, "pred": cut(pred_rel.values), "act": cut(live_rel.values)}))
    r = pd.DataFrame(res).set_index("poi")
    lvl = pd.concat(lv)
    print(f"station places scored: {len(r)} (radius {RADIUS}m), switched to ridership: {int(r.use_st.sum())}")
    print("\n== E1 flow: weekly-profile r vs LIVE (Aug-Sep, non-holiday) ==")
    for c in ["r_chosen", "r_oa", "r_st"]:
        s = r[c].dropna()
        print(f"{c:>9}: median {s.median():.2f}  r>=0.8 {(s >= .8).mean():.0%}  r<0.3 {(s < .3).mean():.0%}  (n={len(s)})")
    print(f"level agreement (3 levels, non-holiday 09-22): {(lvl.pred == lvl.act).mean():.1%}  "
          f"(majority-class baseline {lvl.act.value_counts(normalize=True).max():.1%})")
    print("\nworst r_chosen:\n" + r.nsmallest(6, "r_chosen").round(2).to_string())

    # holiday adjustment with ratio_v1b
    m, feats = train_ratio_v1b(exclude=set(r.index))
    errs = []
    for p, w in flows.items():
        tl = test[p].dropna()
        tl = tl[tl.index.normalize().isin(pd.to_datetime(TEST_HOLS)) & tl.index.hour.isin(range(9, 23))]
        if tl.empty:
            continue
        nh = test[p].dropna()
        nh = nh[~nh.index.normalize().isin(HOLIDAYS) & nh.index.hour.isin(HOURS)]
        live_rel = tl / nh.quantile(.9)
        p90 = w[w.index.get_level_values(1).isin(HOURS)].quantile(.9)
        base_rel = pd.Series(w.reindex(list(zip(dtype_of(tl.index), tl.index.hour))).values / p90, index=tl.index)
        f = calendar(tl.index).reset_index(drop=True)
        for k, v in shape_feats(w).items():
            f[k] = v
        adj = base_rel * np.exp(m.predict(f[feats]))
        errs.append(pd.DataFrame({"poi": p, "day": tl.index.strftime("%m-%d"), "live": live_rel.values,
                                  "noadj": base_rel.values, "adj": adj.values}))
    e = pd.concat(errs).dropna()
    wape = lambda g: pd.Series({c: np.abs(g[c] - g.live).sum() / g.live.sum() * 100 for c in ["noadj", "adj"]} | {"n": len(g)})
    print("\n== E1 holidays (rel-WAPE %, live truth, 09-22h): profile only vs x ratio_v1b ==")
    print(pd.concat([wape(e).to_frame("all").T, e.groupby("day").apply(wape, include_groups=False)]).round(1).to_string())
    r.to_csv(D / "e1_places.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
