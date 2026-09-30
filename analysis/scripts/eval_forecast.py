"""How good is Seoul's own 12h population forecast (서울 실시간 도시데이터 FCST_PPLTN),
and can simple baselines / a GBM with weather+event features beat it?

Inputs: data/obs.csv, data/fcst.csv (from collect_rtd.py).
Population comes as 500-wide [min,max] buckets; we use the midpoint throughout.
Test = issues in the last 7 days; GBM trains on issues before that.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

D = Path(__file__).resolve().parent.parent / "data"
LVLS = ["여유", "보통", "약간 붐빔", "붐빔"]
H = pd.Timedelta(hours=1)


def load():
    o = pd.read_csv(D / "obs.csv", parse_dates=["ppltn_time"])
    o["mid"] = (o.pmin + o.pmax) / 2
    o["lvl_i"] = o.lvl.map({l: i for i, l in enumerate(LVLS)})
    o = o.drop_duplicates(["poi", "ppltn_time"]).sort_values(["poi", "ppltn_time"])
    f = pd.read_csv(D / "fcst.csv", parse_dates=["ppltn_time", "fcst_time"])
    f = f.drop_duplicates(["poi", "ppltn_time", "fcst_time"])
    f["city"] = (f.fmin + f.fmax) / 2
    f["h"] = np.ceil((f.fcst_time - f.ppltn_time) / H).astype(int)
    return o, f


def hourly_grid(o):
    """Actual population interpolated onto whole hours (gaps > 2h left NaN)."""
    out = []
    for poi, g in o.groupby("poi"):
        s = g.set_index("ppltn_time").mid
        grid = pd.date_range(s.index.min().ceil("h"), s.index.max().floor("h"), freq="h")
        u = s.reindex(s.index.union(grid)).interpolate("time", limit=4, limit_area="inside").reindex(grid)
        out.append(pd.DataFrame({"poi": poi, "T": grid, "act": u.values}))
    return pd.concat(out)


def level_thresholds(o):
    """Per POI: lowest midpoint ever labelled at level>=k, used to map a number to a level."""
    thr = {}
    for poi, g in o.groupby("poi"):
        thr[poi] = [g.loc[g.lvl_i >= k, "mid"].min() if (g.lvl_i >= k).any() else np.inf for k in (1, 2, 3)]
    return thr


def to_level(poi_arr, val_arr, thr):
    return np.array([sum(v >= t for t in thr[p]) for p, v in zip(poi_arr, val_arr)])


def main():
    o, f = load()
    A = hourly_grid(o)
    act = A.set_index(["poi", "T"]).act
    look = lambda poi, t: act.reindex(pd.MultiIndex.from_arrays([poi, t])).values

    df = f.rename(columns={"fcst_time": "T", "ppltn_time": "t"})
    df = df.merge(o[["poi", "ppltn_time", "mid", "temp", "precip", "precpt_type", "n_event"]]
                  .rename(columns={"ppltn_time": "t", "mid": "now"}), on=["poi", "t"], how="left")
    df["act"] = look(df.poi, df["T"])
    for k in (1, 2, 3):
        df[f"w{k}"] = look(df.poi, df["T"] - k * 7 * 24 * H)
    df["lag24"] = look(df.poi, df["T"] - 24 * H)
    df["prof"] = df[["w1", "w2", "w3"]].mean(axis=1)
    now_prof = pd.concat([pd.Series(look(df.poi, df.t.dt.floor("h") - k * 7 * 24 * H)) for k in (1, 2, 3)], axis=1).mean(axis=1).values
    df["ratio"] = np.clip(df.now / now_prof, 0.5, 2.0)
    df["prof_x_ratio"] = df.prof * df.ratio
    df["hour"], df["dow"] = df["T"].dt.hour, df["T"].dt.dayofweek
    df["rain"] = df.precpt_type.fillna("없음").ne("없음").astype(int)
    df["poi_i"] = df.poi.str[3:].astype(int)
    df = df.dropna(subset=["act", "now", "w1"])

    cut = df.t.max().normalize() - pd.Timedelta(days=6)
    tr, te = df[df.t < cut].copy(), df[df.t >= cut].copy()
    print(f"obs rows {len(o):,}  POIs {o.poi.nunique()}  range {o.ppltn_time.min()} ~ {o.ppltn_time.max()}")
    print(f"forecast pairs with truth: train {len(tr):,} (issues < {cut.date()}), test {len(te):,}")

    feats = ["poi_i", "hour", "dow", "h", "now", "lag24", "w1", "prof", "ratio", "temp", "rain", "n_event"]
    for name, cols in [("gbm_no_city", feats), ("gbm_plus_city", feats + ["city"])]:
        m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, categorical_features=[0], random_state=0)
        m.fit(tr[cols], np.log1p(tr.act))
        te[name] = np.expm1(m.predict(te[cols]))

    te["persist"], te["week_ago"] = te.now, te.w1
    thr = level_thresholds(o)
    te["act_lvl"] = to_level(te.poi, te.act, thr)
    models = ["city", "persist", "week_ago", "prof", "prof_x_ratio", "gbm_no_city", "gbm_plus_city"]

    def table(sub, title):
        rows = []
        for hb, g in sub.groupby(pd.cut(sub.h, [0, 1, 3, 6, 12], labels=["1h", "2-3h", "4-6h", "7-12h"]), observed=True):
            r = {"horizon": hb, "n": len(g)}
            for m_ in models:
                r[m_] = np.abs(g[m_] - g.act).sum() / g.act.sum() * 100  # WAPE %
            rows.append(r)
        print(f"\n== {title}: WAPE % (lower is better) ==")
        print(pd.DataFrame(rows).round(1).to_string(index=False))

    table(te, "test week, all POIs")
    hol = te["T"].dt.strftime("%m-%d").isin(["09-24", "09-25", "09-26"])  # 2026 추석 연휴
    table(te[hol], "test, 추석 연휴 target hours")
    table(te[~hol], "test, non-holiday target hours")

    # Level accuracy and recall of busy hours (act level >= 약간 붐빔)
    print("\n== level metrics on test (h=2-6) ==")
    g = te[(te.h >= 2) & (te.h <= 6)]
    busy = g.act_lvl >= 2
    print(f"busy share {busy.mean()*100:.1f}%  (n={busy.sum()})")
    for m_ in models:
        pl = to_level(g.poi, g[m_], thr)
        rec = (pl[busy.values] >= 2).mean() * 100 if busy.any() else float("nan")
        prec = (busy.values[pl >= 2]).mean() * 100 if (pl >= 2).any() else float("nan")
        print(f"{m_:>14}: level acc {(pl == g.act_lvl.values).mean()*100:5.1f}%  busy recall {rec:5.1f}%  precision {prec:5.1f}%")

    # Where does the city forecast miss most? Surprise hours: actual deviates >30% from 3-week profile
    te["surprise"] = (te.act / te.prof - 1).abs() > 0.3
    print(f"\n== surprise hours (|act/profile-1|>30%): {te.surprise.mean()*100:.1f}% of test pairs ==")
    table(te[te.surprise], "surprise hours only")
    table(te[te.n_event > 0], "POIs with an event listed at issue time")

    worst = te.assign(err=np.abs(te.city - te.act) / te.act).groupby(["poi"]).agg(name=("poi", "first"), err=("err", "mean")).nlargest(8, "err")
    names = o.drop_duplicates("poi").set_index("poi").name
    worst["name"] = names.reindex(worst.index).values
    print("\n== POIs where the city forecast errs most (mean APE, test) ==")
    print(worst.round(2).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
