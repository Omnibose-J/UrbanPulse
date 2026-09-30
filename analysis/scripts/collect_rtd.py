"""Pull hourly snapshots of seoul-rtd-collector (last ~31 days in HEAD) and keep only
population / forecast / weather / event fields as compact CSVs.

Output (data/):
  obs.csv   : snap_time, poi, name, ppltn_time, pmin, pmax, lvl, temp, precip, precpt_type, n_event
  fcst.csv  : snap_time, poi, ppltn_time, fcst_time, fmin, fmax, flvl
"""
import csv
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "imok-lena/seoul-rtd-collector"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/data"
OUT = Path(__file__).resolve().parent.parent / "data"


def gh_json(url):
    import os
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):  # unauthenticated API is capped at 60 calls/hour
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def list_hourly_files():
    days = [d["name"] for d in gh_json(f"https://api.github.com/repos/{REPO}/contents/data") if d["type"] == "dir"]
    picked = []
    for day in days:
        names = sorted(f["name"] for f in gh_json(f"https://api.github.com/repos/{REPO}/contents/data/{day}"))
        seen = set()
        for n in names:  # seoul_rtd_YYYYMMDD_HHMM.json -> first file per hour
            hh = n[-9:-7]
            if hh not in seen:
                seen.add(hh)
                picked.append(f"{day}/{n}")
    return picked


def fetch(path):
    import gzip
    req = urllib.request.Request(f"{RAW}/{path}", headers={"Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            return path, json.loads(body)
        except Exception as e:  # retry transient network errors, then surface
            err = e
    raise RuntimeError(f"{path}: {err}")


def extract(path, snap):
    snap_time = path.split("_")[-2] + path.split("_")[-1][:4]
    obs, fc = [], []
    for item in snap:
        if item.get("status") != "ok":
            continue
        c = item["data"].get("CITYDATA") or {}
        p = (c.get("LIVE_PPLTN_STTS") or {}).get("LIVE_PPLTN_STTS")
        if not p:
            continue
        w = (c.get("WEATHER_STTS") or {}).get("WEATHER_STTS") or {}
        ev = (c.get("EVENT_STTS") or {}).get("EVENT_STTS") or []
        obs.append([snap_time, c["AREA_CD"], c["AREA_NM"], p["PPLTN_TIME"], p["AREA_PPLTN_MIN"],
                    p["AREA_PPLTN_MAX"], p["AREA_CONGEST_LVL"], w.get("TEMP"), w.get("PRECIPITATION"),
                    w.get("PRECPT_TYPE"), len(ev) if isinstance(ev, list) else 1])
        for f in ((p.get("FCST_PPLTN") or {}).get("FCST_PPLTN") or []):
            fc.append([snap_time, c["AREA_CD"], p["PPLTN_TIME"], f["FCST_TIME"], f["FCST_PPLTN_MIN"],
                       f["FCST_PPLTN_MAX"], f["FCST_CONGEST_LVL"]])
    return obs, fc


def main():
    files = list_hourly_files()
    print(f"{len(files)} hourly snapshots", flush=True)
    with open(OUT / "obs.csv", "w", newline="", encoding="utf-8") as fo, \
         open(OUT / "fcst.csv", "w", newline="", encoding="utf-8") as ff:
        wo, wf = csv.writer(fo), csv.writer(ff)
        wo.writerow(["snap_time", "poi", "name", "ppltn_time", "pmin", "pmax", "lvl", "temp", "precip", "precpt_type", "n_event"])
        wf.writerow(["snap_time", "poi", "ppltn_time", "fcst_time", "fmin", "fmax", "flvl"])
        with ThreadPoolExecutor(8) as ex:
            for i, (path, snap) in enumerate(ex.map(fetch, files), 1):
                o, f = extract(path, snap)
                wo.writerows(o)
                wf.writerows(f)
                if i % 50 == 0:
                    print(f"{i}/{len(files)}", flush=True)
    print("done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
