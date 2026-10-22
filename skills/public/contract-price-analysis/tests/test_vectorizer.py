"""Tests for the text+param vectorizer."""

import numpy as np

from scripts.clustering.vectorizer import Vectorizer, spec_extract


def test_fit_transform_returns_vector():
    v = Vectorizer()
    v.fit([("高压开关柜", {"电压": "10kV"}), ("变压器", {"容量": "1000kVA"})])
    vec = v.transform("高压开关柜", {"电压": "10kV"})
    assert vec.ndim == 1
    assert vec.shape[0] > 0


# v2 移除参数差分(见 vectorizer.py docstring): DN one-hot 承担区分职责


def test_different_writings_of_same_goods_are_close():
    v = Vectorizer()
    v.fit([("高压开关柜", {}), ("10kV高压开关柜", {})])
    a = v.transform("高压开关柜", {})
    b = v.transform("10kV高压开关柜", {})
    # Char-ngram TF-IDF of two near-identical strings should be meaningfully
    # similar (cosine well above 0, i.e. clustering distance < eps=0.6).
    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    assert sim > 0.4


def test_unknown_param_keys_ignored():
    v = Vectorizer()
    v.fit([("设备A", {"电压": "10kV", "颜色": "红"})])
    # "颜色" is not a canonical param field → only "电压" is a numeric dim
    vec = v.transform("设备A", {"电压": "10kV", "颜色": "红"})
    assert vec.shape[0] > 0


def test_spec_token_families_and_normalization():
    from scripts.clustering.vectorizer import spec_tokens

    # 各 token 族 + 归一化(空白/大小写) + CJK 邻接(管A108 无 \b 边界也能抽到)
    toks = spec_tokens("衬塑钢管及管件 DN 50 PN=1.25MPa")
    assert toks == ["DN50", "PN=1.25"]
    assert spec_tokens("无缝管A108") == ["A108"]
    assert spec_tokens("螺纹钢 φ12") == ["Φ12"]
    assert spec_tokens("人造石 20mm") == ["20MM"]
    assert spec_tokens("钢板 Q235B") == ["Q235B"]
    assert spec_tokens("螺纹钢") == []  # 无规格 → 空,不设门槛


def test_spec_token_names_only_within_text():
    """规格 token 从样本文本(name+spec+category 拼接)整体抽取,与来源无关。"""
    from scripts.clustering.vectorizer import spec_tokens

    # spec_model 在 cli._cluster_sample_text 里拼在名称后面
    assert "DN100" in spec_tokens("镀锌钢管 DN100 未分类")


class TestSpecTokenBlindSpots:
    """2026-10-22 盲区补全: De/SC 管径、芯/匹/联数、字母型号串必须成为规格
    token(不同 token = Jaccard 0 = 硬分簇);常见非规格名不得误抽。"""

    def test_de_diameter_tokens_differ(self):
        a, _ = spec_extract("PVC-U塑料排水管及管件 De110")
        b, _ = spec_extract("PVC-U塑料排水管及管件 De50")
        assert a != b and "DE110" in a and "DE50" in b

    def test_sc_conduit_tokens_differ(self):
        a, _ = spec_extract("钢管埋地敷设SC100")
        b, _ = spec_extract("钢管埋地敷设SC50")
        assert a != b

    def test_fiber_core_count(self):
        a, _ = spec_extract("48芯单模光缆")
        b, _ = spec_extract("管内2芯单模光缆")
        assert "48芯" in a and "2芯" in b and a != b

    def test_ac_horsepower(self):
        a, _ = spec_extract("1匹分体式空调")
        b, _ = spec_extract("5匹分体式空调")
        assert a != b

    def test_switch_gang_count(self):
        a, _ = spec_extract("单联单控跷板暗开关")
        b, _ = spec_extract("三联联单控跷板暗开关")
        assert "单联" in a and "三联" in b and a != b

    def test_model_gqq_family(self):
        a, _ = spec_extract("七氟丙烷无管网灭火装置 GQQ90X2/2.5-PAVLN")
        b, _ = spec_extract("七氟丙烷无管网灭火装置 GQQ120/2.5-PAVLN")
        assert a != b  # 90X2 vs 120 → 不同 token

    def test_model_dz_dash_family(self):
        a, _ = spec_extract("低噪声轴流风机DZ-13-6B")
        b, _ = spec_extract("低噪声轴流风机DZ-13-3.2D")
        assert a != b  # 全串 DZ-13-6B vs DZ-13-3.2D

    def test_no_false_positive_on_common_names(self):
        # 非规格名不得抽出 token
        for name in ("LED灯", "A型出口指示灯(中型)", "PVC-U塑料排水管及管件", "PP-R塑料给水管"):
            toks, stripped = spec_extract(name)
            assert toks == [], (name, toks)
            assert stripped == name  # 无 token 也不得改写名称文本

    def test_existing_dn_still_works(self):
        a, _ = spec_extract("热镀锌无缝钢管 DN32")
        b, _ = spec_extract("热镀锌无缝钢管 DN150")
        assert a != b and a == ["DN32"]
