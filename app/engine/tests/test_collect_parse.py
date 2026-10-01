"""Citydata fixtures: one commerce place, one park, and a single-dict CMRCL_RSB copy."""

import json
from pathlib import Path

from engine.parsers import parse_citydata, parse_commerce_level, parse_live_level, parse_timestamp

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_commerce_place_rows():
    body = _load("poi003.json")
    snap = parse_citydata("POI003", body)
    block = body["CITYDATA"]["LIVE_PPLTN_STTS"][0]
    commerce = body["CITYDATA"]["LIVE_CMRCL_STTS"]
    expected: dict[str, int] = {}
    for item in commerce["CMRCL_RSB"]:
        name = item["RSB_LRG_CTGR"]
        expected[name] = expected.get(name, 0) + int(item["RSB_SH_PAYMENT_CNT"])
    assert snap.live is not None and snap.commerce is not None
    assert snap.live["ts"] == parse_timestamp(block["PPLTN_TIME"])
    assert snap.live["level"] == parse_live_level(block["AREA_CONGEST_LVL"])
    assert snap.live["pop_min"] == int(block["AREA_PPLTN_MIN"])
    assert snap.live["pop_max"] == int(block["AREA_PPLTN_MAX"])
    assert snap.commerce["ts"] == parse_timestamp(commerce["CMRCL_TIME"])
    assert snap.commerce["level"] == parse_commerce_level(commerce["AREA_CMRCL_LVL"])
    assert snap.commerce["pay_cnt"] == int(commerce["AREA_SH_PAYMENT_CNT"])
    assert snap.commerce["cat_counts"] == expected
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
    assert snap.commerce["cat_counts"] == {item["RSB_LRG_CTGR"]: int(item["RSB_SH_PAYMENT_CNT"])}
