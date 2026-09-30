"""E3c: final-config recommendation backtest rows + one recorded retry of the 'calm' (최대한 한적하게) rule.

Final config (after E3/E3b): purposes all/food at activity threshold 0.5, shop at 0.6; 명절 excluded.
Rows are saved with place, day, month so the audit can bootstrap by place and compare months.

Pre-registered 'calm' candidates (activity gate unchanged):
  c0 current   : score a - 0.6*L
  c1 heavier   : score a - 1.0*L
  c2 hard-cap  : only hours with predicted L <= 1, score a - 0.6*L
  c3 cap-first : hours with predicted L == 0 if any exist, else L <= 1; score a - 0.6*L
Selection on August: calm crowd_ok >= 80% AND lively >= 85% in every purpose, coverage >= 80% of c0's,
  among passing pick highest mean coverage. Test the pick on September with the same bars.
Also records, for every scored place-day, the base rate: share of 09-23h with actual activity >= threshold.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e3_e4_reco import HOURS, TOL, day_type, load_commerce, load_obs, thresholds, windows  # noqa: E402

PURPOSE = {"all": (["pay"], 0.5), "food": (["cat_음식·음료"], 0.5), "shop": (["cat_유통", "cat_패션·뷰티"], 0.6)}
CALM = {"c0": ("score", 0.6), "c1": ("score", 1.0), "c2": ("cap1", 0.6), "c3": ("cap0first", 0.6)}


def main():
    obs, com = load_obs(), load_commerce()
    for k, (cols, _) in PURPOSE.items():
        com[k + "_v"] = com[cols].sum(axis=1)
    m, pidx, cols_ = train(horizons=[3])
    fc = live_eval(m, pidx, cols_, horizons=[3], start="2026-08-01", require=("prof",), fill_gaps=True).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})
    places = sorted(set(com.poi) & set(obs.poi) & set(fc.poi))
    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    v_act = {k: dict(zip(zip(com.poi, com.h), com[k + "_v"])) for k in PURPOSE}

    rows, cover, base = [], [], []
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
            Lp = {}
            for hr in HOURS:
                pop = fc_i.get((p, d + pd.Timedelta(hours=hr)))
                if pop is not None and not np.isnan(pop):
                    Lp[hr] = sum(pop >= t for t in thr)
            if len(Lp) < 8:
                continue
            ph = cp[(cp.h < issue) & (cp.dtype == dt)]
            if ph.empty:
                continue
            for purpose, (_, gate) in PURPOSE.items():
                p90 = offc[purpose + "_v"].quantile(.9)
                if not p90 or np.isnan(p90):
                    continue
                a_pred = (ph[purpose + "_v"] / p90).groupby(ph.h.dt.hour).mean()
                lively = {hr for hr in Lp if a_pred.get(hr, 0.0) >= gate}
                acts = [v_act[purpose].get((p, d + pd.Timedelta(hours=hr))) for hr in HOURS]
                acts = [a for a in acts if a is not None]
                if acts:
                    base.append({"poi": p, "month": d.month, "purpose": purpose, "base_rate": np.mean([a / p90 >= 0.5 for a in acts])})
                variants = [(t, "final") for t in TOL] + [("calm", c) for c in CALM if c != "c0"]
                for tol, rule in variants:
                    fn, allowed = TOL[tol]
                    allow = lively
                    if tol == "calm":
                        kind, w = CALM["c0" if rule == "final" else rule]
                        fn = lambda a, L, w=w: a - w * L
                        if kind == "cap1":
                            allow = {h for h in lively if Lp[h] <= 1}
                        elif kind == "cap0first":
                            z = {h for h in lively if Lp[h] == 0}
                            allow = z if z else {h for h in lively if Lp[h] <= 1}
                    score = {hr: fn(a_pred.get(hr, 0.0), Lp[hr]) for hr in Lp}
                    ws = windows(score, allow)
                    rule_name = "c0" if (tol == "calm" and rule == "final") else rule
                    cover.append({"poi": p, "month": d.month, "purpose": purpose, "tol": tol, "rule": rule_name, "covered": bool(ws)})
                    for win in ws:
                        for hr in win:
                            ts = d + pd.Timedelta(hours=hr)
                            La, va = L_act.get((p, ts)), v_act[purpose].get((p, ts))
                            if La is None or va is None or np.isnan(La):
                                continue
                            rows.append({"poi": p, "day": d.date(), "month": d.month, "dtype": dt, "purpose": purpose,
                                         "tol": tol, "rule": rule_name, "lively_ok": va / p90 >= 0.5, "crowd_ok": La <= allowed})
    pd.DataFrame(rows).to_csv(D / "e3c_rows.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(cover).to_csv(D / "e3c_cover.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(base).to_csv(D / "e3c_base.csv", index=False, encoding="utf-8-sig")
    r, c = pd.DataFrame(rows), pd.DataFrame(cover)
    calm_r, calm_c = r[r.tol == "calm"], c[c.tol == "calm"]

    def summ(month):
        g = calm_r[calm_r.month == month].groupby(["rule", "purpose"])
        t = pd.DataFrame({"lively": g.lively_ok.mean() * 100, "crowd": g.crowd_ok.mean() * 100,
                          "coverage": calm_c[calm_c.month == month].groupby(["rule", "purpose"]).covered.mean() * 100})
        return t
    aug = summ(8)
    c0cov = aug.xs("c0", level="rule").coverage
    ok = {}
    for rule in CALM:
        t = aug.xs(rule, level="rule")
        ok[rule] = bool(((t.lively >= 85) & (t.crowd >= 80) & (t.coverage >= 0.8 * c0cov)).all())
    print("== calm rule selection on AUGUST ==")
    print(aug.round(1).to_string())
    print("passes:", ok)
    passing = [k for k, v in ok.items() if v]
    if not passing:
        print("no calm candidate passes on August -> keep c0, record as unresolved")
        return
    pick = max(passing, key=lambda k: aug.xs(k, level="rule").coverage.mean())
    sep = summ(9)
    print(f"\nselected: {pick}\n== TEST on SEPTEMBER ==")
    print(sep.loc[[pick, "c0"]].round(1).to_string())
    t = sep.xs(pick, level="rule")
    c0s = sep.xs("c0", level="rule").coverage
    print("September verdict:", "PASS" if ((t.lively >= 85) & (t.crowd >= 80) & (t.coverage >= 0.8 * c0s)).all() else "FAIL")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
