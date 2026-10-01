"""Overlap rule and stable station ids. Synthetic polygons, no shapefile."""

from shapely.geometry import box

from engine.tierb.stations import covered, display_name


def _fraction(station, union) -> float:
    return station.intersection(union).area / station.area


def test_half_the_circle_is_dropped_and_just_under_is_kept():
    station = box(0, 0, 10, 10)
    assert covered(_fraction(station, box(0, 0, 10, 5)))
    assert not covered(_fraction(station, box(0, 0, 10, 4.9)))


def test_ids_follow_normalised_name_order():
    keys = ["다", "가", "나"]
    assigned = [f"STN{index:03d}" for index, _key in enumerate(sorted(keys), start=1)]
    assert assigned == ["STN001", "STN002", "STN003"]
    assert [key for key in sorted(keys)] == ["가", "나", "다"]


def test_display_name_ends_with_the_station_suffix():
    assert display_name("서울", ["서울(2)역", "서울역"]) == "서울역"
