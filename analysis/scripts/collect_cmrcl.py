"""Commerce activity (LIVE_CMRCL_STTS, card payments) per place, hourly, weekend/holiday days only.
Answers "is the place actually open/lively at that hour?" alongside the crowd level.

Sources: HEAD files (last ~31 days) + recovered history (data/hist_files.txt).
Output : data/cmrcl.csv  snap_time, poi, cmrcl_time, lvl, pay_cnt, amt_min, cat_<대분류> payment counts
"""
import csv
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import collect_rtd as c
from collect_rtd_history import _fetch

EXTRA_OFF = {"20260524", "20260525", "20260603", "20260606", "20260815", "20260817", "20260924", "20260925", "20260926"}
CATS = ["음식·음료", "유통", "패션·뷰티", "여가·오락", "생활서비스", "의료·건강", "교육", "숙박"]


def offday(ymd):
    return ymd in EXTRA_OFF or pd.Timestamp(ymd).dayofweek >= 5


def targets(rest=False):
    """rest=False: weekend/holiday days from hist_files.txt + HEAD (the original cmrcl.csv).
    rest=True : everything cmrcl.csv lacks - weekdays from those sources, plus ALL days of
                hist_files_aug.txt (Aug 1-19 was never collected)."""
    want = (lambda ymd: not offday(ymd)) if rest else offday
    items, seen = [], set()
    lists = [("hist_files.txt", want)] + ([("hist_files_aug.txt", lambda ymd: True)] if rest else [])
    for fname, keep in lists:
        rows = (l.split() for l in open(c.OUT / fname, encoding="utf-8") if l.strip())
        for commit, path in sorted(rows, key=lambda r: r[1]):
            key = path[:-7]
            if key not in seen and keep(path.split("/")[1]):
                seen.add(key)
                items.append((commit, path))
    for p in c.list_hourly_files():
        if want(p.split("/")[0]) and f"data/{p}"[:-7] not in seen:
            items.append(("main", f"data/{p}"))
    return items


def extract(path, snap):
    snap_time = path.split("_")[-2] + path.split("_")[-1][:4]
    rows = []
    for item in snap:
        if item.get("status") != "ok":
            continue
        cd = item["data"].get("CITYDATA") or {}
        m = cd.get("LIVE_CMRCL_STTS")
        if not isinstance(m, dict) or not m.get("CMRCL_TIME"):
            continue
        cats = dict.fromkeys(CATS, 0)
        rsb = m.get("CMRCL_RSB")
        lst = rsb.get("CMRCL_RSB") if isinstance(rsb, dict) else None
        lst = [lst] if isinstance(lst, dict) else (lst if isinstance(lst, list) else [])  # single entry comes unwrapped
        for r in lst:
            if isinstance(r, dict) and r.get("RSB_LRG_CTGR") in cats:
                cats[r["RSB_LRG_CTGR"]] += int(r.get("RSB_SH_PAYMENT_CNT") or 0)
        rows.append([snap_time, cd["AREA_CD"], m["CMRCL_TIME"], m.get("AREA_CMRCL_LVL"), m.get("AREA_SH_PAYMENT_CNT"),
                     m.get("AREA_SH_PAYMENT_AMT_MIN")] + [cats[k] for k in CATS])
    return rows


def main(mode=""):  # mode "rest" -> cmrcl_rest.csv (see targets)
    items = targets(rest=(mode == "rest"))
    print(f"{len(items)} hourly snapshots ({mode or 'offday'})", flush=True)
    with open(c.OUT / ("cmrcl_rest.csv" if mode == "rest" else "cmrcl.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["snap_time", "poi", "cmrcl_time", "lvl", "pay_cnt", "amt_min"] + [f"cat_{k}" for k in CATS])
        with ThreadPoolExecutor(6) as ex:
            for i, (path, snap) in enumerate(ex.map(lambda it: _fetch(*it), items), 1):
                w.writerows(extract(path, snap))
                if i % 100 == 0:
                    print(f"{i}/{len(items)}", flush=True)
    print("done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:2])
