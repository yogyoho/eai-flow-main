"""Tests for the DBSCAN clustering engine."""

from scripts.clustering.engine import cluster_items


def test_clusters_group_similar_goods():
    samples = [
        ("高压开关柜", {"电压": "10kV", "电流": "630A"}),
        ("10kV高压开关柜", {"电压": "10kV", "电流": "630A"}),
        ("变压器", {"容量": "1000kVA"}),
        ("电力变压器", {"容量": "1000kVA"}),
        ("特殊定制非标设备XYZ", {"电压": "999kV"}),  # outlier
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    # The two 开关柜 together, the two 变压器 together, the outlier as noise.
    assert result.labels[0] == result.labels[1]
    assert result.labels[2] == result.labels[3]
    assert result.labels[0] != result.labels[2]
    assert -1 in result.labels  # outlier detected


def test_noise_items_separated_when_too_sparse():
    samples = [("A设备", {}), ("B设备", {}), ("C设备", {})]
    result = cluster_items(samples, eps=0.3, min_samples=2)
    # No two are similar enough → all noise.
    assert all(l == -1 for l in result.labels)


def test_empty_samples_returns_empty():
    result = cluster_items([])
    assert result.labels == []
    assert result.representatives == {}


def test_representative_name_populated():
    samples = [
        ("高压开关柜", {"电压": "10kV"}),
        ("高压开关柜", {"电压": "10kV"}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert len(result.representatives) == 1
    # Representative is the first member of the cluster.
    rep = next(iter(result.representatives.values()))
    assert rep == "高压开关柜"
