"""Monthly 행정동 생활인구 zips (data/lp/dong_YYYYMM.zip) -> data/lp_dong.parquet
columns: dt (hourly timestamp), dong (8-digit 행정동코드), pop (총생활인구수)"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parent.parent / "data"


def read_zip(p):
    with zipfile.ZipFile(p) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        raw = z.read(name)
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    from io import StringIO
    df = pd.read_csv(StringIO(text), usecols=[0, 1, 2, 3], dtype=str, index_col=False)
    df.columns = ["day", "hour", "dong", "pop"]
    df["day"] = df.day.str.strip().str.lstrip("?﻿")
    bad = ~df.day.str.fullmatch(r"\d{8}", na=False)
    if bad.any():
        print(f"  {p.name}: dropping {bad.sum()} malformed rows e.g. {df[bad].head(2).values.tolist()}")
        df = df[~bad].copy()
    df["pop"] = pd.to_numeric(df["pop"].str.replace("*", "", regex=False), errors="coerce")
    df["dt"] = pd.to_datetime(df.day.str.strip(), format="%Y%m%d") + pd.to_timedelta(df.hour.astype(int), unit="h")
    return df[["dt", "dong", "pop"]].astype({"dong": "int32", "pop": "float32"})


def main():
    parts = []
    for p in sorted((D / "lp").glob("dong_*.zip")):
        parts.append(read_zip(p))
        print(p.name, len(parts[-1]), flush=True)
    df = pd.concat(parts).drop_duplicates(["dt", "dong"]).sort_values(["dong", "dt"])
    df.to_parquet(D / "lp_dong.parquet", index=False)
    print(f"rows {len(df):,} dongs {df.dong.nunique()} {df.dt.min()} ~ {df.dt.max()}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
