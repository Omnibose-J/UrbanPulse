"""Parsers shared by backfill and collect.

Level words that are not in the map raise. Timestamps are timezone-aware Asia/Seoul.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

LIVE_LEVELS = {"여유": 0, "보통": 1, "약간 붐빔": 2, "붐빔": 3}
COMMERCE_LEVELS = {"한산한": 0, "보통": 1, "분주한": 2, "바쁜": 3}

LIVE_TIME_FMT = "%Y-%m-%d %H:%M"
COMMERCE_TIME_FMT = "%Y%m%d %H%M"


def parse_live_level(word: str) -> int:
    try:
        return LIVE_LEVELS[word]
    except KeyError:
        raise ValueError(f"unknown live level: {word}") from None


def parse_commerce_level(word: str) -> int:
    try:
        return COMMERCE_LEVELS[word]
    except KeyError:
        raise ValueError(f"unknown commerce level: {word}") from None


def kst(ts_str: str, fmt: str) -> datetime:
    """Parse `ts_str` with `fmt` and attach Asia/Seoul. The input has no offset."""
    return datetime.strptime(ts_str.strip(), fmt).replace(tzinfo=KST)


_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H%M", "%Y%m%d%H%M")


def parse_timestamp(text: str) -> datetime:
    """Parse a Seoul citydata timestamp. Raises ValueError if none of the known layouts match."""
    raw = text.strip()
    for fmt in _TIME_FORMATS:
        try:
            return kst(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"unknown timestamp: {raw}")


def parse_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"missing integer: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"non-integer: {value}")
        return int(value)
    text = str(value).strip()
    if text == "":
        raise ValueError("missing integer")
    if "." in text:
        number = float(text)
        if not number.is_integer():
            raise ValueError(f"non-integer: {value}")
        return int(number)
    return int(text)


@dataclass(frozen=True)
class CitySnapshot:
    live: dict[str, Any] | None
    commerce: dict[str, Any] | None
    forecasts: list[dict[str, Any]]
    unknown_categories: tuple[str, ...] = ()


def _dicts(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        return [node]
    if isinstance(node, list):
        return [item for item in node if isinstance(item, dict)]
    return []


def _unwrap(node: Any, inner_key: str) -> Any:
    """If `node` is a wrapper object whose only payload is `inner_key`, return that payload."""
    if isinstance(node, dict) and inner_key in node and "PPLTN_TIME" not in node and "CMRCL_TIME" not in node:
        return node[inner_key]
    return node


def _live_block(city: dict[str, Any]) -> dict[str, Any] | None:
    node = _unwrap(city.get("LIVE_PPLTN_STTS"), "LIVE_PPLTN_STTS")
    blocks = _dicts(node)
    if not blocks:
        return None
    if len(blocks) != 1:
        raise ValueError(f"expected one LIVE_PPLTN_STTS, got {len(blocks)}")
    block = blocks[0]
    if not block.get("PPLTN_TIME"):
        return None
    return block


def _age_rates(block: dict[str, Any]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for key, value in block.items():
        if not isinstance(key, str) or not key.startswith("PPLTN_RATE_"):
            continue
        if value is None or value == "":
            continue
        rates[key] = float(value)
    return rates


def _forecast_rows(place_id: str, issued: Any, block: dict[str, Any]) -> list[dict[str, Any]]:
    node = block.get("FCST_PPLTN")
    if isinstance(node, dict) and "FCST_PPLTN" in node and "FCST_TIME" not in node:
        node = node["FCST_PPLTN"]
    rows: list[dict[str, Any]] = []
    for item in _dicts(node):
        if not item.get("FCST_TIME"):
            continue
        rows.append(
            {
                "place_id": place_id,
                "target_ts": parse_timestamp(str(item["FCST_TIME"])),
                "issued_ts": issued,
                "pop_min": parse_int(item["FCST_PPLTN_MIN"]),
                "pop_max": parse_int(item["FCST_PPLTN_MAX"]),
                "level": parse_live_level(str(item["FCST_CONGEST_LVL"])),
            }
        )
    return rows


COMMERCE_CATEGORIES = (
    "음식·음료",
    "유통",
    "패션·뷰티",
    "여가·오락",
    "생활서비스",
    "의료·건강",
    "교육",
    "숙박",
)
_COMMERCE_ALIAS = {"의료": "의료·건강"}


def normalize_category_counts(raw: dict[str, int]) -> tuple[dict[str, int], list[str]]:
    """Eight fixed keys, zero-filled. `의료` folds into `의료·건강`. Anything else sums into `기타`."""
    totals = {name: 0 for name in COMMERCE_CATEGORIES}
    unknown: list[str] = []
    extra = 0
    for name, count in raw.items():
        key = _COMMERCE_ALIAS.get(name, name)
        if key in totals:
            totals[key] += count
        else:
            unknown.append(name)
            extra += count
    if unknown:
        totals["기타"] = extra
    return totals, unknown


def _category_counts(commerce: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    node = commerce.get("CMRCL_RSB")
    # Research snapshots wrap the rows in {"CMRCL_RSB": [...]} or {"CMRCL_RSB": {...}}.
    # A live response sends the list directly. A single category object is one row.
    if isinstance(node, dict) and "CMRCL_RSB" in node and "RSB_LRG_CTGR" not in node:
        node = node["CMRCL_RSB"]
    raw: dict[str, int] = {}
    for item in _dicts(node):
        name = item.get("RSB_LRG_CTGR")
        if not name:
            continue
        key = str(name)
        raw[key] = raw.get(key, 0) + parse_int(item.get("RSB_SH_PAYMENT_CNT") or 0)
    return normalize_category_counts(raw)


def _commerce_row(place_id: str, city: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    node = city.get("LIVE_CMRCL_STTS")
    if not isinstance(node, dict) or not node.get("CMRCL_TIME"):
        return None, []
    counts, unknown = _category_counts(node)
    return {
        "place_id": place_id,
        "ts": parse_timestamp(str(node["CMRCL_TIME"])),
        "level": parse_commerce_level(str(node["AREA_CMRCL_LVL"])),
        "pay_cnt": parse_int(node["AREA_SH_PAYMENT_CNT"]),
        "cat_counts": counts,
    }, unknown


def parse_citydata(place_id: str, body: dict[str, Any]) -> CitySnapshot:
    """Parse one citydata response. No live population block means an empty snapshot, not an error."""
    city = body.get("CITYDATA") if isinstance(body, dict) else None
    if not isinstance(city, dict):
        raise ValueError(f"{place_id}: missing CITYDATA")
    block = _live_block(city)
    if block is None:
        return CitySnapshot(None, None, [])
    issued = parse_timestamp(str(block["PPLTN_TIME"]))
    male = block.get("MALE_PPLTN_RATE")
    live = {
        "place_id": place_id,
        "ts": issued,
        "pop_min": parse_int(block["AREA_PPLTN_MIN"]),
        "pop_max": parse_int(block["AREA_PPLTN_MAX"]),
        "level": parse_live_level(str(block["AREA_CONGEST_LVL"])),
        "age_rates": _age_rates(block),
        "male_rate": None if male in (None, "") else float(male),
    }
    commerce, unknown = _commerce_row(place_id, city)
    return CitySnapshot(live, commerce, _forecast_rows(place_id, issued, block), tuple(unknown))
