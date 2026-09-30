"""E3b: one recorded retry of the 쇼핑 (shop) recommendation criterion after E3 failed (83.4% < 85%).

Pre-registered before running:
  candidates : predicted-activity threshold {0.5, 0.6, 0.7} x activity profile {all history, last 28 days}
               (the truth definition - actual a_shop >= 0.5 - is NOT changed)
  selection  : on August only; pick the candidate passing lively>=85% & crowd>=80% with the highest
               coverage, where coverage = share of (place, day, tolerance) that got >=1 window;
               a candidate must keep coverage >= 80% of the current rule's (0.5, all history)
  test       : the selected candidate on September (non-명절 days) against the same bars
명절 days are excluded (handled by the 명절 rule). Everything else follows exp_e3_e4_reco.py.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e3_e4_reco import HOURS, TOL, day_type, load_commerce, load_obs, thresholds, windows  # noqa: E402

CATS = ["cat_유통", "cat_패션·뷰티"]
CANDIDATES = [(t, r) for t in (0.5, 0.6, 0.7) for r in ("all", "28d")]


def main():
    obs, com = load_obs(), load_commerce()
    com["shop"] = com[CATS].sum(axis=1)
    m, pidx, cols = train(horizons=[3])
    fc = live_eval(m, pidx, cols, horizons=[3], start="2026-08-01", require=("prof",), fill_gaps=True).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})
    places = sorted(set(com.poi) & set(obs.poi) & set(fc.poi))
    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    s_act = dict(zip(zip(com.poi, com.h), com.shop))

    hits, cover = [], []
    for p in places:
        op, cp = obs[obs.poi == p], com[com.poi == p].copy()
        cp["dtype"] = cp.h.dt.normalize().map(day_type)
        for d in pd.date_range("2026-08-01", "2026-09-29", freq="D"):
            dt = day_type(d)
            if dt == "myeongjeol":
                continue
            issue = d - pd.Timedelta(days=3)
            hist_o = op[(op.h < issue) & (op.h >= issue - pd.Timedelta(days=90))]
            hist_c = cp[(cp.h < issue) & (cp.h >= issue - pd.Timedelta(days=56))]
            if len(hist_o) < 24 * 14 or hist_c.empty:
                continue
            thr = thresholds(hist_o)
            offc = hist_c[(hist_c.dtype != "weekday") & hist_c.h.dt.hour.isin(HOURS)]
            p90 = offc.shop.quantile(.9)
            if not p90 or np.isnan(p90):
                continue
            Lp = {}
            for hr in HOURS:
                pop = fc_i.get((p, d + pd.Timedelta(hours=hr)))
                if pop is not None and not np.isnan(pop):
                    Lp[hr] = sum(pop >= t for t in thr)
            if len(Lp) < 8:
                continue
            for recency in ("all", "28d"):
                lo = issue - pd.Timedelta(days=28) if recency == "28d" else pd.Timestamp.min
                ph = cp[(cp.h < issue) & (cp.h >= lo) & (cp.dtype == dt)]
                if ph.empty:
                    continue
                a_pred = (ph.shop / p90).groupby(ph.h.dt.hour).mean()
                for t in (0.5, 0.6, 0.7):
                    lively = {hr for hr in Lp if a_pred.get(hr, 0.0) >= t}
                    for tol, (fn, allowed) in TOL.items():
                        score = {hr: fn(a_pred.get(hr, 0.0), Lp[hr]) for hr in Lp}
                        ws = windows(score, lively)
                        cover.append({"month": d.month, "cand": (t, recency), "covered": bool(ws)})
                        for w in ws:
                            for hr in w:
                                ts = d + pd.Timedelta(hours=hr)
                                La, sa = L_act.get((p, ts)), s_act.get((p, ts))
                                if La is None or sa is None or np.isnan(La):
                                    continue
                                hits.append({"month": d.month, "cand": (t, recency), "tol": tol,
                                             "lively_ok": sa / p90 >= 0.5, "crowd_ok": La <= allowed})
    h, c = pd.DataFrame(hits), pd.DataFrame(cover)
    summ = lambda month: pd.DataFrame({
        "lively_ok": h[h.month == month].groupby("cand").lively_ok.mean() * 100,
        "crowd_ok": h[h.month == month].groupby("cand").crowd_ok.mean() * 100,
        "coverage": c[c.month == month].groupby("cand").covered.mean() * 100,
        "n_hours": h[h.month == month].groupby("cand").size()})

    aug = summ(8)
    base_cov = aug.loc[[(0.5, "all")], "coverage"].iloc[0]
    aug["ok"] = (aug.lively_ok >= 85) & (aug.crowd_ok >= 80) & (aug.coverage >= 0.8 * base_cov)
    print("== selection on AUGUST (non-명절) ==")
    print(aug.round(1).to_string())
    ok = aug[aug.ok]
    if ok.empty:
        print("\nno candidate passes on August -> 쇼핑 stays 준비 중 (no test run)")
        return
    pick = ok.coverage.idxmax()
    print(f"\nselected on August: threshold {pick[0]}, profile {pick[1]}")
    sep = summ(9)
    print("\n== TEST on SEPTEMBER (non-명절): selected vs current rule ==")
    print(sep.loc[[pick, (0.5, "all")]].round(1).to_string())
    s = sep.loc[[pick]].iloc[0]
    verdict = s.lively_ok >= 85 and s.crowd_ok >= 80 and s.coverage >= 0.8 * sep.loc[[(0.5, "all")], "coverage"].iloc[0]
    print(f"\nSeptember verdict: {'PASS' if verdict else 'FAIL'}")
    print("\nper tolerance, selected, September:")
    hs = h[(h.month == 9) & (h.cand == pick)]
    print((hs.groupby("tol")[["lively_ok", "crowd_ok"]].mean() * 100).round(1).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
