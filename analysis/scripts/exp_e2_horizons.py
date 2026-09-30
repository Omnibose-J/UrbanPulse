"""E2 (구현설계서 7.1): calendar-ratio model trained on horizons 0-7, gated per horizon.

Gates (frozen before running, 구현설계서 §5):
  G1 holidays: model WAPE <= 0.9 x baseline WAPE (>= 10% lower)
  G2 normal (all non-holiday days incl. weekends): model WAPE - baseline WAPE <= 0.3 %p
Baseline = 3-week same-weekday average (weeks k>=1, k>=2 for h=7).
A: live truth, unseen holidays 8/15, 8/17, 9/24-26 (model trained on proxy through 2026-07)
B: proxy truth 2026-01..07 (model trained on proxy through 2025-12) - 설 + 5-6월 holidays
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_days_ahead import BIG, HOLIDAYS, WIN, load  # noqa: E402
from eval_ratio_live import calendar, live_eval, train  # noqa: E402

H = list(range(8))


def gates(sub_hol, sub_norm, pred="model", base="prof", truth="live"):
    w = lambda g, c: np.abs(g[c] - g[truth]).sum() / g[truth].sum() * 100
    rows = []
    for h in H:
        a, b = sub_hol[sub_hol.h == h], sub_norm[sub_norm.h == h]
        hb, hm, nb, nm = w(a, base), w(a, pred), w(b, base), w(b, pred)
        rows.append({"h": h, "hol_base": hb, "hol_model": hm, "G1": hm <= 0.9 * hb,
                     "norm_base": nb, "norm_model": nm, "G2": nm - nb <= 0.3, "n_hol": len(a)})
    t = pd.DataFrame(rows).set_index("h")
    t["PASS"] = t.G1 & t.G2
    return t


def part_a():
    m, pidx, cols = train(horizons=H)
    r = live_eval(m, pidx, cols, horizons=H)
    print(f"[A] live test {r.index.min()} ~ {r.index.max()}, places {r.poi.nunique()}")
    return gates(r[r.hol], r[~r.hol], truth="live")


def part_b():
    m, pidx, cols = train(horizons=H, until=pd.Timestamp("2025-12-31 23:00"))
    P = load("place").pivot(index="dt", columns="dong", values="pop").asfreq("h")
    places = [p for p in P.columns if p in pidx]
    P = P[places]
    test = P.index[(P.index >= "2026-01-01")]
    day = test.normalize()
    big = np.zeros(len(test), bool)
    for s in BIG["seol"]:
        big |= day.isin([s + pd.Timedelta(days=o) for o in WIN])
    hol_mask = day.isin(HOLIDAYS) | big
    cal = calendar(test).reset_index(drop=True)
    out = []
    for h in H:
        kmin = 1 if h < 7 else 2
        prof = pd.concat([P.shift(7 * 24 * k) for k in range(kmin, kmin + 3)]).groupby(level=0).mean().loc[test]
        for p in places:
            f = cal.copy()
            f["poi_i"], f["h"] = pidx[p], h
            d = pd.DataFrame({"act": P.loc[test, p].values, "prof": prof[p].values,
                              "ratio": np.exp(m.predict(f[cols])), "hol": hol_mask, "h": h})
            out.append(d.dropna())
    r = pd.concat(out)
    r["model"] = r.prof * r.ratio
    print(f"[B] proxy test 2026-01 ~ 07, places {len(places)}, holiday hours share {r.hol.mean():.1%}")
    return gates(r[r.hol], r[~r.hol], truth="act")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in [("A live, unseen holidays", part_a), ("B proxy 2026-01~07", part_b)]:
        t = fn()
        print(f"\n== E2 {name}: WAPE % per horizon (days) ==")
        print(t.round(2).to_string())
