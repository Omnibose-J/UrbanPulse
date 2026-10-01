"""ingest_raw parses a raw folder twice into the same rows."""

import gzip
import json
from pathlib import Path

from engine.parsers import parse_citydata


def _write(folder: Path, place: str, pop: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    body = {
        "CITYDATA": {
            "LIVE_PPLTN_STTS": [
                {
                    "PPLTN_TIME": "2026-10-01 09:00",
                    "AREA_PPLTN_MIN": str(pop),
                    "AREA_PPLTN_MAX": str(pop + 5),
                    "AREA_CONGEST_LVL": "여유",
                }
            ]
        }
    }
    payload = gzip.compress(json.dumps(body).encode("utf-8"))
    (folder / f"{place}.json.gz").write_bytes(payload)


def test_parsing_a_folder_twice_is_the_same_rows(tmp_path):
    folder = tmp_path / "2026" / "10" / "01" / "0900"
    _write(folder, "POI001", 10)
    _write(folder, "POI002", 20)

    def read_all():
        rows = []
        for path in sorted(folder.glob("*.json.gz")):
            body = json.loads(gzip.decompress(path.read_bytes()))
            snap = parse_citydata(path.name.removesuffix(".json.gz"), body)
            rows.append((snap.live["place_id"], snap.live["pop_min"], snap.live["pop_max"]))
        return rows

    assert read_all() == read_all()
    assert read_all()[0][1] == 10
