import pytest

from engine.__main__ import NOT_YET


@pytest.mark.parametrize("job", sorted(NOT_YET))
def test_unimplemented_jobs_exit_2_naming_their_work_unit(cli, job):
    r = cli(job)
    assert r.returncode == 2
    assert NOT_YET[job] in r.stderr


def test_unknown_job_exits_2(cli):
    assert cli("nope").returncode == 2


def test_healthcheck_without_env_exits_1_naming_first_missing_variable(cli):
    r = cli("healthcheck")
    assert r.returncode == 1
    assert "missing env var: DATABASE_URL" in r.stderr
