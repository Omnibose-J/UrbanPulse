"""E3 + E4 (구현설계서 7.1): does the served recommendation keep its promise?

For every A1 place (live + commerce) and target day D in 2026-08-01..09-29, build the
recommendation exactly as served, using only what was known at issue time I = D - 3 days:
  - predicted level  : serve-form forecast at h=3 (live 3-week avg x calendar ratio, model
                       trained on proxy through 2026-07) mapped with level thresholds fitted
                       on live obs in the 90 days before I
  - activity profile : lively_profile by day type (평일/주말/공휴일/명절) from commerce before I;
                       a_cat = category payments / place p90 over weekend+holiday 09-23h, 8 weeks before I
  - windows          : 구현설계서 §4.4 scores, 1-2h windows, up to 3 non-overlapping
Score against what actually happened at the recommended hours:
  lively_ok : actual a_cat >= 0.5 (same normalisation as issue time)
  crowd_ok  : actual Seoul level <= allowed (한적 1, 적당 2, 붐벼도 3)
Frozen pass bars: lively_ok >= 85% per purpose, crowd_ok >= 80%; 추석 judged separately.
Naive comparison: "quietest predicted hours" ignoring activity.
명절 profile does not exist before 추석 2026 -> two variants: use 공휴일 profile / no recommendation.
E4: same metrics for foreign-heavy places + payments per person.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import BIG, HOLIDAYS, WIN  # noqa: E402
from eval_fill_gap import D  # noqa: E402
from eval_ratio_live import live_eval, train  # noqa: E402

LV = {"여유": 0, "보통": 1, "약간 붐빔": 2, "붐빔": 3}
PURPOSE = {"food": ["cat_음식·음료"], "shop": ["cat_유통", "cat_패션·뷰티"], "all": ["pay"]}
TOL = {"calm": (lambda a, L: a - 0.6 * L, 1), "lively": (lambda a, L: a - 0.5 * abs(L - 1), 2),
       "busy_ok": (lambda a, L: a - 0.2 * max(L - 2, 0), 3)}
FOREIGN = ["명동", "동대문", "이태원", "홍대", "인사동", "남대문"]
HOURS = range(9, 24)
MYEONGJEOL = set()
for s in list(BIG["seol"]) + list(BIG["chuseok"]):
    MYEONGJEOL |= {(s + pd.Timedelta(days=o)).date() for o in range(0, 3)}  # the 3 holiday days


def day_type(d):
    d = pd.Timestamp(d).date()
    if d in MYEONGJEOL:
        return "myeongjeol"
    if pd.Timestamp(d) in HOLIDAYS:
        return "holiday"
    return "weekend" if pd.Timestamp(d).dayofweek >= 5 else "weekday"


def load_obs():
    o = pd.concat([pd.read_csv(D / f, parse_dates=["ppltn_time"]) for f in ("obs_hist.csv", "obs_hist_aug.csv", "obs.csv")])
    o["h"] = o.ppltn_time.dt.round("h")
    o = o.drop_duplicates(["poi", "h"])
    o["mid"], o["L"] = (o.pmin + o.pmax) / 2, o.lvl.map(LV)
    return o[["poi", "h", "mid", "L"]]


def load_commerce():
    c = pd.concat([pd.read_csv(D / f, dtype={"cmrcl_time": str}) for f in ("cmrcl.csv", "cmrcl_rest.csv")])
    c["h"] = pd.to_datetime(c.cmrcl_time, format="%Y%m%d %H%M").dt.round("h")
    c = c.drop_duplicates(["poi", "h"])
    c["pay"] = pd.to_numeric(c.pay_cnt, errors="coerce")
    return c[["poi", "h", "pay", "cat_음식·음료", "cat_유통", "cat_패션·뷰티"]]


def thresholds(ob):
    """lowest midpoint ever labelled >= k (k=1..3) in the window; inf if never seen."""
    return [ob.loc[ob.L >= k, "mid"].min() if (ob.L >= k).any() else np.inf for k in (1, 2, 3)]


def windows(score, allowed_hours):
    """1-2h windows over consecutive allowed hours, greedy best non-overlapping, max 3."""
    cand = []
    hs = [h for h in HOURS if h in allowed_hours]
    for h in hs:
        cand.append(((h,), score[h]))
        if h + 1 in allowed_hours:
            cand.append(((h, h + 1), (score[h] + score[h + 1]) / 2))
    cand.sort(key=lambda x: -x[1])
    used, out = set(), []
    for w, s in cand:
        if used.isdisjoint(w):
            out.append(w)
            used |= set(w)
        if len(out) == 3:
            break
    return out


def main():
    obs, com = load_obs(), load_commerce()
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    a1 = sorted(set(com.poi) & set(obs.poi))

    m, pidx, cols = train(horizons=[3])
    fc = live_eval(m, pidx, cols, horizons=[3], start="2026-08-01", require=("prof",), fill_gaps=True).reset_index()
    fc = fc.rename(columns={fc.columns[0]: "ts"})  # the DatetimeIndex (target hour); 'h' column is the horizon
    places = [p for p in a1 if p in set(fc.poi)]
    print(f"A1 places {len(a1)}, with model forecast {len(places)}")

    fc_i = dict(zip(zip(fc.poi, fc.ts), fc.model))
    L_act = dict(zip(zip(obs.poi, obs.h), obs.L))
    act = {k: dict(zip(zip(com.poi, com.h), com[v].sum(axis=1))) for k, v in PURPOSE.items()}
    rows = []
    days = pd.date_range("2026-08-01", "2026-09-29", freq="D")
    for p in places:
        op, cp = obs[obs.poi == p], com[com.poi == p].copy()
        cp["dtype"] = cp.h.dt.normalize().map(day_type)
        for d in days:
            issue = d - pd.Timedelta(days=3)
            hist_o = op[(op.h < issue) & (op.h >= issue - pd.Timedelta(days=90))]
            hist_c = cp[(cp.h < issue) & (cp.h >= issue - pd.Timedelta(days=56))]
            if len(hist_o) < 24 * 14 or hist_c.empty:
                continue
            thr = thresholds(hist_o)
            offc = hist_c[(hist_c.dtype != "weekday") & hist_c.h.dt.hour.isin(HOURS)]
            p90 = {k: offc[v].sum(axis=1).quantile(.9) for k, v in PURPOSE.items()}
            dt = day_type(d)
            prof_src = {"myeongjeol": ["myeongjeol"], "holiday": ["holiday"], "weekend": ["weekend"], "weekday": ["weekday"]}[dt]
            for variant in (["as_holiday", "none"] if dt == "myeongjeol" else ["normal"]):
                use = ["holiday", "weekend"] if variant == "as_holiday" else prof_src
                if variant == "none":
                    continue  # design: no activity profile -> A1 recommendation withheld (counted as coverage loss)
                ph = cp[(cp.h < issue) & cp.dtype.isin(use)]
                if ph.empty:
                    continue
                for purpose, catcols in PURPOSE.items():
                    if p90[purpose] <= 0 or np.isnan(p90[purpose]):
                        continue
                    ph_a = (ph[catcols].sum(axis=1) / p90[purpose]).groupby(ph.h.dt.hour).mean()
                    Lp, a_pred = {}, {}
                    for hr in HOURS:
                        ts = d + pd.Timedelta(hours=hr)
                        pop = fc_i.get((p, ts))
                        if pop is None or np.isnan(pop):
                            continue
                        Lp[hr] = sum(pop >= t for t in thr)
                        a_pred[hr] = ph_a.get(hr, 0.0)
                    if len(Lp) < 8:
                        continue
                    lively_hours = {hr for hr in Lp if a_pred[hr] >= 0.5}
                    for tol, (fn, allowed) in TOL.items():
                        score = {hr: fn(a_pred[hr], Lp[hr]) for hr in Lp}
                        naive_score = {hr: -Lp[hr] for hr in Lp}
                        for kind, sc, allow in [("served", score, lively_hours), ("naive", naive_score, set(Lp))]:
                            for w in windows(sc, allow):
                                for hr in w:
                                    ts = d + pd.Timedelta(hours=hr)
                                    La, pa = L_act.get((p, ts)), act[purpose].get((p, ts))
                                    if La is None or pa is None or np.isnan(La):
                                        continue
                                    aa = pa / p90[purpose]
                                    rows.append({"poi": p, "day": d, "dtype": dt, "variant": variant, "purpose": purpose,
                                                 "tol": tol, "kind": kind, "lively_ok": aa >= 0.5, "crowd_ok": La <= allowed,
                                                 "n_windows_empty": len(lively_hours) == 0})
    r = pd.DataFrame(rows)
    r["foreign"] = r.poi.map(lambda p: any(k in str(names.get(p, "")) for k in FOREIGN))
    r.to_csv(D / "e3_rows.csv", index=False, encoding="utf-8-sig")

    agg = lambda g: pd.Series({"lively_ok": g.lively_ok.mean() * 100, "crowd_ok": g.crowd_ok.mean() * 100, "n_hours": len(g)})
    base = r[(r.kind == "served") & (r.dtype != "myeongjeol")]
    print("\n== E3 served, non-명절 days (Aug-Sep), by purpose ==")
    print(base.groupby("purpose").apply(agg, include_groups=False).round(1).to_string())
    print("\n== E3 served, by purpose x tolerance ==")
    print(base.groupby(["purpose", "tol"]).apply(agg, include_groups=False).round(1).to_string())
    print("\n== E3 served vs naive (quietest predicted hours), non-명절 ==")
    print(r[r.dtype != "myeongjeol"].groupby(["purpose", "kind"]).apply(agg, include_groups=False).round(1).to_string())
    print("\n== E3 by day type (served) ==")
    print(r[r.kind == "served"].groupby(["dtype", "purpose"]).apply(agg, include_groups=False).round(1).to_string())
    print("\n== E4 foreign-heavy vs other places (served, non-명절) ==")
    print(base.groupby(["foreign", "purpose"]).apply(agg, include_groups=False).round(1).to_string())

    # E4 payments per person
    j = obs.merge(com, on=["poi", "h"])
    j = j[j.h.dt.hour.isin(HOURS) & (j.h >= "2026-08-01")]
    ppp = (j.groupby("poi").pay.sum() / j.groupby("poi").mid.sum() * 1000).rename("pay_per_1000ppl")
    t = ppp.to_frame().assign(name=names.reindex(ppp.index).values)
    t["foreign"] = t.name.map(lambda s: any(k in str(s) for k in FOREIGN))
    print("\n== E4 card payments per 1,000 people-hours (median) ==")
    print(t.groupby("foreign").pay_per_1000ppl.median().round(2).to_string())
    print(t[t.foreign].sort_values("pay_per_1000ppl").round(2).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
