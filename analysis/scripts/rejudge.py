"""Consistent re-judgement of every served claim (rules fixed before running).

Verdict rule (all items):
  PASS        point estimate meets the bar AND the whole place-bootstrap 95% CI meets it
  BORDERLINE  point meets the bar, CI crosses it
  FAIL        point misses the bar
Action: PASS -> on; BORDERLINE -> on + flagged for weekly re-judgement; FAIL -> off ("준비 중").
Bars are the pre-registered ones (구현설계서 7.1). Each user-selectable promise (purpose x tolerance)
is judged on its own; 'busy_ok' crowd promise is true by definition and is not judged.
E1 uses the pre-registered selection (rule threshold picked on August = 0.0).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import HOLIDAYS  # noqa: E402
from eval_fill_gap import D, live_hourly  # noqa: E402
from eval_ratio_live import calendar, live_eval, train  # noqa: E402
from exp_e1_tier_b import (HOURS, TEST_HOLS, buffers, dtype_of, oa_flow, shape_feats, st_flow,  # noqa: E402
                           station_places, train_ratio_v1b, weekly)

RNG = np.random.default_rng(0)
B = 1000
FOREIGN = ["명동", "동대문", "이태원", "홍대", "인사동", "남대문"]
OUT = []


def boot(groups, stat):
    keys = list(groups)
    return np.percentile([stat([groups[k] for k in RNG.choice(keys, len(keys))]) for _ in range(B)], [2.5, 97.5])


def verdict(name, point, ci, bar, higher_is_better=True, unit="%"):
    ok_point = point >= bar if higher_is_better else point <= bar
    ok_ci = (ci[0] >= bar) if higher_is_better else (ci[1] <= bar)
    v = "PASS" if ok_point and ok_ci else "BORDERLINE" if ok_point else "FAIL"
    OUT.append({"item": name, "point": round(point, 2), "ci_lo": round(ci[0], 2), "ci_hi": round(ci[1], 2),
                "bar": ("≥" if higher_is_better else "≤") + f"{bar}{unit}", "verdict": v})


def rate(groups_col):
    return lambda gs: np.concatenate(gs).mean() * 100


def e3():
    r = pd.read_csv(D / "e3c_rows.csv")
    f = r[((r.tol != "calm") & (r.rule == "final")) | ((r.tol == "calm") & (r.rule == "c0"))]
    names = pd.read_csv(D / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    f = f.assign(foreign=f.poi.map(lambda p: any(k in str(names.get(p, "")) for k in FOREIGN)))
    for sub, tag in [(f, ""), (f[f.foreign], " [외국인 많은 장소]")]:
        for (pur, tol), g in sub.groupby(["purpose", "tol"]):
            gl = {p: x.lively_ok.values for p, x in g.groupby("poi")}
            verdict(f"E3{tag} {pur}/{tol} 활발", g.lively_ok.mean() * 100, boot(gl, rate(None)), 85)
            if tol != "busy_ok":
                gc = {p: x.crowd_ok.values for p, x in g.groupby("poi")}
                verdict(f"E3{tag} {pur}/{tol} 혼잡 약속", g.crowd_ok.mean() * 100, boot(gc, rate(None)), 80)
    old = pd.read_csv(D / "e3_rows.csv")
    mj = old[(old.kind == "served") & (old.dtype == "myeongjeol")]
    for pur, g in mj.groupby("purpose"):
        gl = {p: x.lively_ok.values for p, x in g.groupby("poi")}
        verdict(f"E3 명절(추석) {pur} 활발", g.lively_ok.mean() * 100, boot(gl, rate(None)), 85)


def e1():
    pl, coords = station_places()
    buf = buffers(pl, coords)
    live = live_hourly().pivot(index="dt", columns="poi", values="live").asfreq("h")
    oa, st = oa_flow(buf), st_flow(pl)
    test = live[live.index >= "2026-08-01"]
    rs, lv, flows = {}, {}, {}
    for p in [p for p in pl if p in live.columns and p in oa.columns]:
        w_oa = weekly(oa[p])
        w_st = weekly(st[p]) if p in st.columns else None
        ag = w_oa.corr(w_st) if w_st is not None else np.nan
        ch = w_st if (w_st is not None and ag < 0.0) else w_oa  # pre-registered pick on August
        flows[p] = ch
        rs[p] = ch.corr(weekly(test[p]))
        tl = test[p].dropna()
        tl = tl[~tl.index.normalize().isin(HOLIDAYS) & tl.index.hour.isin(range(9, 23))]
        rel = ch / ch[ch.index.get_level_values(1).isin(HOURS)].quantile(.9)
        pr = rel.reindex(list(zip(dtype_of(tl.index), tl.index.hour))).values
        k = ~np.isnan(pr)
        lv[p] = (np.digitize(pr[k], [0.5, 0.9]) == np.digitize((tl / tl.quantile(.9)).values[k], [0.5, 0.9]))
    rsv = {p: np.array([v]) for p, v in rs.items()}
    verdict("E1 역세권 흐름 상관 중앙값", float(np.median(list(rs.values()))), boot(rsv, lambda gs: np.median(np.concatenate(gs))), 0.8, unit="")
    verdict("E1 크게 틀린 역 비율(r<0.3)", np.mean([v < .3 for v in rs.values()]) * 100,
            boot(rsv, lambda gs: np.mean(np.concatenate(gs) < .3) * 100), 10, higher_is_better=False)
    verdict("E1 3단계 일치율", np.concatenate(list(lv.values())).mean() * 100, boot(lv, rate(None)), 60)
    m, feats = train_ratio_v1b(exclude=set(rs))
    diff = {}
    for p, w in flows.items():
        tl = test[p].dropna()
        tl = tl[tl.index.normalize().isin(pd.to_datetime(TEST_HOLS)) & tl.index.hour.isin(range(9, 23))]
        nh = test[p].dropna()
        nh = nh[~nh.index.normalize().isin(HOLIDAYS) & nh.index.hour.isin(HOURS)]
        if tl.empty:
            continue
        live_rel = (tl / nh.quantile(.9)).values
        base_rel = w.reindex(list(zip(dtype_of(tl.index), tl.index.hour))).values / w[w.index.get_level_values(1).isin(HOURS)].quantile(.9)
        fcal = calendar(tl.index).reset_index(drop=True)
        for k_, v_ in shape_feats(w).items():
            fcal[k_] = v_
        adj = base_rel * np.exp(m.predict(fcal[feats]))
        ok = ~np.isnan(base_rel)
        diff[p] = np.stack([np.abs(adj - live_rel)[ok], np.abs(base_rel - live_rel)[ok], live_rel[ok]])
    red = lambda gs: (1 - sum(g[0].sum() for g in gs) / sum(g[1].sum() for g in gs)) * 100
    verdict("E1 역세권 공휴일 보정의 오차 감소율", red(list(diff.values())), boot(diff, red), 0)


def e2():
    m, pidx, cols = train(horizons=list(range(8)))
    for h in (3, 7):
        r = live_eval(m, pidx, cols, horizons=[h])
        hol, nor = r[r.hol], r[~r.hol]
        gh = {p: np.stack([np.abs(g.model - g.live), np.abs(g.prof - g.live), g.live]) for p, g in hol.groupby("poi")}
        gn = {p: np.stack([np.abs(g.model - g.live), np.abs(g.prof - g.live), g.live]) for p, g in nor.groupby("poi")}
        red = lambda gs: (1 - sum(g[0].sum() for g in gs) / sum(g[1].sum() for g in gs)) * 100
        worse = lambda gs: (sum(g[0].sum() for g in gs) - sum(g[1].sum() for g in gs)) / sum(g[2].sum() for g in gs) * 100
        verdict(f"E2 공휴일 오차 감소율 (h={h})", red(list(gh.values())), boot(gh, red), 10)
        verdict(f"E2 평소 오차 악화폭 %p (h={h})", worse(list(gn.values())), boot(gn, worse), 0.3, higher_is_better=False, unit="%p")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    e3()
    e2()
    e1()
    t = pd.DataFrame(OUT)
    t.to_csv(D / "rejudge.csv", index=False, encoding="utf-8-sig")
    print(t.to_string(index=False))
    print("\n", t.verdict.value_counts().to_dict())
