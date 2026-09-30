"""One JSON line per event on stdout, UTF-8 regardless of the console code page. Never logs a URL."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

_configured = False


def _configure() -> None:
    global _configured
    if not _configured:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        _configured = True


def log(job: str, event: str, **fields: Any) -> None:
    _configure()
    record = {"job": job, "event": event, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **fields}
    print(json.dumps(record, ensure_ascii=False), flush=True)
