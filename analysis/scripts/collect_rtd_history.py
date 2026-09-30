"""Recover older snapshots (deleted from HEAD) via their adding commit, hourly-sampled.

Input : data/hist_files.txt  lines "<commit> data/YYYYMMDD/seoul_rtd_YYYYMMDD_HHMM.json"
        (built with: git log --diff-filter=A --name-only on a blobless clone)
Output: data/obs_hist.csv, data/fcst_hist.csv (same columns as collect_rtd.py)
"""
import csv
import sys
from concurrent.futures import ThreadPoolExecutor

import collect_rtd as c

RAW_ROOT = f"https://raw.githubusercontent.com/{c.REPO}"


def main(tag=""):  # tag: e.g. "_aug" -> hist_files_aug.txt -> obs_hist_aug.csv
    rows = [l.split() for l in open(c.OUT / f"hist_files{tag}.txt", encoding="utf-8") if l.strip()]
    seen, picked = set(), []
    for commit, path in sorted(rows, key=lambda r: r[1]):
        key = path[:-7]  # .../seoul_rtd_YYYYMMDD_HH -> first file per hour
        if key not in seen:
            seen.add(key)
            picked.append((commit, path))
    print(f"{len(picked)} hourly snapshots", flush=True)

    with open(c.OUT / f"obs_hist{tag}.csv", "w", newline="", encoding="utf-8") as fo, \
         open(c.OUT / f"fcst_hist{tag}.csv", "w", newline="", encoding="utf-8") as ff:
        wo, wf = csv.writer(fo), csv.writer(ff)
        wo.writerow(["snap_time", "poi", "name", "ppltn_time", "pmin", "pmax", "lvl", "temp", "precip", "precpt_type", "n_event"])
        wf.writerow(["snap_time", "poi", "ppltn_time", "fcst_time", "fmin", "fmax", "flvl"])
        with ThreadPoolExecutor(8) as ex:
            for i, (path, snap) in enumerate(ex.map(lambda it: _fetch(*it), picked), 1):
                o, f = c.extract(path, snap)
                wo.writerows(o)
                wf.writerows(f)
                if i % 100 == 0:
                    print(f"{i}/{len(picked)}", flush=True)
    print("done")


def _fetch(commit, path):
    import gzip, json, urllib.request
    req = urllib.request.Request(f"{RAW_ROOT}/{commit}/{path}", headers={"Accept-Encoding": "gzip"})
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            return path, json.loads(body)
        except Exception as e:
            err = e
    raise RuntimeError(f"{path}: {err}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:2])
