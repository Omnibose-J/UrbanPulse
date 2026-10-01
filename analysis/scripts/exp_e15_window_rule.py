"""E15 + E16: does the window rule written into SOW-M3 keep the E3 promises? (fixed before running, 2026-10-01)

SOW-M3 narrowed the research rule so that every window hour is a "가도 괜찮아요" hour (invariant 9).
For 'calm' this is the E3c candidate c2, which failed on August, so the flag table cannot be assumed to carry over.

Variants (everything else as exp_e3c_calm.py: A1 places, 2026-08-01..09-29, 명절 excluded, issue = D-3,
gates all 0.5 / food 0.5 / shop 0.6, truth = actual a >= 0.5, crowd truth = actual level <= allowed):
  O research : windows over lively hours, score penalises crowding
  A sow      : windows over lively hours with predicted level <= allowed (calm 1, lively 2, busy_ok 3)
  B drop     : windows as O, then drop every window containing an hour with predicted level > allowed
Judgement: 7.0 rule (place bootstrap B=1000, seed 0, 95% CI). lively bar 85, crowd bar 80 (not for busy_ok);
combination state = worse of the two (PASS on, BORDERLINE reference, FAIL off). Groups: all A1, foreign-heavy.
Coverage = share of (place, day) with at least one window; reported, not judged.
Decision rule: keep A if no combination that the flag table serves (on/reference) gets a worse state under A.
Otherwise take B if it satisfies that. Otherwise keep the variant with more served combinations (tie -> A) and
set the flag table to that variant's states.

E16 (home list "지금 열려 있고 한산한 곳"): among A1 place-hours 09-23 with actual level <= 1 and expected
activity (profile, purpose all) >= 0.5, share with actual a >= 0.5. Bar 85, same judgement. Baseline: the same
share without the expected-activity filter. The profile here is the D-3 one (the served list uses D-0; D-3 is
the conservative side).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e3_e4_reco import FOREIGN, HOURS, TOL, day_type, load_commerce, load_obs, thresholds, windows  # noqa: E402

PURPOSE = {
    "all": (["pay"], 0.5),
    "food": (["cat_음식·음료"], 0.5),
    "shop": (["cat_유통", "cat_패션·뷰티"], 0.6),
}
FLAGS = {  # served states in SOW-M3 (group, purpose, tol) -> state
    ("all", "all", "calm"): "reference",
    ("all", "all", "lively"): "on",
    ("all", "all", "busy_ok"): "on",
    ("all", "food", "calm"): "off",
    ("all", "food", "lively"): "on",
    ("all", "food", "busy_ok"): "on",
    ("all", "shop", "calm"): "off",
    ("all", "shop", "lively"): "reference",
    ("all", "shop", "busy_ok"): "on",
    ("foreign", "all", "calm"): "off",
    ("foreign", "all", "lively"): "reference",
    ("foreign", "all", "busy_ok"): "reference",
    ("foreign", "food", "calm"): "off",
    ("foreign", "food", "lively"): "reference",
    ("foreign", "food", "busy_ok"): "reference",
    ("foreign", "shop", "calm"): "off",
    ("foreign", "shop", "lively"): "off",
    ("foreign", "shop", "busy_ok"): "reference",
}
RANK = {"off": 0, "reference": 1, "on": 2}
RNG = np.random.default_rng(0)
B = 1000


def boot(groups):
    keys = list(groups)
    return np.percentile(
        [np.concatenate([groups[k] for k in RNG.choice(keys, len(keys))]).mean() * 100 for _ in range(B)],
        [2.5, 97.5],
    )


def judge(g, col, bar):
    point = g[col].mean() * 100
    lo, hi = boot({p: x[col].values for p, x in g.groupby("poi")})
    v = "PASS" if point >= bar and lo >= bar else "BORDERLINE" if point >= bar else "FAIL"
    return point, lo, hi, v


def main():
    obs, com = load_obs(), load_commerce()
    for k, (cols, _) in PURPOSE.items():
        com[k + "_v"] = com[cols].sum(axis=1)
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    m, pidx, cols_ = train(horizons=[3])
    fc = live_eval(
        m, pidx, cols_, horizons=[3], start="2026-08-01", require=("prof",), fill_gaps=True
    ).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})
    places = sorted(set(com.poi) & set(obs.poi) & set(fc.poi))
    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    v_act = {k: dict(zip(zip(com.poi, com.h), com[k + "_v"])) for k in PURPOSE}

    rows, cover, home = [], [], []
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
                p90 = offc[purpose + "_v"].quantile(0.9)
                if not p90 or np.isnan(p90):
                    continue
                a_pred = (ph[purpose + "_v"] / p90).groupby(ph.h.dt.hour).mean()
                lively = {hr for hr in Lp if a_pred.get(hr, 0.0) >= gate}
                if purpose == "all":
                    for hr in HOURS:
                        ts = d + pd.Timedelta(hours=hr)
                        La, va = L_act.get((p, ts)), v_act["all"].get((p, ts))
                        if La is None or va is None or np.isnan(La) or La > 1:
                            continue
                        home.append(
                            {"poi": p, "expected": a_pred.get(hr, 0.0) >= 0.5, "lively_ok": va / p90 >= 0.5}
                        )
                for tol, (fn, allowed) in TOL.items():
                    score = {hr: fn(a_pred.get(hr, 0.0), Lp[hr]) for hr in Lp}
                    w_o = windows(score, lively)
                    variants = {
                        "O": w_o,
                        "A": windows(score, {h for h in lively if Lp[h] <= allowed}),
                        "B": [w for w in w_o if all(Lp[h] <= allowed for h in w)],
                    }
                    for var, ws in variants.items():
                        cover.append(
                            {"poi": p, "purpose": purpose, "tol": tol, "var": var, "covered": bool(ws)}
                        )
                        for rank, win in enumerate(ws):
                            for hr in win:
                                ts = d + pd.Timedelta(hours=hr)
                                La, va = L_act.get((p, ts)), v_act[purpose].get((p, ts))
                                if La is None or va is None or np.isnan(La):
                                    continue
                                rows.append(
                                    {
                                        "poi": p,
                                        "day": d.date(),
                                        "purpose": purpose,
                                        "tol": tol,
                                        "var": var,
                                        "rank": rank,
                                        "hour": hr,
                                        "lively_ok": va / p90 >= 0.5,
                                        "crowd_ok": La <= allowed,
                                    }
                                )
    r, c, hm = pd.DataFrame(rows), pd.DataFrame(cover), pd.DataFrame(home)
    for f in (r, c, hm):
        f["foreign"] = f.poi.map(lambda p: any(k in str(names.get(p, "")) for k in FOREIGN))
    r.to_csv(D / "e15_rows.csv", index=False, encoding="utf-8-sig")

    out = []
    for grp, sub, csub in [("all", r, c), ("foreign", r[r.foreign], c[c.foreign])]:
        for (pur, tol, var), g in sub.groupby(["purpose", "tol", "var"]):
            lp, llo, lhi, lv = judge(g, "lively_ok", 85)
            if tol == "busy_ok":
                cp_, clo, chi, cv = np.nan, np.nan, np.nan, "PASS"
            else:
                cp_, clo, chi, cv = judge(g, "crowd_ok", 80)
            worst = min(lv, cv, key=lambda v: {"FAIL": 0, "BORDERLINE": 1, "PASS": 2}[v])
            state = {"PASS": "on", "BORDERLINE": "reference", "FAIL": "off"}[worst]
            cov = csub[(csub.purpose == pur) & (csub.tol == tol) & (csub["var"] == var)].covered.mean() * 100
            out.append(
                {
                    "group": grp,
                    "purpose": pur,
                    "tol": tol,
                    "var": var,
                    "lively": lp,
                    "l_lo": llo,
                    "l_hi": lhi,
                    "l_v": lv,
                    "crowd": cp_,
                    "c_lo": clo,
                    "c_hi": chi,
                    "c_v": cv,
                    "state": state,
                    "table": FLAGS[(grp, pur, tol)],
                    "coverage": cov,
                    "n_hours": len(g),
                }
            )
    t = pd.DataFrame(out)
    t.to_csv(D / "e15_verdict.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    print("== E15 verdicts (state = this run, table = SOW-M3 flag file) ==")
    print(t.round(1).to_string(index=False))
    print("\n== E15 decision ==")
    for var in ("O", "A", "B"):
        v = t[t["var"] == var]
        served = v[v.table != "off"]
        worse = served[served.state.map(RANK) < served.table.map(RANK)]
        print(
            f"{var}: served combos {len(served)}, worse than table {len(worse)}, on/reference under this variant {(v.state != 'off').sum()}"
        )
        if len(worse):
            print(
                worse[["group", "purpose", "tol", "state", "table", "lively", "crowd", "coverage"]]
                .round(1)
                .to_string(index=False)
            )
    print("\n== first-pick hour distribution, variant A, all A1 (share %) ==")
    fp = r[(r["var"] == "A") & (r["rank"] == 0)]
    print((fp.groupby("hour").size() / len(fp) * 100).round(1).to_string())

    print("\n== E16 home list: actual lively among actual-level<=1 hours ==")
    for grp, sub in [("all", hm), ("non-foreign", hm[~hm.foreign])]:
        e = sub[sub.expected]
        point, lo, hi, v = judge(e, "lively_ok", 85)
        print(
            f"{grp}: expected>=0.5 -> {point:.1f}% (CI {lo:.1f}~{hi:.1f}) {v}, n={len(e):,}; "
            f"no filter -> {sub.lively_ok.mean() * 100:.1f}%, n={len(sub):,}; filter keeps {len(e) / len(sub) * 100:.1f}% of hours"
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
