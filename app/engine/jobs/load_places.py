"""Load the 121 Seoul places into `places`. One-off: `python -m engine load_places`.

Geopandas is imported inside `run` so the rest of the engine (and the Docker image) does not depend on it.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from psycopg.types.json import Jsonb

from engine import db, settings
from engine.log import log

JOB = "load_places"
HERITAGE = "고궁·문화유산"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
GU_FIELD = "sggnm"

_SHP = "analysis/data/poi/서울시 주요 121장소 영역/서울시 주요 121장소 영역.shp"
_DONG = "analysis/data/poi/dong.geojson"
_FILL = "analysis/data/fill_gap_by_place.csv"
_OBS = ("analysis/data/obs.csv", "analysis/data/obs_hist.csv", "analysis/data/obs_hist_aug.csv")
_CMRCL = ("analysis/data/cmrcl.csv", "analysis/data/cmrcl_rest.csv")

_UPSERT = """
insert into places (
  id, tier, name, name_en, category, gu, lat, lon, geom, poi_code,
  open_hours, foreign_heavy, serve_state, updated_at
) values (
  %(id)s, %(tier)s, %(name)s, %(name_en)s, %(category)s, %(gu)s, %(lat)s, %(lon)s,
  %(geom)s, %(poi_code)s, %(open_hours)s, %(foreign_heavy)s, %(serve_state)s, now()
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
  poi_code = excluded.poi_code,
  open_hours = excluded.open_hours,
  foreign_heavy = excluded.foreign_heavy,
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
   or places.poi_code is distinct from excluded.poi_code
   or places.open_hours is distinct from excluded.open_hours
   or places.foreign_heavy is distinct from excluded.foreign_heavy
   or places.serve_state is distinct from excluded.serve_state
"""


def _pois(path: Path) -> set[str]:
    found: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            poi = (row.get("poi") or "").strip()
            if poi:
                found.add(poi)
    return found


def _fill_categories(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            poi = (row.get("poi") or "").strip()
            category = (row.get("CATEGORY") or "").strip()
            if poi and category:
                out[poi] = category
    return out


def _substrings(path: Path) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    subs = data.get("substrings") if isinstance(data, dict) else None
    if not subs or not all(isinstance(s, str) and s for s in subs):
        raise RuntimeError(f"{path.name}: substrings must be a non-empty list of strings")
    return list(subs)


def _open_hours_table(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path.name}: expected a mapping of POI to hours")
    return data


def _hours_for(poi: str, tier: str, category: str | None, table: dict[str, Any]) -> dict[str, Any] | None:
    if not (tier == "A2" and category == HERITAGE):
        return None
    spec = table.get(poi)
    if not isinstance(spec, dict) or not isinstance(spec.get("hours"), dict):
        raise RuntimeError(f"missing open_hours for A2 heritage place {poi}")
    hours = spec["hours"]
    if set(hours) != set(WEEKDAYS):
        raise RuntimeError(f"open_hours for {poi} must have keys {WEEKDAYS}")
    for day in WEEKDAYS:
        value = hours[day]
        if value is not None and not isinstance(value, str):
            raise RuntimeError(f"open_hours for {poi} {day} must be a string or null")
    if not spec.get("source") or not spec.get("checked"):
        raise RuntimeError(f"open_hours for {poi} needs source and checked")
    return {
        "hours": {day: hours[day] for day in WEEKDAYS},
        "source": str(spec["source"]),
        "checked": str(spec["checked"]),
    }


def _geom_json(geom: Any) -> dict[str, Any]:
    from shapely.geometry import mapping

    return json.loads(json.dumps(mapping(geom)))


def _write_place_codes(codes: list[str]) -> Path:
    """Tracked list of POI codes in shapefile order. A repeat writes the same bytes."""
    path = Path(__file__).resolve().parents[1] / "config" / "place_codes.yaml"
    body = "codes:\n" + "".join(f"  - {code}\n" for code in codes)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def run() -> int:
    settings.load_env()
    env = settings.require(("DATABASE_URL",))
    try:
        import geopandas as gpd
    except ImportError:
        print("missing dependency: geopandas (pip install geopandas pyogrio)", file=sys.stderr)
        return 1

    root = settings.REPO_ROOT
    config = Path(__file__).resolve().parents[1] / "config"
    shp_path = root / _SHP
    dong_path = root / _DONG
    if not shp_path.exists() or not dong_path.exists():
        print("missing place geometry under analysis/data/poi", file=sys.stderr)
        return 1

    places = gpd.read_file(shp_path)
    if places.crs is None:
        raise RuntimeError("shapefile has no CRS")
    crs_before = places.crs.to_string()
    places = places.to_crs(4326)
    for column in ("AREA_CD", "AREA_NM", "CATEGORY"):
        if column not in places.columns:
            raise RuntimeError(f"shapefile is missing {column}")
    if len(places) != places["AREA_CD"].nunique():
        raise RuntimeError("AREA_CD is not unique")

    projected = places.to_crs(5179)
    cent_m = projected.geometry.centroid
    cent = gpd.GeoSeries(cent_m, crs=5179).to_crs(4326)
    outside_own = sorted(
        places.loc[~projected.geometry.covers(cent_m), "AREA_CD"].astype(str).tolist()
    )

    dong = gpd.read_file(dong_path)
    if dong.crs is None:
        raise RuntimeError("dong.geojson has no CRS")
    if GU_FIELD not in dong.columns:
        raise RuntimeError(f"dong.geojson has no {GU_FIELD} attribute")
    dong = dong.to_crs(4326)
    points = gpd.GeoDataFrame(
        {"AREA_CD": places["AREA_CD"].astype(str).tolist()},
        geometry=cent,
        crs=4326,
    )
    joined = gpd.sjoin(points, dong[[GU_FIELD, "geometry"]], how="left", predicate="within")
    if joined.index.has_duplicates:
        tied = sorted(set(joined.loc[joined.index.duplicated(), "AREA_CD"].astype(str)))
        raise RuntimeError(f"centroid falls in more than one dong: {tied}")
    gu_by_code = dict(zip(joined["AREA_CD"].astype(str), joined[GU_FIELD], strict=True))
    outside_dong = sorted(code for code, gu in gu_by_code.items() if gu is None or gu != gu)

    obs: set[str] = set()
    for rel in _OBS:
        obs |= _pois(root / rel)
    commerce: set[str] = set()
    for rel in _CMRCL:
        commerce |= _pois(root / rel)
    fill_cat = _fill_categories(root / _FILL)
    substrings = _substrings(config / "foreign_heavy.yaml")
    hours_table = _open_hours_table(config / "open_hours.yaml")
    english_available = bool(os.environ.get("DATA_GO_KR_KEY"))
    if english_available:
        raise RuntimeError(
            "DATA_GO_KR_KEY is set but the English place-name API is not implemented; name_en was not guessed"
        )

    rows: list[dict[str, Any]] = []
    from_shapefile = 0
    for i, place in places.iterrows():
        code = str(place["AREA_CD"])
        name = str(place["AREA_NM"])
        if code in fill_cat:
            category: str | None = fill_cat[code]
        else:
            raw = place["CATEGORY"]
            category = None if raw is None or str(raw).strip() in {"", "None", "nan"} else str(raw).strip()
            from_shapefile += 1
        tier = "A1" if code in commerce else "A2"
        serve = "preparing" if code in obs else "off"
        point = cent.loc[i]
        gu = gu_by_code.get(code)
        gu_text = None if gu is None or str(gu) in {"None", "nan"} else str(gu)
        if gu_text is None and code not in outside_dong:
            outside_dong.append(code)
        hours = _hours_for(code, tier, category, hours_table)
        rows.append(
            {
                "id": code,
                "tier": tier,
                "name": name,
                "name_en": None,
                "category": category,
                "gu": gu_text,
                "lat": float(point.y),
                "lon": float(point.x),
                "geom": Jsonb(_geom_json(place.geometry)),
                "poi_code": code,
                "open_hours": Jsonb(hours) if hours is not None else None,
                "foreign_heavy": any(piece in name for piece in substrings),
                "serve_state": serve,
            }
        )

    with db.connect(env["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany(_UPSERT, rows)
            written = cur.rowcount
        conn.commit()

    codes_path = _write_place_codes([row["id"] for row in rows])

    foreign_n = sum(1 for row in rows if row["foreign_heavy"])
    heritage = sorted(row["id"] for row in rows if row["open_hours"] is not None)
    log(
        JOB,
        "done",
        crs=crs_before,
        stored_crs="EPSG:4326",
        centroid="EPSG:5179 then transformed to EPSG:4326",
        gu_field=GU_FIELD,
        places=len(rows),
        written=written,
        place_codes=str(codes_path.relative_to(settings.REPO_ROOT).as_posix()),
        foreign_heavy=foreign_n,
        outside_dong=outside_dong,
        outside_own_polygon=outside_own,
        category_from_shapefile=from_shapefile,
        name_en_api=False,
        name_en_null=len(rows),
        open_hours=heritage,
    )
    return 0
