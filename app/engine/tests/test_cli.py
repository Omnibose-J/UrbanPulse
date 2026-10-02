import re
from pathlib import Path

from engine.__main__ import JOBS

ROOT = Path(__file__).resolve().parents[3]


def test_every_mapped_job_parses(cli):
    text = (ROOT / "docs" / "LLM_PROJECT_MAP.md").read_text(encoding="utf-8")
    names = sorted(set(re.findall(r"python -m engine ([a-z0-9_]+)", text)))
    assert names
    assert set(names) <= set(JOBS)
    for name in names:
        result = cli(name, "--help")
        assert result.returncode == 0, name


def test_unknown_job_exits_2(cli):
    assert cli("nope").returncode == 2


def test_healthcheck_without_env_exits_1_naming_first_missing_variable(cli):
    r = cli("healthcheck")
    assert r.returncode == 1
    assert "missing env var: DATABASE_URL" in r.stderr
