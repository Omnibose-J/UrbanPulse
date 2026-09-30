"""E14: recommended hours vs. what a person would do anyway (go at lunch / dinner).

Uses the per-hour table of E5 (data/e5_hours.parquet: A1 places, 2026-08-01..09-29, info as of D-3).
'추천' = hours rated 2 by rate(h, 0.15) in exp_e5_rating, i.e. the top windows of the day (proxy for the served windows).
Baselines: lunch 12-13h, dinner 19-20h, afternoon 15-16h, any hour 09-23h.
Truth per hour: fit = actually lively (activity/p90 >= 0.5) AND actual level within tolerance.
Output: data/e14_baseline.csv (purpose x tolerance x day type), printed table.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_e3_e4_reco import day_type  # noqa: E402
from exp_e5_rating import D, rate  # noqa: E402

BASE = {"추천": None, "점심 12~13시": [12, 13], "저녁 19~20시": [19, 20], "오후 15~16시": [15, 16], "아무 시간": list(range(9, 24))}


def main():
    h = pd.read_parquet(D / "e5_hours.parquet")
    h = h[(h.day >= "2026-08-01") & (h.day <= "2026-09-29") & h.truth]
    r = rate(h, 0.15)
    r["dtype"] = r.day.map(day_type)
    rows = []
    for (pu, tol), g in r.groupby(["purpose", "tol"]):
        if tol == "busy_ok":
            continue
        for dt, x in [("all", g)] + list(g.groupby("dtype")):
            row = {"purpose": pu, "tol": tol, "dtype": dt, "places": x.poi.nunique()}
            for name, hs in BASE.items():
                y = x[x.rating == 2] if hs is None else x[x.hr.isin(hs)]
                row[name] = round(y.fit.mean() * 100, 1)
            rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(D / "e14_baseline.csv", index=False, encoding="utf-8-sig")
    print(t.to_string(index=False))
    w = r[r.rating == 2]
    print("\n추천 시간의 분포 (%):", (w.hr.value_counts(normalize=True).sort_index() * 100).round(0).astype(int).to_dict())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
