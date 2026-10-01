"""Tier B flows, ported number for number from the frozen research script.

Holidays are passed in (the `holidays` table). This module does not import `analysis`.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from engine import settings

RADIUS = 250


def data_root() -> Path:
    return settings.REPO_ROOT / "analysis" / "data"


def station_groups() -> tuple[dict[str, list[str]], pd.DataFrame]:
    """Live places whose name contains a station, and the mean coordinate of each station."""
    names = pd.read_csv(data_root() / "fill_gap_by_place.csv", encoding="utf-8-sig", index_col=0).AREA_NM
    stations = pd.read_csv(data_root() / "subway" / "stations.csv")
    stations["n"] = stations.BLDN_NM.map(norm)
    coords = stations.groupby("n")[["LAT", "LOT"]].mean()
    groups: dict[str, list[str]] = {}
    for poi, name in names.items():
        parts = [norm(part) for part in re.split(r"[·,]", str(name)) if str(part).strip().endswith("역")]
        parts = [part for part in parts if part in coords.index]
        if parts:
            groups[str(poi)] = parts
    return groups, coords


def prefers_ridership(correlation: float) -> bool:
    """Ridership replaces the tract flow only when the two weeks disagree."""
    return correlation < 0.0


def norm(name: object) -> str:
    return re.sub(r"\(.*?\)|역$", "", str(name)).strip()


def dtype_of(index: pd.DatetimeIndex) -> np.ndarray:
    return np.where(index.dayofweek == 6, "sun", np.where(index.dayofweek == 5, "sat", "wk"))


def weekly(series: pd.Series, holidays) -> pd.Series:
    """Mean by day type and hour, after dropping holiday dates."""
    days = pd.to_datetime(list(holidays))
    kept = series[~series.index.normalize().isin(days)].dropna()
    grouped = kept.groupby([dtype_of(kept.index), kept.index.hour]).mean()
    grouped.index.names = ["dtype", "hour"]
    return grouped


def smooth_share(share: pd.DataFrame) -> pd.DataFrame:
    """Hour H is the mean of bins H-1 and H. Columns stay 0..23."""
    previous = share[[(hour - 1) % 24 for hour in range(24)]]
    return (share + previous.to_numpy()) / 2


def read_oa(codes: set[str], year_month: str) -> pd.DataFrame:
    archive = zipfile.ZipFile(data_root() / "lp_oa" / f"oa_{year_month}.zip")
    parts = []
    for name in archive.namelist():
        frame = pd.read_csv(
            archive.open(name), encoding="cp949", usecols=[0, 1, 3, 4], dtype=str, index_col=False
        )
        frame.columns = ["day", "hour", "oa", "pop"]
        parts.append(frame[frame.oa.isin(codes)])
    table = pd.concat(parts)
    table["pop"] = pd.to_numeric(table["pop"].str.replace("*", "", regex=False), errors="coerce")
    hours = pd.to_timedelta(table.hour.astype(int), unit="h")
    table["dt"] = pd.to_datetime(table.day, format="%Y%m%d") + hours
    return table[["dt", "oa", "pop"]]


def _geopandas():
    import geopandas as gpd

    return gpd


def buffers(keys, longitudes, latitudes, key_name: str = "poi"):
    """250 m circles in EPSG:5179, dissolved on `key_name`."""
    gpd = _geopandas()
    frame = gpd.GeoDataFrame(
        {key_name: list(keys)},
        geometry=gpd.points_from_xy(list(longitudes), list(latitudes)),
        crs=4326,
    )
    projected = frame.to_crs(5179)
    projected["geometry"] = projected.buffer(RADIUS)
    return projected.dissolve(key_name).reset_index()


def oa_flow(circles, key_name: str = "poi") -> pd.DataFrame:
    """Area-weighted tract population for 202605 and 202606. Columns are the dissolve keys."""
    gpd = _geopandas()
    archive = zipfile.ZipFile(data_root() / "lp_oa" / "oa_202606.zip")
    first = archive.namelist()[0]
    header = pd.read_csv(archive.open(first), encoding="cp949", usecols=[3], dtype=str, index_col=False)
    codes = set(header.iloc[:, 0])
    tracts = gpd.read_file(data_root() / "poi" / "oa2016.geojson").to_crs(5179)
    tracts = tracts[tracts.TOT_OA_CD.isin(codes)]
    tracts["oa_area"] = tracts.area
    overlap = gpd.overlay(
        circles[[key_name, "geometry"]],
        tracts[["TOT_OA_CD", "oa_area", "geometry"]],
        how="intersection",
    )
    overlap["w"] = overlap.area / overlap.oa_area
    population = pd.concat([read_oa(set(overlap.TOT_OA_CD), month) for month in ("202605", "202606")])
    joined = overlap.merge(population, left_on="TOT_OA_CD", right_on="oa")
    weighted = joined["pop"] * joined.w
    return weighted.groupby([joined[key_name], joined.dt]).sum().unstack(0)


def st_flow(groups: dict[str, list[str]]) -> pd.DataFrame:
    """Daily ridership times the May-June hourly share. Keys of `groups` become columns."""
    root = data_root() / "subway"
    daily = pd.concat(
        [
            pd.read_csv(root / f"day_{code}.csv", encoding="utf-8-sig", index_col=False)
            for code in (153, 154, 155)
        ]
    )
    daily["st"] = daily["역명"].map(norm)
    daily["d"] = pd.to_datetime(daily["사용일자"].astype(str))
    daily = (
        daily.drop_duplicates(["d", "노선명", "역명"])
        .groupby(["st", "d"])[["승차총승객수", "하차총승객수"]]
        .sum()
        .sum(axis=1)
    )
    monthly = pd.read_csv(root / "hourly_month_2026.csv")
    monthly = monthly[monthly.USE_MM.isin([202605, 202606])].sort_values("JOB_YMD")
    monthly = monthly.drop_duplicates(["USE_MM", "SBWY_ROUT_LN_NM", "STTN"], keep="last")
    monthly["st"] = monthly.STTN.map(norm)
    hourly = pd.DataFrame(
        {
            hour: monthly[[f"HR_{hour}_GET_ON_NOPE", f"HR_{hour}_GET_OFF_NOPE"]].sum(axis=1)
            for hour in range(24)
        }
    ).assign(st=monthly.st)
    hourly = hourly.groupby("st").sum()
    share = smooth_share(hourly.div(hourly.sum(axis=1), axis=0))
    columns = {}
    for key, stations in groups.items():
        parts = []
        for station in stations:
            if station not in share.index or station not in daily.index.get_level_values(0):
                continue
            totals = daily.xs(station, level=0)
            index = pd.date_range(totals.index.min(), totals.index.max() + pd.Timedelta(hours=23), freq="h")
            values = totals.reindex(index.normalize()).to_numpy() * share.loc[station].to_numpy()[index.hour]
            parts.append(pd.Series(values, index=index))
        if parts:
            columns[key] = sum(parts)
    return pd.DataFrame(columns)
