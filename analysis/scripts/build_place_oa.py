"""Monthly 집계구 생활인구 (OA-14979) -> hourly area-weighted estimate for the 121 places.

For each month: download zip (unless present) -> keep only tracts touching a place ->
write data/place_oa/YYYYMM.parquet (poi, dt, est_oa) -> delete the zip if we downloaded it.
Empty daily files (header only) are logged, not fatal.
usage: python build_place_oa.py 202301 202607
"""
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_fill_gap import D  # noqa: E402
from eval_fill_gap_oa import oa_weights  # noqa: E402

OUT = D / "place_oa"
URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"


def months(a, b):
    return [p.strftime("%Y%m") for p in pd.period_range(pd.Period(a, "M"), pd.Period(b, "M"), freq="M")]


def download(ym, dst):
    body = urllib.parse.urlencode({"infId": "OA-14979", "seqNo": "", "seq": ym[2:], "infSeq": "1"}).encode()
    with urllib.request.urlopen(urllib.request.Request(URL, data=body), timeout=1800) as r, open(dst, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if dst.stat().st_size < 10_000_000:
        raise RuntimeError(f"{ym}: download too small ({dst.stat().st_size} bytes)")


def main(a, b):
    OUT.mkdir(exist_ok=True)
    ref = zipfile.ZipFile(D / "lp_oa/oa_202607.zip")
    codes = set(pd.read_csv(ref.open(ref.namelist()[0]), encoding="cp949", usecols=[3], dtype=str, index_col=False).iloc[:, 0])
    w, cover = oa_weights(codes)
    cover.to_csv(OUT / "cover.csv")
    keep = set(w.TOT_OA_CD)
    for ym in months(a, b):
        if (OUT / f"{ym}.parquet").exists():
            continue
        zp = D / f"lp_oa/oa_{ym}.zip"
        ours = not zp.exists()
        if ours:
            download(ym, zp)
        parts, empty = [], []
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if not n.lower().endswith(".csv"):
                    continue
                ch = pd.read_csv(z.open(n), encoding="cp949", usecols=[0, 1, 3, 4], dtype=str, index_col=False)
                if ch.empty:
                    empty.append(n)
                    continue
                ch.columns = ["day", "hour", "oa", "pop"]
                parts.append(ch[ch.oa.isin(keep)])
        df = pd.concat(parts)
        df["pop"] = pd.to_numeric(df["pop"].str.replace("*", "", regex=False), errors="coerce")
        df["dt"] = pd.to_datetime(df.day.str.strip().str[-8:], format="%Y%m%d") + pd.to_timedelta(df.hour.astype(int), unit="h")
        e = w.merge(df, left_on="TOT_OA_CD", right_on="oa")
        est = (e["pop"] * e.w).groupby([e.AREA_CD, e.dt]).sum().rename("est_oa").reset_index().rename(columns={"AREA_CD": "poi"})
        est.to_parquet(OUT / f"{ym}.parquet", index=False)
        if ours:
            zp.unlink()
        print(f"{ym}: files {len(z.namelist())}, empty {len(empty)}, days {est.dt.dt.normalize().nunique()}, rows {len(est):,}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:3])
