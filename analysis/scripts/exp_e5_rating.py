"""E5: per-hour 3-step rating backtest (디자인 명세서 v2 §7). Rules fixed before running.

Rating per hour, per place x day x purpose x tolerance, from info known at D-3 (same inputs as E3/E3c):
  avoid (0): predicted activity < gate (A1 purpose gate: all/food 0.5, shop 0.6) OR predicted level beyond tolerance
             (calm: L >= 2, lively(=적당히): L == 3, busy_ok: never)
  good  (2): not avoid AND score >= week_top - margin AND score > 0
  ok    (1): otherwise
  score = recommendation score of 구현설계서 4.4; week_top = max score over non-avoid hours of target days [d-3, d+4]
  (each day at its own 3-day-ahead forecast; approximates the served 8-day list).
Truth per hour: lively = actual activity / p90 >= 0.5; crowd_ok = actual level <= allowed (calm 1, lively 2);
  fit = lively AND crowd_ok (busy_ok: fit = lively).

Pre-registered:
  candidates margin in {0.15, 0.25, 0.35}
  bars (same as E3): good hours lively >= 85%; good hours crowd_ok >= 80% (calm/lively only; busy_ok is true by definition)
  ordering: fit rate good > ok > avoid, and (good - avoid) fit gap > 0
  selection on AUGUST: among margins whose good-hour bars pass (point) in every SERVED combo (on/reference in the
    on/off table, non-foreign), pick the LARGEST margin (most good hours). None passes -> pick 0.15 and report.
  test on SEPTEMBER with the uniform verdict rule (rejudge.py: point + place-bootstrap 95% CI), per purpose x tolerance,
    all places and the foreign-heavy subset. 명절 excluded (A1 recommendations are off on 명절).
Outputs: data/e5_hours.csv, data/e5_verdict.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402
from exp_e3_e4_reco import HOURS, TOL, day_type, load_commerce, load_obs, thresholds  # noqa: E402
import rejudge as rj  # noqa: E402

PURPOSE = {"all": (["pay"], 0.5), "food": (["cat_음식·음료"], 0.5), "shop": (["cat_유통", "cat_패션·뷰티"], 0.6)}
MARGINS = [0.15, 0.25, 0.35]
TOO_BUSY = {"calm": lambda L: L >= 2, "lively": lambda L: L == 3, "busy_ok": lambda L: False}
ALLOWED = {"calm": 1, "lively": 2, "busy_ok": 3}
# on/off table (구현설계서 4.4), non-foreign A1
SERVED = {("all", "calm"), ("all", "lively"), ("all", "busy_ok"), ("food", "lively"), ("food", "busy_ok"),
          ("shop", "lively"), ("shop", "busy_ok")}


def build_hours():
    obs, com = load_obs(), load_commerce()
    for k, (cols, _) in PURPOSE.items():
        com[k + "_v"] = com[cols].sum(axis=1)
    m, pidx, cols_ = train(horizons=[3])
    fc = live_eval(m, pidx, cols_, horizons=[3], start="2026-07-29", require=("prof",), fill_gaps=True).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})
    places = sorted(set(com.poi) & set(obs.poi) & set(fc.poi))
    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    v_act = {k: dict(zip(zip(com.poi, com.h), com[k + "_v"])) for k in PURPOSE}
    tol_fn = {t: TOL[t][0] for t in TOL}
    rows = []
    for p in places:
        op, cp = obs[obs.poi == p], com[com.poi == p].copy()
        cp["dtype"] = cp.h.dt.normalize().map(day_type)
        for d in pd.date_range("2026-07-29", "2026-10-03", freq="D"):
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
                for tol in TOL:
                    for hr, L in Lp.items():
                        a = float(a_pred.get(hr, 0.0))
                        ts = d + pd.Timedelta(hours=hr)
                        La, va = L_act.get((p, ts)), v_act[purpose].get((p, ts))
                        rows.append({"poi": p, "day": d.normalize(), "purpose": purpose, "tol": tol, "hr": hr,
                                     "avoid": a < gate or TOO_BUSY[tol](L), "score": tol_fn[tol](a, L),
                                     "La": np.nan if La is None else La,
                                     "a_act": np.nan if va is None else va / p90})
    h = pd.DataFrame(rows)
    h["lively"] = h.a_act >= 0.5
    h["crowd_ok"] = h.La <= h.tol.map(ALLOWED)
    h["fit"] = h.lively & (h.crowd_ok | (h.tol == "busy_ok"))
    h["truth"] = h.La.notna() & h.a_act.notna()
    h.to_parquet(D / "e5_hours.parquet")
    return h


def rate(h, margin):
    ok = h[~h.avoid]
    day_top = ok.groupby(["poi", "purpose", "tol", "day"]).score.max().rename("dtop").reset_index()
    tops = []
    for (p, pu, t), g in day_top.groupby(["poi", "purpose", "tol"]):
        s = g.set_index("day").dtop
        wtop = [s[(s.index >= d - pd.Timedelta(days=3)) & (s.index <= d + pd.Timedelta(days=4))].max() for d in s.index]
        tops.append(pd.DataFrame({"poi": p, "purpose": pu, "tol": t, "day": s.index, "wtop": wtop}))
    top = pd.concat(tops)
    r = h.merge(top, on=["poi", "purpose", "tol", "day"], how="left")
    good = ~r.avoid & (r.score >= r.wtop - margin) & (r.score > 0)
    r["rating"] = np.where(r.avoid, 0, np.where(good, 2, 1))
    return r


def summary(r):
    t = r[r.truth]
    g = t[t.rating == 2].groupby(["purpose", "tol"])
    s = pd.DataFrame({"good_lively": g.lively.mean() * 100, "good_crowd": g.crowd_ok.mean() * 100,
                      "good_share": t.groupby(["purpose", "tol"]).rating.apply(lambda x: (x == 2).mean() * 100)})
    for k, n in [(2, "fit_good"), (1, "fit_ok"), (0, "fit_avoid")]:
        s[n] = t[t.rating == k].groupby(["purpose", "tol"]).fit.mean() * 100
    s.loc[s.index.get_level_values("tol") == "busy_ok", "good_crowd"] = np.nan
    return s


def passes(s):
    served = s[[ix in SERVED for ix in s.index]]
    ok = (served.good_lively >= 85) & (served.good_crowd.isna() | (served.good_crowd >= 80))
    return bool(ok.all())


def main():
    p = D / "e5_hours.parquet"
    h = pd.read_parquet(p) if p.exists() else build_hours()
    h = h[(h.day >= "2026-08-01") & (h.day <= "2026-09-29")]
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    foreign = {q for q in h.poi.unique() if any(k in str(names.get(q, "")) for k in rj.FOREIGN)}

    print("== selection on AUGUST (non-foreign) ==")
    aug_ok = {}
    for mg in MARGINS:
        r = rate(h, mg)
        s = summary(r[(r.day.dt.month == 8) & ~r.poi.isin(foreign)])
        aug_ok[mg] = passes(s)
        print(f"\nmargin {mg}: pass={aug_ok[mg]}\n{s.round(1).to_string()}")
    passing = [mg for mg in MARGINS if aug_ok[mg]]
    pick = max(passing) if passing else min(MARGINS)
    print(f"\nselected margin: {pick} ({'passed on August' if passing else 'NONE passed on August -> strictest'})")

    r = rate(h, pick)
    sep = r[(r.day.dt.month == 9) & r.truth]
    print("\n== TEST on SEPTEMBER ==")
    for sub, tag in [(sep[~sep.poi.isin(foreign)], ""), (sep[sep.poi.isin(foreign)], " [외국인 많은 장소]")]:
        print(f"\n{tag or '[일반 장소]'}\n{summary(sub).round(1).to_string()}")
        for (pu, tol), g in sub.groupby(["purpose", "tol"]):
            gg = g[g.rating == 2]
            if gg.empty:
                continue
            name = f"E5{tag} {pu}/{tol}"
            gl = {q: x.lively.values for q, x in gg.groupby("poi")}
            rj.verdict(f"{name} 좋아요 활발", gg.lively.mean() * 100, rj.boot(gl, rj.rate(None)), 85)
            if tol != "busy_ok":
                gc = {q: x.crowd_ok.values for q, x in gg.groupby("poi")}
                rj.verdict(f"{name} 좋아요 혼잡 약속", gg.crowd_ok.mean() * 100, rj.boot(gc, rj.rate(None)), 80)
            gap = {q: np.stack([x.fit.values, (x.rating == 2).values, (x.rating == 0).values]) for q, x in g.groupby("poi")}

            def gapf(gs):
                a = np.concatenate(gs, axis=1)
                gd, av = a[0][a[1] == 1], a[0][a[2] == 1]
                return (gd.mean() - av.mean()) * 100 if len(gd) and len(av) else np.nan
            rj.verdict(f"{name} 좋아요-피하세요 실제 적합 차이 %p", gapf(list(gap.values())), rj.boot(gap, gapf), 0, unit="%p")
    v = pd.DataFrame(rj.OUT)
    v.to_csv(D / "e5_verdict.csv", index=False, encoding="utf-8-sig")
    print("\n" + v.to_string(index=False))
    print("\n", v.verdict.value_counts().to_dict())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
