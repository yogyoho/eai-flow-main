"""Tests for the text+param vectorizer."""

import numpy as np

from scripts.clustering.vectorizer import Vectorizer


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
