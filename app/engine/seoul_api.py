"""Fetch one Seoul citydata place. The key stays in the URL and never in an exception message."""

from __future__ import annotations

import time
from typing import Any

import httpx

SEOUL_URL = "http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/{code}"
TIMEOUT = 20.0
# Three attempts. Sleep 1s before the second and 2s before the third.
BACKOFF_S = (0.0, 1.0, 2.0)


class SeoulError(RuntimeError):
    """Place code and status only. Never a URL or a key."""


def fetch(place_code: str, client: httpx.Client, key: str) -> dict[str, Any]:
    """Return the parsed JSON body. HTTP errors, non-200, and a missing CITYDATA raise SeoulError."""
    url = SEOUL_URL.format(key=key, code=place_code)
    error: SeoulError | None = None
    for delay in BACKOFF_S:
        if delay:
            time.sleep(delay)
        try:
            response = client.get(url, timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            error = SeoulError(f"{place_code}: {type(exc).__name__}")
            continue
        if response.status_code != 200:
            error = SeoulError(f"{place_code}: HTTP {response.status_code}")
            continue
        try:
            body = response.json()
        except ValueError:
            error = SeoulError(f"{place_code}: invalid JSON")
            continue
        city = body.get("CITYDATA") if isinstance(body, dict) else None
        if not isinstance(city, dict) or not city:
            error = SeoulError(f"{place_code}: missing CITYDATA")
            continue
        return body
    assert error is not None
    raise error
