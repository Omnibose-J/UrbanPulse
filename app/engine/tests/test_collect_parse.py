"""Citydata fixtures: one commerce place, one park, and a single-dict CMRCL_RSB copy."""

import json
from pathlib import Path

from engine.parsers import (
    COMMERCE_CATEGORIES,
    parse_citydata,
    parse_live_level,
    parse_timestamp,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_commerce_place_rows():
    body = _load("poi003.json")
    snap = parse_citydata("POI003", body)
    block = body["CITYDATA"]["LIVE_PPLTN_STTS"][0]
    commerce = body["CITYDATA"]["LIVE_CMRCL_STTS"]
    raw: dict[str, int] = {}
    for item in commerce["CMRCL_RSB"]:
        name = item["RSB_LRG_CTGR"]
        raw[name] = raw.get(name, 0) + int(item["RSB_SH_PAYMENT_CNT"])
    counts = snap.commerce["cat_counts"]
    assert "의료" not in counts
    assert set(COMMERCE_CATEGORIES) <= set(counts)
    assert counts["의료·건강"] == raw.get("의료", 0) + raw.get("의료·건강", 0)
    for name, count in raw.items():
        if name in ("의료", "의료·건강"):
            continue
        if name in COMMERCE_CATEGORIES:
            assert counts[name] == count
        else:
            assert name in snap.unknown_categories
    assert snap.commerce["pay_cnt"] == int(commerce["AREA_SH_PAYMENT_CNT"])
    assert len(snap.forecasts) == len(block["FCST_PPLTN"])
    assert snap.forecasts[0]["issued_ts"] == snap.live["ts"]
    assert snap.forecasts[0]["target_ts"] == parse_timestamp(block["FCST_PPLTN"][0]["FCST_TIME"])
    assert snap.forecasts[0]["level"] == parse_live_level(block["FCST_PPLTN"][0]["FCST_CONGEST_LVL"])


def test_park_has_no_commerce():
    body = _load("poi087.json")
    assert body["CITYDATA"]["LIVE_CMRCL_STTS"] is None
    snap = parse_citydata("POI087", body)
    assert snap.live is not None
    assert snap.commerce is None
    assert snap.forecasts


def test_single_dict_cmrcl_rsb():
    body = _load("poi003_cmrcl_rsb_dict.json")
    item = body["CITYDATA"]["LIVE_CMRCL_STTS"]["CMRCL_RSB"]
    assert isinstance(item, dict)
    snap = parse_citydata("POI003", body)
    assert snap.commerce is not None
    counts = snap.commerce["cat_counts"]
    name = item["RSB_LRG_CTGR"]
    assert "의료" not in counts
    assert counts.get("의료·건강" if name == "의료" else name, 0) == int(item["RSB_SH_PAYMENT_CNT"])
    assert set(COMMERCE_CATEGORIES) <= set(counts)
