"""Environment access. Values come from the process environment, optionally seeded from the repo-root `.env`.

Rules (AGENTS.md hard rule 4): a missing variable exits 1 naming it; a value is never printed, not even a
prefix. Set `ENGINE_SKIP_DOTENV=1` to ignore the `.env` file (tests do this so they never read real keys).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path

from dotenv import load_dotenv

from engine import ROOT_ENV_FILE

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Seed os.environ from `<repo root>/.env` when present. Existing variables win."""
    if os.environ.get("ENGINE_SKIP_DOTENV") == "1":
        return
    path = REPO_ROOT / ROOT_ENV_FILE
    if path.exists():
        load_dotenv(path, override=False)


def require(names: Iterable[str], env: dict[str, str] | None = None) -> dict[str, str]:
    """Return the named variables; exit 1 on the first one that is missing or empty."""
    source = os.environ if env is None else env
    out: dict[str, str] = {}
    for name in names:
        value = source.get(name, "")
        if not value:
            print(f"missing env var: {name}", file=sys.stderr)
            sys.exit(1)
        out[name] = value
    return out
