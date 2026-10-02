"""Usual-flow profiles for tier B places. One transaction replaces `tier_b_profile`."""

from __future__ import annotations

import pandas as pd

from engine import db, settings
from engine.log import log
from engine.tierb.flows import norm, oa_flow, prefers_ridership, st_flow, weekly

JOB = "tier_b"
DAY_TYPE = {"wk": "weekday", "sat": "sat", "sun": "sun"}
FULL = pd.MultiIndex.from_product([list(DAY_TYPE), range(24)], names=["dtype", "hour"])


def _holidays() -> list[pd.Timestamp]:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    with db.connect(url) as conn:
        rows = conn.execute("select date from holidays").fetchall()
    return [pd.Timestamp(row[0]) for row in rows]


def _relative(chosen: pd.Series) -> pd.Series | None:
    aligned = chosen.reindex(FULL)
    if aligned.isna().any():
        return None
    daytime = aligned[aligned.index.get_level_values("hour").isin(range(9, 24))]
    scale = float(daytime.quantile(0.9))
    if scale <= 0:
        return None
    return aligned / scale


def _choose(oa: pd.Series | None, ridership: pd.Series | None, holidays) -> tuple[pd.Series | None, bool]:
    if oa is None:
        return None, False
    week_oa = weekly(oa.dropna(), holidays)
    if ridership is None:
        return _relative(week_oa), False
    week_st = weekly(ridership.dropna(), holidays)
    use_ridership = prefers_ridership(float(week_oa.corr(week_st)))
    return _relative(week_st if use_ridership else week_oa), use_ridership


def compute_profiles(places: list[tuple]) -> tuple[list[tuple], dict]:
    """places are (id, name, geom geojson). A station with no tract overlap is listed, not stored."""
    import geopandas as gpd
    from shapely.geometry import shape

    if not places:
        raise RuntimeError("no tier B places")
    holidays = _holidays()
    frame = gpd.GeoDataFrame(
        {"id": [row[0] for row in places]},
        geometry=[shape(row[2]) for row in places],
        crs=4326,
    ).to_crs(5179)
    groups = {row[0]: [norm(row[1])] for row in places}
    population = oa_flow(frame, key_name="id")
    ridership = st_flow(groups)
    rows: list[tuple] = []
    used = 0
    missing: list[str] = []
    for place_id, _name, _geom in places:
        oa_series = population[place_id] if place_id in population.columns else None
        ride_series = ridership[place_id] if place_id in ridership.columns else None
        relative, chose_ride = _choose(oa_series, ride_series, holidays)
        if relative is None:
            missing.append(place_id)
            continue
        if chose_ride:
            used += 1
        for (dtype, hour), value in relative.items():
            rows.append((place_id, DAY_TYPE[str(dtype)], int(hour), float(value)))
    detail = {
        "places": len(places),
        "profiles": len(rows) // 72,
        "used_ridership": used,
        "no_profile": missing,
    }
    return rows, detail


def write_profiles(rows: list[tuple], detail: dict) -> int:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    with db.job_run(url, JOB) as ctx:
        with db.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("delete from tier_b_profile where place_id like 'STN%'")
                cur.executemany(
                    "insert into tier_b_profile (place_id, day_type, hour, rel) values (%s, %s, %s, %s)",
                    rows,
                )
            from engine.tierb.stations import delete_unprofiled

            removed = delete_unprofiled(conn)
            detail = {**detail, "removed": removed}
            conn.commit()
        ctx["detail"] = detail
    log(
        JOB,
        "ok",
        places=detail["places"],
        profiles=detail["profiles"],
        used_ridership=detail["used_ridership"],
        no_profile=len(detail["no_profile"]),
        removed=detail["removed"],
    )
    return 0


def build_profiles() -> int:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    with db.connect(url) as conn:
        places = conn.execute(
            "select id, name, geom from places where tier = 'B' and geom is not null order by id"
        ).fetchall()
    rows, detail = compute_profiles(places)
    return write_profiles(rows, detail)
