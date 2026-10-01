"""Level words and KST timestamps."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from engine.parsers import (
    COMMERCE_LEVELS,
    COMMERCE_TIME_FMT,
    LIVE_LEVELS,
    LIVE_TIME_FMT,
    kst,
    parse_commerce_level,
    parse_live_level,
)

KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize("word,level", LIVE_LEVELS.items())
def test_live_level_words(word, level):
    assert parse_live_level(word) == level


@pytest.mark.parametrize("word,level", COMMERCE_LEVELS.items())
def test_commerce_level_words(word, level):
    assert parse_commerce_level(word) == level


def test_unknown_level_word_raises():
    with pytest.raises(ValueError, match="unknown live level"):
        parse_live_level("혼잡")
    with pytest.raises(ValueError, match="unknown commerce level"):
        parse_commerce_level("한산")


def test_kst_timestamp_is_seoul():
    parsed = kst("2026-08-29 23:30", LIVE_TIME_FMT)
    assert parsed == datetime(2026, 8, 29, 23, 30, tzinfo=KST)
    assert parsed.isoformat() == "2026-08-29T23:30:00+09:00"


def test_cmrcl_time_parses():
    parsed = kst("20260515 2300", COMMERCE_TIME_FMT)
    assert parsed == datetime(2026, 5, 15, 23, 0, tzinfo=KST)
