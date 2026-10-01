"""One experimental place per subway station that is not already inside the 121 areas."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.jobs.load_places import GU_FIELD
from engine.log import log
from engine.tierb.flows import buffers, data_root, norm

JOB = "tier_b"
SHP = "analysis/data/poi/서울시 주요 121장소 영역/서울시 주요 121장소 영역.shp"
DONG = "analysis/data/poi/dong.geojson"
CATEGORY = "역세권"

_UPSERT = """
insert into places (
  id, tier, name, name_en, category, gu, lat, lon, geom, poi_code,
  station_codes, open_hours, foreign_heavy, serve_state, updated_at
) values (
  %(id)s, 'B', %(name)s, null, %(category)s, %(gu)s, %(lat)s, %(lon)s,
  %(geom)s, null, %(station_codes)s, null, false, 'experimental', now()
)
on conflict (id) do update set
  tier = excluded.tier,
  name = excluded.name,
  name_en = excluded.name_en,
  category = excluded.category,
  gu = excluded.gu,
  lat = excluded.lat,
  lon = excluded.lon,
  geom = excluded.geom,
  station_codes = excluded.station_codes,
  serve_state = excluded.serve_state,
  updated_at = now()
where places.tier is distinct from excluded.tier
   or places.name is distinct from excluded.name
   or places.name_en is distinct from excluded.name_en
   or places.category is distinct from excluded.category
   or places.gu is distinct from excluded.gu
   or places.lat is distinct from excluded.lat
   or places.lon is distinct from excluded.lon
   or places.geom is distinct from excluded.geom
   or places.station_codes is distinct from excluded.station_codes
   or places.serve_state is distinct from excluded.serve_state
"""


def covered(fraction: float) -> bool:
    """True when at least half of the station circle lies inside the 121 areas."""
    return fraction >= 0.5


def display_name(key: str, raw_names: list[str]) -> str:
    wanted = f"{key}역"
    if wanted in raw_names:
        return wanted
    ending = [name for name in raw_names if name.endswith("역")]
    return ending[0] if ending else wanted


def _geom_json(geom: Any) -> dict[str, Any]:
    from shapely.geometry import mapping

    return json.loads(json.dumps(mapping(geom)))


def _groups(table: pd.DataFrame) -> pd.DataFrame:
    frame = table.copy()
    frame["key"] = frame["BLDN_NM"].map(norm)
    return frame


def build_rows() -> tuple[list[dict[str, Any]], int]:
    """Return place rows and the number of stations dropped for overlap."""
    import geopandas as gpd
    from shapely.ops import unary_union

    root = settings.REPO_ROOT
    raw = pd.read_csv(data_root() / "subway" / "stations.csv", dtype=str)
    grouped = _groups(raw)
    keys: list[str] = []
    longitudes: list[float] = []
    latitudes: list[float] = []
    for row in grouped.itertuples(index=False):
        keys.append(row.key)
        longitudes.append(float(row.LOT))
        latitudes.append(float(row.LAT))
    circles = buffers(keys, longitudes, latitudes, key_name="station")
    places = gpd.read_file(root / SHP).to_crs(5179)
    places["geometry"] = places.geometry.make_valid()
    union = unary_union(list(places.geometry))
    dropped = []
    kept_keys = []
    for _, row in circles.iterrows():
        area = float(row.geometry.area)
        fraction = 0.0 if area == 0 else float(row.geometry.intersection(union).area) / area
        if covered(fraction):
            dropped.append(str(row.station))
        else:
            kept_keys.append(str(row.station))
    kept_keys = sorted(set(kept_keys))
    numeric = grouped.assign(LAT=grouped.LAT.astype(float), LOT=grouped.LOT.astype(float))
    means = numeric.groupby("key")[["LAT", "LOT"]].mean()
    codes = grouped.groupby("key")["BLDN_ID"].agg(lambda values: sorted(set(values)))
    names = {
        str(key): display_name(str(key), [str(value) for value in frame["BLDN_NM"]])
        for key, frame in grouped.groupby("key")
    }
    circles_wgs = circles.set_index("station").to_crs(4326)
    dong = gpd.read_file(root / DONG)
    if dong.crs is None:
        raise RuntimeError("dong.geojson has no CRS")
    if GU_FIELD not in dong.columns:
        raise RuntimeError(f"dong.geojson has no {GU_FIELD} attribute")
    dong = dong.to_crs(4326)
    points = gpd.GeoDataFrame(
        {"key": kept_keys},
        geometry=gpd.points_from_xy(
            [float(means.loc[key, "LOT"]) for key in kept_keys],
            [float(means.loc[key, "LAT"]) for key in kept_keys],
        ),
        crs=4326,
    )
    joined = gpd.sjoin(points, dong[[GU_FIELD, "geometry"]], how="left", predicate="within")
    if joined.index.has_duplicates:
        tied = sorted(set(joined.loc[joined.index.duplicated(), "key"].astype(str)))
        raise RuntimeError(f"station point falls in more than one dong: {tied}")
    gu_by_key = dict(zip(joined["key"].astype(str), joined[GU_FIELD], strict=True))
    rows = []
    for index, key in enumerate(kept_keys, start=1):
        gu = gu_by_key.get(key)
        gu_text = None if gu is None or str(gu) in {"None", "nan"} else str(gu)
        rows.append(
            {
                "id": f"STN{index:03d}",
                "name": names[key],
                "category": CATEGORY,
                "gu": gu_text,
                "lat": round(float(means.loc[key, "LAT"]), 6),
                "lon": round(float(means.loc[key, "LOT"]), 6),
                "geom": Jsonb(_geom_json(circles_wgs.loc[key].geometry)),
                "station_codes": list(codes.loc[key]),
            }
        )
    return rows, len(set(dropped))


def _counts(conn) -> list[tuple]:
    return conn.execute(
        "select tier, serve_state, count(*) from places where tier <> 'B' group by 1, 2 order by 1, 2"
    ).fetchall()


def load_stations() -> int:
    settings.load_env()
    url = settings.require(("DATABASE_URL",))["DATABASE_URL"]
    rows, dropped = build_rows()
    with db.job_run(url, JOB) as ctx:
        with db.connect(url) as conn:
            before = _counts(conn)
            changed = 0
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(_UPSERT, row)
                    changed += cur.rowcount
            after = _counts(conn)
            if before != after:
                raise RuntimeError("A1/A2 place counts changed")
            conn.commit()
        ctx["detail"] = {"places": len(rows), "dropped": dropped, "changed": changed}
    log(JOB, "ok", places=len(rows), dropped=dropped, changed=changed)
    return 0
