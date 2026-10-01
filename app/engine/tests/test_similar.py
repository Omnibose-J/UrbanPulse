"""Cosine neighbours. The visitors block is all-or-nothing."""

from engine.similar import feature_vectors, top_others, use_visitors


def test_identical_vectors_score_one_without_a_self_row():
    ids = ["POI001", "POI002", "POI003"]
    commerce = {place: [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for place in ids}
    categories = {place: "카페" for place in ids}
    vectors = feature_vectors(ids, commerce, categories, None)
    ranked = top_others(ids, vectors)
    assert [other for _, other, _ in ranked["POI001"]] == ["POI002", "POI003"]
    assert all(abs(score - 1) < 1e-9 for _, _, score in ranked["POI001"])
    assert all(other != "POI001" for _, other, _ in ranked["POI001"])
    assert [rank for rank, _, _ in ranked["POI001"]] == [1, 2]


def test_visitors_block_is_dropped_when_one_place_lacks_28_days():
    counts = {"POI001": 28, "POI002": 28}
    assert use_visitors(counts) is True
    counts["POI003"] = 27
    assert use_visitors(counts) is False
    ids = ["POI001", "POI002"]
    commerce = {place: [0.0] * 8 for place in ids}
    visitors = {"POI001": [1.0, 0.0], "POI002": [0.0, 1.0]}
    without = feature_vectors(ids, commerce, {"POI001": "a", "POI002": "b"}, None)
    with_visitors = feature_vectors(ids, commerce, {"POI001": "a", "POI002": "b"}, visitors)
    assert len(with_visitors[0]) > len(without[0])
