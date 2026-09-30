"""Calendar-only deviation model, tested out-of-sample on UNSEEN holidays with live truth.

Why: 생활인구 ends 2026-07, so a deployable model cannot need recent proxy levels.
Model: log(act / prof3) ~ place, hour, dow, month, holiday flags, distance to holiday, horizon
       trained on the 집계구 place proxy 2023-01 ~ 2026-07 (build_place_oa.py).
Serve: live 3-week same-weekday average x exp(predicted deviation).
Test : live population 2026-08-01 ~ 09-29 (8/15 Sat, 8/17 Mon substitute, 추석 9/24-26),
       design frozen before looking at these dates. Also checks the May-Jul hypothesis
       "apply the deviation only on weekday holidays".
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import BIG, HOLIDAYS, WIN, load  # noqa: E402
from eval_fill_gap import D, live_hourly  # noqa: E402

HORIZONS = [1, 3, 7]
TEST_HOLS = {"2026-08-15": "광복절(토)", "2026-08-17": "대체공휴일(월)", "2026-09-24": "추석 연휴(목)",
             "2026-09-25": "추석(금)", "2026-09-26": "추석 연휴(토)"}


def calendar(times):
    """Calendar features for an hourly DatetimeIndex (works beyond the proxy's end)."""
    day = times.normalize()
    hol = day.isin(HOLIDAYS)
    big = np.zeros(len(times), dtype=int)
    for k, (kind, starts) in enumerate(BIG.items(), 1):
        for s in starts:
            big[day.isin([s + pd.Timedelta(days=o) for o in WIN])] = k
    hd = np.array(sorted(set(HOLIDAYS)), dtype="datetime64[ns]")
    dv = day.values.astype("datetime64[ns]")
    pos = np.searchsorted(hd, dv)
    nxt = (hd[np.minimum(pos, len(hd) - 1)] - dv) / np.timedelta64(1, "D")
    prv = (dv - hd[np.maximum(pos - 1, 0)]) / np.timedelta64(1, "D")
    return pd.DataFrame({"hour": times.hour, "dow": times.dayofweek, "month": times.month, "hol": hol.astype(int),
                         "hol_wkend": (hol & (times.dayofweek >= 5)).astype(int), "big": big,
                         "to_hol": np.clip(nxt, 0, 8), "from_hol": np.clip(prv, 0, 8)}, index=times)


def train(horizons=HORIZONS, until=None):
    """until: last proxy timestamp used for training (None = all, i.e. through 2026-07)."""
    P = load("place").pivot(index="dt", columns="dong", values="pop").asfreq("h")
    if until is not None:
        P = P[P.index <= until]
    times, places, X = P.index, P.columns.values, P.values
    cal = calendar(times)
    rows = []
    for h in horizons:
        kmin = 1 if h < 7 else 2
        wk = [np.roll(X, 7 * 24 * k, axis=0) for k in range(kmin, kmin + 3)]
        for w, k in zip(wk, range(kmin, kmin + 3)):
            w[: 7 * 24 * k] = np.nan
        prof = np.nanmean(wk, axis=0)
        df = pd.DataFrame({"y": np.log((X / prof).ravel()), "poi_i": np.tile(np.arange(len(places)), len(times)),
                           "t": np.repeat(np.arange(len(times)), len(places)), "h": h})
        rows.append(df.replace([np.inf, -np.inf], np.nan).dropna())
    df = pd.concat(rows)
    df = df[df.t >= 21 * 24].sample(n=3_000_000, random_state=0)
    feats = cal.iloc[df.t.values].reset_index(drop=True)
    feats["poi_i"], feats["h"] = df.poi_i.values, df.h.values
    m = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, max_leaf_nodes=63, random_state=0)
    m.fit(feats, df.y.values)
    print(f"trained on {len(df):,} rows, proxy {times.min().date()} ~ {times.max().date()}, places {len(places)}")
    return m, {p: i for i, p in enumerate(places)}, feats.columns


def live_eval(m, pidx, cols, horizons=HORIZONS, start="2026-08-01", require=("live", "prof", "last"), fill_gaps=False):
    """Serve-form predictions (live 3-week same-weekday avg x predicted ratio) for targets >= start."""
    live = live_hourly()
    L = live.pivot(index="dt", columns="poi", values="live").asfreq("h")
    L = L[[p for p in L.columns if p in pidx]]
    if fill_gaps:  # backtest only: hourly extraction left 1h holes on many days; the 30-min service feed has none
        L = L.interpolate(limit=1, limit_area="inside")
    out = []
    for h in horizons:
        kmin = 1 if h < 7 else 2
        wk = [L.shift(7 * 24 * k) for k in range(kmin, kmin + 3)]
        prof = pd.concat(wk).groupby(level=0).mean()
        last = wk[0]
        tt = L.index[(L.index >= start)]
        for p in L.columns:
            d = pd.DataFrame({"live": L.loc[tt, p], "prof": prof.loc[tt, p], "last": last.loc[tt, p]}).dropna(subset=list(require))  # scoring needs live+last; serving needs only prof
            if d.empty:
                continue
            f = calendar(d.index).reset_index(drop=True)
            f["poi_i"], f["h"] = pidx[p], h
            d["ratio"] = np.exp(m.predict(f[cols]))
            d["poi"], d["h"] = p, h
            out.append(d)
    r = pd.concat(out)
    r["model"] = r.prof * r.ratio
    r["day"] = r.index.strftime("%Y-%m-%d")
    r["hol"] = r.day.isin(TEST_HOLS)
    return r


def main():
    m, pidx, cols = train()
    r = live_eval(m, pidx, cols)
    wkday_hol = r.hol & (r.index.dayofweek < 5)
    r["model_wkday_only"] = np.where(r.hol & ~wkday_hol, r.prof, r.model)
    cols_ = ["last", "prof", "model", "model_wkday_only"]
    wape = lambda g: pd.Series({c: np.abs(g[c] - g.live).sum() / g.live.sum() * 100 for c in cols_} | {"n": len(g)})

    print(f"live test {r.index.min()} ~ {r.index.max()}, places {r.poi.nunique()}")
    for name, sub in [("unseen holidays (5 days)", r[r.hol]), ("normal days Aug-Sep", r[~r.hol])]:
        print(f"\n== {name}: WAPE % vs LIVE ==")
        print(sub.groupby("h").apply(wape, include_groups=False).round(1).to_string())
    t = r[r.hol & (r.h == 3)].groupby("day").apply(wape, include_groups=False).round(1)
    t.index = [f"{d} {TEST_HOLS[d]}" for d in t.index]
    print("\n== per holiday (h=3) ==\n" + t.to_string())
    s = r[(r.h == 3) & r.index.hour.isin(range(10, 23))]
    print("\n== service hours 10-22, h=3 ==")
    print(pd.DataFrame({"holidays": wape(s[s.hol]), "normal": wape(s[~s.hol])}).round(1).to_string())
    # days just before/after 추석 (travel-out effect), h=3
    near = r[(r.h == 3) & r.day.isin(["2026-09-22", "2026-09-23", "2026-09-27", "2026-09-28"])]
    print("\n== 추석 adjacent days (9/22-23, 9/27-28), h=3 ==")
    print(near.groupby("day").apply(wape, include_groups=False).round(1).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
