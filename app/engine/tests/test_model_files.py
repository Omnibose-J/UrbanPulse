"""An active registry row with no artifact must fail the process."""

import pytest

from engine.jobs.forecast import require_model_files


def test_an_active_row_with_a_missing_directory_exits_1(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        require_model_files(tmp_path / "ratio_v1", "2026-10-01T00:00:00+09:00")
    assert caught.value.code == 1
    assert str(tmp_path / "ratio_v1") in capsys.readouterr().err
