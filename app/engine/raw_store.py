"""Write a raw citydata body once. The file is created exclusively and never rewritten."""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.parsers import KST


def folder_for(run_ts: datetime, raw_dir: Path) -> Path:
    """`RAW_DIR/YYYY/MM/DD/HHMM` in Asia/Seoul, minute of the run start (seconds dropped)."""
    minute = run_ts.astimezone(KST).replace(second=0, microsecond=0)
    return raw_dir / f"{minute:%Y}" / f"{minute:%m}" / f"{minute:%d}" / f"{minute:%H%M}"


def write(run_ts: datetime, place_code: str, body: dict[str, Any], raw_dir: Path) -> Path:
    folder = folder_for(run_ts, raw_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{place_code}.json.gz"
    payload = gzip.compress(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    with path.open("xb") as handle:
        handle.write(payload)
    return path
