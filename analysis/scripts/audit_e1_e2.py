"""Reliability / validity audit for E1 (tier-B station estimate) and E2 (holiday forecast).

E1:
  - selection-rule threshold sensitivity {0.0..0.5}: pick on AUGUST truth (max median r subject to
    share r<0.3 <= 10%), test on SEPTEMBER truth. (pre-registered)
  - place-level bootstrap 95% CI of median r and share r<0.3 for the current rule (0.2), Aug-Sep truth
  - 3-level agreement vs chance: Cohen's kappa, and majority-class baseline
E2 (served model, h=3, unseen holidays 8/15, 8/17, 9/24-26, live truth):
  - place-level bootstrap 95% CI of holiday WAPE (baseline vs model) and of the relative reduction
  - per-day direction and leave-one-day-out reduction
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import HOLIDAYS  # noqa: E402
from eval_fill_gap import live_hourly  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e1_tier_b import HOURS, buffers, dtype_of, oa_flow, st_flow, station_places, weekly  # noqa: E402

RNG = np.random.default_rng(0)
B = 1000


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    po = (a == b).mean()
    cats = np.union1d(a, b)
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return (po - pe) / (1 - pe)


def boot(values_by_place, stat):
    keys = list(values_by_place)
    out = []
    for _ in range(B):
        s = RNG.choice(keys, len(keys), replace=True)
        out.append(stat([values_by_place[k] for k in s]))
    return np.percentile(out, [2.5, 97.5])


def e1():
    pl, coords = station_places()
    buf = buffers(pl, coords)
    live = live_hourly().pivot(index="dt", columns="poi", values="live").asfreq("h")
    oa, st = oa_flow(buf), st_flow(pl)
    places = [p for p in pl if p in live.columns and p in oa.columns]
    truth = {m: live[(live.index.month == m)] for m in (8, 9)}
    truth["both"] = live[live.index >= "2026-08-01"]
    prof = {}
    for p in places:
        w_oa = weekly(oa[p])
        w_st = weekly(st[p]) if p in st.columns else None
        prof[p] = (w_oa, w_st, w_oa.corr(w_st) if w_st is not None else np.nan)

    def score(thr, tkey):
        rs = {}
        for p, (w_oa, w_st, ag) in prof.items():
            ch = w_st if (w_st is not None and ag < thr) else w_oa
            rs[p] = ch.corr(weekly(truth[tkey][p]))
        return pd.Series(rs)

    rows = []
    for thr in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        for tk in (8, 9):
            s = score(thr, tk)
            rows.append({"thr": thr, "month": tk, "median_r": s.median(), "share_lt_0.3": (s < .3).mean() * 100,
                         "share_ge_0.8": (s >= .8).mean() * 100})
    t = pd.DataFrame(rows)
    aug = t[t.month == 8].set_index("thr")
    ok = aug[aug["share_lt_0.3"] <= 10]
    pick = ok.median_r.idxmax() if not ok.empty else None
    print("== E1 rule threshold sensitivity (select on Aug, test on Sep) ==")
    print(t.pivot(index="thr", columns="month").round(2).to_string())
    print(f"selected on August: {pick}")
    if pick is not None:
        sep = t[(t.month == 9) & (t.thr == pick)].iloc[0]
        cur = t[(t.month == 9) & (t.thr == 0.2)].iloc[0]
        print(f"September: selected thr {pick}: median r {sep.median_r:.2f}, r<0.3 {sep['share_lt_0.3']:.0f}% | current 0.2: median r {cur.median_r:.2f}, r<0.3 {cur['share_lt_0.3']:.0f}%")

    s = score(0.2, "both")
    ci_med = boot(s.to_dict(), lambda v: np.median(v))
    ci_bad = boot(s.to_dict(), lambda v: np.mean(np.array(v) < .3) * 100)
    print(f"\ncurrent rule (0.2), Aug-Sep: median r {s.median():.2f} [95% CI {ci_med[0]:.2f}, {ci_med[1]:.2f}], "
          f"r<0.3 {(s < .3).mean() * 100:.0f}% [95% CI {ci_bad[0]:.0f}, {ci_bad[1]:.0f}], n={len(s)}")
    print(f"month stability (current rule): Aug median {score(0.2, 8).median():.2f}, Sep median {score(0.2, 9).median():.2f}")

    # levels: kappa
    pred, act = [], []
    for p, (w_oa, w_st, ag) in prof.items():
        ch = w_st if (w_st is not None and ag < 0.2) else w_oa
        rel = ch / ch[ch.index.get_level_values(1).isin(HOURS)].quantile(.9)
        tl = truth["both"][p].dropna()
        tl = tl[~tl.index.normalize().isin(HOLIDAYS) & tl.index.hour.isin(range(9, 23))]
        pr = rel.reindex(list(zip(dtype_of(tl.index), tl.index.hour))).values
        ok_ = ~np.isnan(pr)
        pred += list(np.digitize(pr[ok_], [0.5, 0.9]))
        act += list(np.digitize((tl / tl.quantile(.9)).values[ok_], [0.5, 0.9]))
    pred, act = np.array(pred), np.array(act)
    print(f"levels: agreement {(pred == act).mean() * 100:.1f}%, majority baseline {pd.Series(act).value_counts(normalize=True).max() * 100:.1f}%, "
          f"Cohen's kappa {kappa(pred, act):.2f}")
    print("confusion (rows=actual, cols=pred):\n" + pd.crosstab(act, pred).to_string())


def e2():
    m, pidx, cols = train(horizons=[3])
    r = live_eval(m, pidx, cols, horizons=[3])
    h = r[r.hol]
    wape = lambda g, c: np.abs(g[c] - g.live).sum() / g.live.sum() * 100
    by_place = {p: g for p, g in h.groupby("poi")}

    def red(gs):
        g = pd.concat(gs)
        return (1 - wape(g, "model") / wape(g, "prof")) * 100
    ci = boot(by_place, red)
    ci_b = boot(by_place, lambda gs: wape(pd.concat(gs), "prof"))
    ci_m = boot(by_place, lambda gs: wape(pd.concat(gs), "model"))
    print(f"\n== E2 unseen holidays (h=3) ==\nbaseline {wape(h, 'prof'):.1f}% [{ci_b[0]:.1f}, {ci_b[1]:.1f}]  "
          f"model {wape(h, 'model'):.1f}% [{ci_m[0]:.1f}, {ci_m[1]:.1f}]  reduction {red([h]):.1f}% [95% CI {ci[0]:.1f}, {ci[1]:.1f}]")
    per = h.groupby("day").apply(lambda g: pd.Series({"base": wape(g, "prof"), "model": wape(g, "model")}), include_groups=False)
    per["better"] = per.model < per.base
    print(per.round(1).to_string())
    for d in per.index:
        g = h[h.day != d]
        print(f"leave out {d}: reduction {red([g]):.1f}%")
    places_better = pd.Series({p: wape(g, "model") < wape(g, "prof") for p, g in by_place.items()})
    print(f"places where model beats baseline on holidays: {places_better.mean() * 100:.0f}% of {len(places_better)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    e1()
    e2()
