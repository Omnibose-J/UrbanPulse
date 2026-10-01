"""Holiday kind rules against the 2026 KASI rows, and English for every returned name."""

import json
from pathlib import Path

from engine.jobs.sync_holidays import english_name, kind_of, load_english_names

FIXTURES = Path(__file__).parent / "fixtures"


def _expected_kind(name: str) -> str:
    if "대체" in name:
        return "substitute"
    if "설날" in name:
        return "seol"
    if "추석" in name:
        return "chuseok"
    return "holiday"


def test_2026_kind_mapping():
    rows = json.loads((FIXTURES / "kasi_2026.json").read_text(encoding="utf-8"))
    seol = [row for row in rows if row["name"] == "설날"]
    chuseok = [row for row in rows if row["name"] == "추석"]
    substitute = [row for row in rows if "대체공휴일" in row["name"]]
    assert len(seol) == 3
    assert len(chuseok) == 3
    assert substitute
    assert all(kind_of(row["name"]) == "seol" for row in seol)
    assert all(kind_of(row["name"]) == "chuseok" for row in chuseok)
    assert all(kind_of(row["name"]) == "substitute" for row in substitute)
    assert all(kind_of(row["name"]) == _expected_kind(row["name"]) for row in rows)


def test_every_returned_name_has_english():
    names = json.loads((FIXTURES / "kasi_names.json").read_text(encoding="utf-8"))
    table = load_english_names()
    assert names
    for name in names:
        assert english_name(name, table)
