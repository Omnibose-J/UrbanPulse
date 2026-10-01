"""Load a trained ratio_v1 model and score one place."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import sklearn

from engine.calendar_feats import calendar

FEATURES = ["hour", "dow", "month", "hol", "hol_wkend", "big", "to_hol", "from_hol", "poi_i", "h"]


class RatioModel:
    def __init__(self, model, meta: dict, directory: Path):
        self.model = model
        self.meta = meta
        self.directory = directory
        self.place_index: dict[str, int] = meta["place_index"]
        self.features: list[str] = meta["features"]
        self.holidays = [date.fromisoformat(day) for day in meta["holidays"]]
        self.seol_starts = [date.fromisoformat(day) for day in meta["block_starts"]["seol"]]
        self.chuseok_starts = [date.fromisoformat(day) for day in meta["block_starts"]["chuseok"]]
        self.passing_horizons = set(meta.get("passing_horizons") or [])

    def ratio(self, place_id: str, timestamps, horizon_d: int):
        """Predicted log-ratio. None when the place was not in the training pivot."""
        if place_id not in self.place_index:
            return None
        index = pd.DatetimeIndex(pd.to_datetime(list(timestamps)))
        frame = calendar(index, self.holidays, self.seol_starts, self.chuseok_starts)
        frame["poi_i"] = self.place_index[place_id]
        frame["h"] = horizon_d
        return self.model.predict(frame[self.features])


def load(directory: str | Path) -> RatioModel:
    directory = Path(directory)
    meta_path = directory / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    installed = sklearn.__version__
    trained = meta["sklearn_version"]
    if installed != trained:
        print(f"sklearn {installed} != meta {trained}", file=sys.stderr)
        raise SystemExit(1)
    model = joblib.load(directory / "model.joblib")
    return RatioModel(model, meta, directory)
