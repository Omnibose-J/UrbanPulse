"""Consistent re-judgement, part 2: the crowd-only recommendation promises of A2 and B had never been tested.

Same verdict rule and bar as rejudge.py (crowd promise >= 80%, place-bootstrap 95% CI).
A2 (live, no commerce): served forecast (h=3, as of D-3), level thresholds from 90 days before issue,
   candidate hours 09-20, score = -w*L (calm w=0.6) / -0.5*|L-1| (lively); truth = Seoul level at the hour.
   allowed: calm <= 1, lively <= 2.
B  (45 station places as stand-ins): chosen flow (rule threshold 0.0) x ratio_v1b on holidays, 3 levels,
   candidate hours 09-22, calm score = -0.6*L; truth = live relative level (live / p90 of non-holiday live).
   allowed: calm <= 1. ('lively' allows every B level -> true by definition, not judged.)
Appends to data/rejudge.csv.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import HOLIDAYS  # noqa: E402
from eval_fill_gap import D, live_hourly  # noqa: E402
from eval_ratio_live import calendar, live_eval, train  # noqa: E402
from exp_e1_tier_b import HOURS, buffers, dtype_of, oa_flow, shape_feats, st_flow, station_places, train_ratio_v1b, weekly  # noqa: E402
from exp_e3_e4_reco import load_commerce, load_obs, thresholds, windows  # noqa: E402
import rejudge as rj  # noqa: E402


def a2():
    obs, com = load_obs(), load_commerce()
    a2 = sorted(set(obs.poi) - set(com.poi))
    m, pidx, cols = train(horizons=[3])
    fc = live_eval(m, pidx, cols, horizons=[3], start="2026-08-01", require=("prof",), fill_gaps=True).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})
    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    rows = []
    places = [p for p in a2 if p in set(fc.poi)]
    for p in places:
        op = obs[obs.poi == p]
        for d in pd.date_range("2026-08-01", "2026-09-29", freq="D"):
            issue = d - pd.Timedelta(days=3)
            ho = op[(op.h < issue) & (op.h >= issue - pd.Timedelta(days=90))]
            if len(ho) < 24 * 14:
                continue
            thr = thresholds(ho)
            Lp = {}
            for hr in range(9, 21):
                pop = fc_i.get((p, d + pd.Timedelta(hours=hr)))
                if pop is not None and not np.isnan(pop):
                    Lp[hr] = sum(pop >= t for t in thr)
            if len(Lp) < 6:
                continue
            for tol, fn, allowed in [("calm", lambda L: -0.6 * L, 1), ("lively", lambda L: -0.5 * abs(L - 1), 2)]:
                for w in windows({h: fn(L) for h, L in Lp.items()}, set(Lp)):
                    for hr in w:
                        La = L_act.get((p, d + pd.Timedelta(hours=hr)))
                        if La is not None and not np.isnan(La):
                            rows.append({"poi": p, "tol": tol, "crowd_ok": La <= allowed})
    r = pd.DataFrame(rows)
    print(f"A2 places {r.poi.nunique()} (of {len(a2)}), scored hours {len(r):,}")
    for tol, g in r.groupby("tol"):
        gc = {p: x.crowd_ok.values for p, x in g.groupby("poi")}
        rj.verdict(f"A2 {tol} 혼잡 약속", g.crowd_ok.mean() * 100, rj.boot(gc, rj.rate(None)), 80)


def tier_b():
    pl, coords = station_places()
    buf = buffers(pl, coords)
    live = live_hourly().pivot(index="dt", columns="poi", values="live").asfreq("h")
    oa, st = oa_flow(buf), st_flow(pl)
    test = live[live.index >= "2026-08-01"]
    flows = {}
    for p in [p for p in pl if p in live.columns and p in oa.columns]:
        w_oa = weekly(oa[p])
        w_st = weekly(st[p]) if p in st.columns else None
        ag = w_oa.corr(w_st) if w_st is not None else np.nan
        flows[p] = w_st if (w_st is not None and ag < 0.0) else w_oa
    m, feats = train_ratio_v1b(exclude=set(flows))
    rows = []
    for p, w in flows.items():
        p90 = w[w.index.get_level_values(1).isin(HOURS)].quantile(.9)
        nh = test[p].dropna()
        nh = nh[~nh.index.normalize().isin(HOLIDAYS) & nh.index.hour.isin(HOURS)]
        lp90 = nh.quantile(.9)
        sf = shape_feats(w)
        for d in pd.date_range("2026-08-01", "2026-09-29", freq="D"):
            hrs = pd.date_range(d + pd.Timedelta(hours=9), d + pd.Timedelta(hours=22), freq="h")
            rel = w.reindex(list(zip(dtype_of(hrs), hrs.hour))).values / p90
            if d in HOLIDAYS:
                f = calendar(hrs).reset_index(drop=True)
                for k, v in sf.items():
                    f[k] = v
                rel = rel * np.exp(m.predict(f[feats]))
            Lp = {h.hour: int(np.digitize(x, [0.5, 0.9])) for h, x in zip(hrs, rel) if not np.isnan(x)}
            for win in windows({h: -0.6 * L for h, L in Lp.items()}, set(Lp)):
                for hr in win:
                    a = test[p].get(d + pd.Timedelta(hours=hr))
                    if a is not None and not np.isnan(a):
                        rows.append({"poi": p, "crowd_ok": int(np.digitize(a / lp90, [0.5, 0.9])) <= 1})
    r = pd.DataFrame(rows)
    print(f"B stand-in places {r.poi.nunique()}, scored hours {len(r):,}")
    gc = {p: x.crowd_ok.values for p, x in r.groupby("poi")}
    rj.verdict("B calm 혼잡 약속 (가장 붐비는 시간대 피하기)", r.crowd_ok.mean() * 100, rj.boot(gc, rj.rate(None)), 80)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a2()
    tier_b()
    t = pd.DataFrame(rj.OUT)
    print(t.to_string(index=False))
    old = pd.read_csv(D / "rejudge.csv")
    pd.concat([old, t]).to_csv(D / "rejudge.csv", index=False, encoding="utf-8-sig")
