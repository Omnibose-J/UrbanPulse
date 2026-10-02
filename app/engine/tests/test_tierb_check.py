"""tier_b --check must fail the process when a figure misses its tolerance."""

from engine.jobs.tier_b import verdict_code


def test_a_figure_outside_tolerance_exits_1(capsys):
    assert verdict_code((0.84, 6.67, 62.28)) == 0
    assert verdict_code((0.84, 6.67, 70.0)) == 1
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "FAIL" in out
