"""A holiday added to the table changes the model's hol feature."""

from datetime import date, datetime
from pathlib import Path

import psycopg

from engine.parsers import KST
from engine.ratio_model import FEATURES, RatioModel, load_calendar
from engine.tests.tempdb import schema


class _Hol:
    def predict(self, frame):
        return frame["hol"].to_numpy()


def test_a_date_added_to_the_table_changes_hol():
    meta = {
        "place_index": {"POI001": 0},
        "features": FEATURES,
        "holidays": ["2026-08-15"],
        "block_starts": {"seol": [], "chuseok": []},
    }
    model = RatioModel(_Hol(), meta, Path("."))
    stamp = [datetime(2026, 10, 5, 12, tzinfo=KST)]
    with schema() as dsn:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into holidays (date, name, kind) values ('2026-10-05', 'added', 'holiday')"
            )
            holidays, seol, chuseok = load_calendar(conn)
            scored = model.ratio("POI001", stamp, 0, holidays, seol, chuseok)
            frozen = model.ratio("POI001", stamp, 0, [date(2026, 8, 15)], [], [])
    assert int(scored[0]) == 1
    assert int(frozen[0]) == 0
