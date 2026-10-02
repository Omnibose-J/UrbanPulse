"""Model loader refuses a sklearn mismatch and unknown places."""

import json
from pathlib import Path

import joblib
import pytest
import sklearn

from engine.ratio_model import load


class _Dummy:
    def predict(self, frame):
        return [0.2] * len(frame)


def _write(directory: Path, version: str, places: dict) -> None:
    directory.mkdir(parents=True)
    joblib.dump(_Dummy(), directory / "model.joblib")
    meta = {
        "place_index": places,
        "features": ["hour", "dow", "month", "hol", "hol_wkend", "big", "to_hol", "from_hol", "poi_i", "h"],
        "horizons_trained": [0, 1, 2, 3, 4, 5, 6, 7],
        "holidays_source": "research",
        "trained_range": "2023-01-01..2026-07-31",
        "n_rows": 1,
        "sklearn_version": version,
        "git_commit": "test",
        "created_at": "2026-10-01T00:00:00+09:00",
        "holidays": ["2026-08-15"],
        "block_starts": {"seol": ["2026-02-16"], "chuseok": ["2026-09-24"]},
    }
    (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_version_mismatch_refuses_to_load(tmp_path):
    _write(tmp_path / "model", "0.0.0", {"POI001": 0})
    with pytest.raises(SystemExit) as caught:
        load(tmp_path / "model")
    assert caught.value.code == 1


def test_batched_hours_match_one_call_each(tmp_path):
    _write(tmp_path / "model", sklearn.__version__, {"POI001": 0})
    model = load(tmp_path / "model")

    def predict(frame):
        return frame["hour"].to_numpy()

    model.model.predict = predict
    stamps = ["2026-08-15 09:00", "2026-08-15 18:00"]
    batched = [float(value) for value in model.ratio("POI001", stamps, 1)]
    single = [float(model.ratio("POI001", [stamp], 1)[0]) for stamp in stamps]
    assert batched == single


def test_unknown_place_returns_none(tmp_path):
    _write(tmp_path / "model", sklearn.__version__, {"POI001": 0})
    model = load(tmp_path / "model")
    assert model.ratio("POI999", ["2026-08-15 12:00"], 3) is None
    assert list(model.ratio("POI001", ["2026-08-15 12:00"], 3)) == [0.2]
