"""Tests for price statistics computation."""

from scripts.stats import compute_stats


def test_compute_stats_basic():
    prices = [100.0, 200.0, 300.0, 400.0, 500.0]
    s = compute_stats(prices)
    assert s["count"] == 5
    assert s["mean"] == 300.0
    assert s["min"] == 100.0
    assert s["max"] == 500.0
    assert s["median"] == 300.0
    assert s["std"] > 0


def test_compute_stats_empty():
    s = compute_stats([])
    assert s["count"] == 0
    assert s["mean"] is None
    assert s["min"] is None


def test_compute_stats_single():
    s = compute_stats([42.0])
    assert s["count"] == 1
    assert s["mean"] == 42.0
    assert s["std"] == 0.0
    assert s["outlier_count"] == 0


def test_compute_stats_outlier_flag():
    # 100000 is far beyond mean + 3*std of an otherwise tight cluster.
    prices = [100.0, 110.0, 105.0, 100000.0]
    s = compute_stats(prices)
    assert s["outlier_count"] == 1


def test_compute_stats_no_false_outlier():
    prices = [100.0, 110.0, 105.0, 115.0]
    s = compute_stats(prices)
    assert s["outlier_count"] == 0
