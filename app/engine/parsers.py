"""Parsers shared by backfill and collect.

Level words that are not in the map raise. Timestamps are timezone-aware Asia/Seoul.
"""

from __future__ import annotations

from datetime import datetime
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
