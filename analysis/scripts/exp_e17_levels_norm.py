"""E17: two causes of "no pick" days and false "avoid" hours, and one candidate fix for each (fixed before running, 2026-10-01).

Observed on the served tables (2026-10-01): a handful of places have no recommendation on most weekdays.
  cause 1  level thresholds = lowest population ever labelled >= k (90 days). On September live data this rule
           reproduces Seoul's level 48.6% of the time, predicts a higher level 51.3% of the time, and calls 21.5%
           of hours "붐빔" when 3.2% were. An error-minimising boundary reaches 79.6% (over 9.0%, under 11.4%).
  cause 2  activity is normalised by the weekend+holiday p90. Weekend-heavy places never reach 0.5 on weekdays
           (every hour "closed"); weekday-heavy places exceed 0.5 all day on weekdays (the gate removes nothing).

Variants (2 x 2), everything else as E15 variant A (windows from fit hours; A1; 2026-08-01..09-29; 명절 excluded;
issue = D-3; gates all 0.5 / food 0.5 / shop 0.6; truth lively = actual a >= 0.5 under the variant's own normaliser):
  thresholds  min   : current rule
              split : per boundary k, the population cut that minimises (rows labelled >= k below it) +
                      (rows labelled < k at or above it) over the 90 days before issue; made monotone
  normaliser  off   : current rule, p90 over weekend+holiday hours 09-23 of the 56 days before issue
              class : p90 over the hours 09-23 of the target day's class (weekday | weekend+holiday) in those 56 days

Judgement of window promises: 7.0 rule, place bootstrap B=1000 seed 0; lively bar 85, crowd bar 80 (not busy_ok).
Reported, not judged: coverage (share of place-days with a window) overall and on weekdays; exact agreement of the
predicted level with the actual level; precision of "too_busy" cells (actual level above allowed), of "closed" cells
(actual a < 0.5), and the fit rate of "fit" cells (actually lively and within tolerance).

Decision rule:
  thresholds -> adopt `split` if, with the normaliser held at `off`, no combination served by the flag table gets a
                worse state than the table. Otherwise keep `min`.
  normaliser -> `class` changes what "lively" means (relative to the same kind of day), so it is a product decision,
                not only a statistical one: recommend it only if, with the adopted thresholds, no served combination
                gets a worse state AND weekday coverage rises. The user decides.
Caveat: August-September was already used to choose earlier rules; this is a re-judgement, not a fresh holdout.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e3_e4_reco import FOREIGN, HOURS, TOL, day_type, load_commerce, load_obs, thresholds, windows  # noqa: E402
from exp_e15_window_rule import FLAGS, RANK, judge  # noqa: E402

PURPOSE = {
    "all": (["pay"], 0.5),
    "food": (["cat_음식·음료"], 0.5),
    "shop": (["cat_유통", "cat_패션·뷰티"], 0.6),
}
VARIANTS = [(t, n) for t in ("min", "split") for n in ("off", "class")]


def thresholds_split(ob):
    out = []
    for k in (1, 2, 3):
        hi, lo = np.sort(ob.loc[ob.L >= k, "mid"].values), np.sort(ob.loc[ob.L < k, "mid"].values)
        if len(hi) == 0:
            out.append(np.inf)
        elif len(lo) == 0:
            out.append(hi.min())
        else:
            cand = np.unique(np.concatenate([hi, lo]))
            err = np.searchsorted(hi, cand, "left") + (len(lo) - np.searchsorted(lo, cand, "left"))
            out.append(cand[err.argmin()])
    return list(np.maximum.accumulate(out))


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

    rows, cover, cells, lvl = [], [], [], []
    for p in places:
        op, cp = obs[obs.poi == p], com[com.poi == p].copy()
        cp["dtype"] = cp.h.dt.normalize().map(day_type)
        for d in pd.date_range("2026-08-01", "2026-09-29", freq="D"):
            dt = day_type(d)
            if dt == "myeongjeol":
                continue
            wk = dt == "weekday"
            issue = d - pd.Timedelta(days=3)
            hist_o = op[(op.h < issue) & (op.h >= issue - pd.Timedelta(days=90))]
            hist_c = cp[(cp.h < issue) & (cp.h >= issue - pd.Timedelta(days=56))]
            if len(hist_o) < 24 * 14 or hist_c.empty:
                continue
            thr = {"min": thresholds(hist_o), "split": thresholds_split(hist_o)}
            in_hours = hist_c[hist_c.h.dt.hour.isin(HOURS)]
            norm_src = {
                "off": in_hours[in_hours.dtype != "weekday"],
                "class": in_hours[(in_hours.dtype == "weekday") == wk],
            }
            pops = {}
            for hr in HOURS:
                pop = fc_i.get((p, d + pd.Timedelta(hours=hr)))
                if pop is not None and not np.isnan(pop):
                    pops[hr] = pop
            if len(pops) < 8:
                continue
            ph = cp[(cp.h < issue) & (cp.dtype == dt)]
            if ph.empty:
                continue
            for tname in ("min", "split"):
                Lp = {hr: sum(pop >= t for t in thr[tname]) for hr, pop in pops.items()}
                for hr, L in Lp.items():
                    La = L_act.get((p, d + pd.Timedelta(hours=hr)))
                    if La is not None and not np.isnan(La):
                        lvl.append(
                            {
                                "thr": tname,
                                "exact": L == La,
                                "over": L > La,
                                "under": L < La,
                                "pred3": L == 3,
                                "act3": La == 3,
                            }
                        )
                for nname in ("off", "class"):
                    for purpose, (_, gate) in PURPOSE.items():
                        p90 = norm_src[nname][purpose + "_v"].quantile(0.9)
                        if not p90 or np.isnan(p90):
                            continue
                        a_pred = (ph[purpose + "_v"] / p90).groupby(ph.h.dt.hour).mean()
                        lively = {hr for hr in Lp if a_pred.get(hr, 0.0) >= gate}
                        for tol, (fn, allowed) in TOL.items():
                            score = {hr: fn(a_pred.get(hr, 0.0), Lp[hr]) for hr in Lp}
                            ws = windows(score, {h for h in lively if Lp[h] <= allowed})
                            key = {
                                "poi": p,
                                "purpose": purpose,
                                "tol": tol,
                                "thr": tname,
                                "norm": nname,
                                "weekday": wk,
                            }
                            cover.append({**key, "covered": bool(ws)})
                            win_hours = {h for w in ws for h in w}
                            for hr in Lp:
                                ts = d + pd.Timedelta(hours=hr)
                                La, va = L_act.get((p, ts)), v_act[purpose].get((p, ts))
                                if La is None or va is None or np.isnan(La):
                                    continue
                                liv, crowd = va / p90 >= 0.5, La <= allowed
                                reason = (
                                    "closed"
                                    if hr not in lively
                                    else "too_busy"
                                    if Lp[hr] > allowed
                                    else "fit"
                                )
                                cells.append({**key, "reason": reason, "lively": liv, "crowd": crowd})
                                if hr in win_hours:
                                    rows.append({**key, "lively_ok": liv, "crowd_ok": crowd})
    r, c, ce, lv = pd.DataFrame(rows), pd.DataFrame(cover), pd.DataFrame(cells), pd.DataFrame(lvl)
    for f in (r, c, ce):
        f["foreign"] = f.poi.map(lambda p: any(k in str(names.get(p, "")) for k in FOREIGN))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)

    print("== level agreement with Seoul's actual level (forecast at D-3, hours 09-23), % ==")
    print((lv.groupby("thr")[["exact", "over", "under", "pred3", "act3"]].mean() * 100).round(1).to_string())

    out = []
    for grp, sub, csub in [("all", r, c), ("foreign", r[r.foreign], c[c.foreign])]:
        for (pur, tol, tn, nn), g in sub.groupby(["purpose", "tol", "thr", "norm"]):
            lp, llo, lhi, lvd = judge(g, "lively_ok", 85)
            cp_, clo, chi, cvd = (
                (np.nan, np.nan, np.nan, "PASS") if tol == "busy_ok" else judge(g, "crowd_ok", 80)
            )
            worst = min(lvd, cvd, key=lambda v: {"FAIL": 0, "BORDERLINE": 1, "PASS": 2}[v])
            cs = csub[(csub.purpose == pur) & (csub.tol == tol) & (csub.thr == tn) & (csub.norm == nn)]
            out.append(
                {
                    "group": grp,
                    "purpose": pur,
                    "tol": tol,
                    "thr": tn,
                    "norm": nn,
                    "lively": lp,
                    "l_lo": llo,
                    "l_v": lvd,
                    "crowd": cp_,
                    "c_lo": clo,
                    "c_v": cvd,
                    "state": {"PASS": "on", "BORDERLINE": "reference", "FAIL": "off"}[worst],
                    "table": FLAGS[(grp, pur, tol)],
                    "cov": cs.covered.mean() * 100,
                    "cov_wd": cs[cs.weekday].covered.mean() * 100,
                    "cov_off": cs[~cs.weekday].covered.mean() * 100,
                }
            )
    t = pd.DataFrame(out)
    t.to_csv(D / "e17_verdict.csv", index=False, encoding="utf-8-sig")
    print("\n== window promises (state = this run; table = current flag file) ==")
    print(t.round(1).to_string(index=False))

    print("\n== decision ==")
    for tn, nn in VARIANTS:
        v = t[(t.thr == tn) & (t.norm == nn)]
        served = v[v.table != "off"]
        worse = served[served.state.map(RANK) < served.table.map(RANK)]
        better = v[v.state.map(RANK) > v.table.map(RANK)]
        a = v[v.group == "all"]
        print(
            f"{tn}/{nn}: served {len(served)}, worse {len(worse)}, better {len(better)}, "
            f"mean coverage all-A1 {a['cov'].mean():.1f} (weekday {a.cov_wd.mean():.1f}, off-day {a.cov_off.mean():.1f})"
        )
        for _, x in pd.concat([worse.assign(chg="worse"), better.assign(chg="better")]).iterrows():
            print(
                f"    {x.chg}: {x.group} {x.purpose}/{x.tol} {x.table} -> {x.state} (lively {x.lively:.1f}, crowd {x.crowd:.1f}, cov {x['cov']:.1f})"
            )

    print(
        "\n== hour cells, all A1, tolerance lively(적당), by variant: share and how often the label was true, % =="
    )
    s = ce[ce.tol == "lively"]
    g = s.groupby(["thr", "norm", "purpose", "reason"])
    cell = pd.DataFrame(
        {"n": g.size(), "actually_lively": g.lively.mean() * 100, "actually_within_tol": g.crowd.mean() * 100}
    )
    cell["share"] = cell.n / cell.groupby(level=[0, 1, 2]).n.transform("sum") * 100
    cell["label_true"] = np.where(
        cell.index.get_level_values("reason") == "closed",
        100 - cell.actually_lively,
        np.where(
            cell.index.get_level_values("reason") == "too_busy",
            100 - cell.actually_within_tol,
            (s.assign(ok=s.lively & s.crowd).groupby(["thr", "norm", "purpose", "reason"]).ok.mean() * 100),
        ),
    )
    print(cell[["share", "label_true"]].round(1).to_string())

    print("\n== places with a window on fewer than half of weekdays (purpose all, tol lively) ==")
    w = (
        c[(c.purpose == "all") & (c.tol == "lively") & c.weekday]
        .groupby(["thr", "norm", "poi"])
        .covered.mean()
    )
    for tn, nn in VARIANTS:
        x = w.loc[(tn, nn)]
        low = x[x < 0.5]
        print(
            f"{tn}/{nn}: {len(low)} of {len(x)} places: "
            + ", ".join(f"{names.get(p, p)} {v:.0%}" for p, v in low.sort_values().items())
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
