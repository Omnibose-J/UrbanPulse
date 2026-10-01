"""Floor versus the research round-half-even hour."""

from datetime import datetime

from engine.hourly import floor_hour, research_hour
from engine.parsers import KST


def test_floor_keeps_ten_thirty_in_hour_ten_and_eleven_thirty_in_hour_eleven():
    ten = floor_hour(datetime(2026, 8, 29, 10, 30, tzinfo=KST))
    eleven = floor_hour(datetime(2026, 8, 29, 11, 30, tzinfo=KST))
    assert ten.hour == 10
    assert eleven.hour == 11


def test_research_grid_puts_ten_thirty_in_ten_and_eleven_thirty_in_twelve():
    ten = research_hour(datetime(2026, 8, 29, 10, 30, tzinfo=KST))
    eleven = research_hour(datetime(2026, 8, 29, 11, 30, tzinfo=KST))
    assert (ten.hour, eleven.hour) == (10, 12)
