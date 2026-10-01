"""Flag file: the judged table, and a loader that rejects a bad line."""

from pathlib import Path

import pytest

from engine.flags import FlagFile, load
from engine.reco import build_row

EXPECTED = {
    ("a1", "sight", "calm"): "off",
    ("a1", "sight", "moderate"): "on",
    ("a1", "sight", "busy_ok"): "on",
    ("a1", "food", "calm"): "off",
    ("a1", "food", "moderate"): "on",
    ("a1", "food", "busy_ok"): "on",
    ("a1", "shop", "calm"): "off",
    ("a1", "shop", "moderate"): "reference",
    ("a1", "shop", "busy_ok"): "on",
    ("a1_foreign", "sight", "calm"): "off",
    ("a1_foreign", "sight", "moderate"): "reference",
    ("a1_foreign", "sight", "busy_ok"): "reference",
    ("a1_foreign", "food", "calm"): "off",
    ("a1_foreign", "food", "moderate"): "reference",
    ("a1_foreign", "food", "busy_ok"): "reference",
    ("a1_foreign", "shop", "calm"): "off",
    ("a1_foreign", "shop", "moderate"): "off",
    ("a1_foreign", "shop", "busy_ok"): "reference",
    ("a2", "none", "calm"): "on",
    ("a2", "none", "moderate"): "on",
    ("a2", "none", "busy_ok"): "on",
}


def test_every_judged_combination_and_an_unlisted_one():
    flags = load()
    for combo, state in EXPECTED.items():
        assert flags.lookup(*combo) == (state, "windows_only")
    assert flags.lookup("a1", "none", "calm") == ("off", "windows_only")
    place = {
        "id": "POI001",
        "tier": "A2",
        "foreign_heavy": False,
        "serve_state": "on",
        "open_hours": None,
    }
    row = build_row(place, _day(), "calm", "none", _ready(), FlagFile({}, flags.lively_min), "weekday")
    assert row["state"] == "off"
    assert row["off_reason"] == "unverified"


def test_duplicate_line_and_unknown_value_are_rejected(tmp_path: Path):
    duplicate = tmp_path / "dup.yaml"
    duplicate.write_text(
        "\n".join(
            [
                "version: 1",
                "lively_min: {sight: 0.5, food: 0.5, shop: 0.6}",
                "combos:",
                "  - {group: a1, purpose: sight, tolerance: calm, state: off, strip: windows_only}",
                "  - {group: a1, purpose: sight, tolerance: calm, state: on, strip: windows_only}",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as duplicate_exit:
        load(duplicate)
    assert "duplicate" in str(duplicate_exit.value)
    unknown = tmp_path / "bad.yaml"
    unknown.write_text(
        "\n".join(
            [
                "version: 1",
                "lively_min: {sight: 0.5, food: 0.5, shop: 0.6}",
                "combos:",
                "  - {group: a1, purpose: sight, tolerance: calm, state: maybe, strip: windows_only}",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as unknown_exit:
        load(unknown)
    assert "unknown state" in str(unknown_exit.value)


def _day():
    from datetime import date

    return date(2026, 10, 1)


def _ready():
    return {
        hour: {"ready": True, "level": 1, "a_all": 1.0, "a_food": 1.0, "a_shop": 1.0} for hour in range(9, 24)
    }
