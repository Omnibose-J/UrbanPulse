import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def clean_env(monkeypatch):
    """A process environment without any engine variable and without .env loading."""
    for name in ("DATABASE_URL", "SEOUL_API_KEY", "KASI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    return {k: v for k, v in os.environ.items()}


@pytest.fixture
def cli(clean_env):
    """Run `python -m engine <args>` from the repo root with the clean environment."""
    import subprocess

    def _run(*args: str):
        env = dict(clean_env)
        env["PYTHONPATH"] = str(ROOT / "app")
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "engine", *args], cwd=ROOT, env=env, capture_output=True, text=True
        )

    return _run


@pytest.fixture
def private_conn():
    """A connection whose search_path is a throwaway copy of the schema. The live tables are never written."""
    import psycopg

    from engine.tests.tempdb import schema

    with schema() as dsn:
        conn = psycopg.connect(dsn, autocommit=False, connect_timeout=5)
        try:
            yield conn
        finally:
            conn.close()
