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


# --- Step 1 规格 AND 门限 (name 与 spec 都要匹配才算同一商品) --------------


def test_same_name_different_spec_separated():
    """同名不同牌号/规格必须分簇(无缝管 A108 75217 vs A159 5190 污染案例)。"""
    samples = [
        ("无缝管 A108", {}),
        ("无缝管 A108", {}),
        ("无缝管 A159", {}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert result.labels[0] == result.labels[1]
    assert result.labels[0] != result.labels[2]  # A159 独行 → noise


def test_same_spec_different_names_not_merged():
    """规格 one-hot 大权重的老缺陷回归位: 不同商品同规格(444 vs 258)不得合并。"""
    samples = [("大理石 20mm", {}), ("人造石 20mm", {})]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert result.labels[0] == -1 and result.labels[1] == -1


def test_unspecified_items_not_mixed_into_specified_cluster():
    """无规格行与有规格行: 未知≠匹配,不混簇;无规格行彼此按名称聚类(407/504 现状)。"""
    samples = [
        ("无缝管 A159", {}),
        ("无缝管", {}),
        ("无缝管", {}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert result.labels[1] == result.labels[2]
    assert result.labels[0] != result.labels[1]


def test_same_category_different_goods_not_merged():
    """真机 81 条 mega 簇回归位: 同分类短名(电源线/监控模块)靠分类字符串
    塌成一团——分类不再进文本,不同名必须分离。"""
    samples = [
        ("电源线", {"category": "消防电源监控"}),
        ("消防电源监控主机", {"category": "消防电源监控"}),
        ("管内穿线铜芯导 线", {"category": "照明安装工程"}),
        ("砖、混凝土结构 暗配镀锌配管", {"category": "照明安装工程"}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert all(l == -1 for l in result.labels)  # 四组互不相似, 全部落单


def test_same_name_different_category_separated():
    """设计 §1.3: 同名不同分类必须分簇(类目 AND 门限)。"""
    samples = [
        ("管内穿线铜芯导线", {"category": "照明安装工程"}),
        ("管内穿线铜芯导线", {"category": "B4应急照明安装工程"}),
        ("管内穿线铜芯导线", {"category": "照明安装工程"}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert result.labels[0] == result.labels[2]
    assert result.labels[0] != result.labels[1]


def test_category_missing_is_neutral():
    """一方分类缺失 → 不设门槛(不惩罚提取缺口),按名称聚类。"""
    samples = [
        ("管内穿线铜芯导线", {"category": "照明安装工程"}),
        ("管内穿线铜芯导线", {}),
        ("管内穿线铜芯导线", {}),
    ]
    result = cluster_items(samples, eps=0.6, min_samples=2)
    assert result.labels[0] == result.labels[1] == result.labels[2]
