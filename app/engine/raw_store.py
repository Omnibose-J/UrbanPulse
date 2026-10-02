"""Write a raw citydata body once. A local file is created exclusively; a bucket object is write-once."""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from engine.parsers import KST


def is_gcs(raw_dir: str | Path) -> bool:
    return str(raw_dir).startswith("gs://")


def _minute(run_ts: datetime) -> datetime:
    return run_ts.astimezone(KST).replace(second=0, microsecond=0)


def relative_key(run_ts: datetime, place_code: str) -> str:
    """`YYYY/MM/DD/HHMM/<code>.json.gz` in Asia/Seoul."""
    minute = _minute(run_ts)
    return f"{minute:%Y}/{minute:%m}/{minute:%d}/{minute:%H%M}/{place_code}.json.gz"


def relative_folder(run_ts: datetime) -> str:
    minute = _minute(run_ts)
    return f"{minute:%Y}/{minute:%m}/{minute:%d}/{minute:%H%M}"


def folder_for(run_ts: datetime, raw_dir: Path) -> Path:
    """Local `RAW_DIR/YYYY/MM/DD/HHMM`. Bucket locations do not use this."""
    return Path(raw_dir) / relative_folder(run_ts)


def _payload(body: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def write(run_ts: datetime, place_code: str, body: dict[str, Any], raw_dir: str | Path, client=None):
    payload = _payload(body)
    key = relative_key(run_ts, place_code)
    if is_gcs(raw_dir):
        from engine.raw_gcs import upload

        return upload(str(raw_dir), key, payload, client)
    import os

    path = Path(raw_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    try:
        os.link(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    temporary.unlink(missing_ok=True)
    return path


def _decode(name: str, data: bytes) -> tuple[str, dict | None, str | None]:
    code = name.rsplit("/", 1)[-1].removesuffix(".json.gz")
    try:
        return code, json.loads(gzip.decompress(data)), None
    except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return code, None, type(exc).__name__


def iter_day(raw_dir: str | Path, day: date, client=None):
    """Yield `(folder, code, body, error)`. A bad file does not stop the rest."""
    prefix = f"{day:%Y}/{day:%m}/{day:%d}/"
    if is_gcs(raw_dir):
        from engine.raw_gcs import read_prefix

        for name, data in read_prefix(str(raw_dir), prefix, client):
            folder = name.rsplit("/", 2)[-2] if "/" in name else ""
            code, body, error = _decode(name, data)
            yield folder, code, body, error
        return
    root = Path(raw_dir) / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
    if not root.is_dir():
        return
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        for path in sorted(folder.glob("*.json.gz")):
            code = path.name.removesuffix(".json.gz")
            try:
                data = path.read_bytes()
            except OSError as exc:
                yield folder.name, code, None, type(exc).__name__
                continue
            decoded, body, error = _decode(path.name, data)
            yield folder.name, decoded, body, error


def read_day(raw_dir: str | Path, day: date, client=None) -> list[tuple[str, dict]]:
    """Successfully parsed `(place code, body)` rows for one KST day."""
    rows = []
    for _folder, code, body, error in iter_day(raw_dir, day, client):
        if error is None and body is not None:
            rows.append((code, body))
    return rows
