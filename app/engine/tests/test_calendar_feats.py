"""Hand-checked calendar features for the frozen research holiday list."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from engine.calendar_feats import calendar, load_research_calendar

RESEARCH = Path(__file__).resolve().parents[1] / "train" / "research_holidays.txt"

# hour, dow, month, hol, hol_wkend, big, to_hol, from_hol
# 2026-09-01 is a Tuesday, so 09-21 is Monday. Chuseok block starts 09-24, window -3..+6.
# Previous holiday before 09-24 is 08-17; the list ends at 09-26.
EXPECTED = {
    "2026-09-21": (0, 9, 0, 0, 2, 3, 8),
    "2026-09-22": (1, 9, 0, 0, 2, 2, 8),
    "2026-09-23": (2, 9, 0, 0, 2, 1, 8),
    "2026-09-24": (3, 9, 1, 0, 2, 0, 8),
    "2026-09-25": (4, 9, 1, 0, 2, 0, 1),
    "2026-09-26": (5, 9, 1, 1, 2, 0, 1),
    "2026-09-27": (6, 9, 0, 0, 2, 0, 1),
    "2026-09-28": (0, 9, 0, 0, 2, 0, 2),
    "2026-09-29": (1, 9, 0, 0, 2, 0, 3),
    "2026-09-30": (2, 9, 0, 0, 2, 0, 4),
    "2026-08-15": (5, 8, 1, 1, 0, 0, 8),
    "2026-08-17": (0, 8, 1, 0, 0, 0, 2),
}


def test_research_calendar_matches_hand_values():
    holidays, seol, chuseok = load_research_calendar(RESEARCH)
    index = pd.DatetimeIndex([datetime.fromisoformat(f"{day} 12:00") for day in EXPECTED])
    frame = calendar(index, holidays, seol, chuseok)
    for stamp, expected in EXPECTED.items():
        row = frame.loc[pd.Timestamp(f"{stamp} 12:00")]
        got = (
            int(row.dow),
            int(row.month),
            int(row.hol),
            int(row.hol_wkend),
            int(row.big),
            float(row.to_hol),
            float(row.from_hol),
        )
        assert got == expected, stamp
