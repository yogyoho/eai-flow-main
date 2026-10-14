"""cluster 相位 pins 装载纯函数（cpa v3 术语, spec 2026-10-14 §2.3）。

merge_pins(terms, legacy): 启用术语优先,legacy config.json merge_pins 过渡兼容;
归一化 canonical 撞车时 legacy 条目丢弃（aliases 已被术语覆盖的先验不再重复喂引擎）。
"""

from scripts.cli import _merge_pins


def test_terms_win_and_legacy_dedupes():
    terms = [
        {"name": "锚杆", "aliases": ["锚杆Φ22", "树脂锚杆"]},
        {"name": "钢绞线", "aliases": ["矿用钢绞线"]},
    ]
    legacy = [
        {"name": "锚杆", "aliases": ["玻璃钢锚杆"]},  # 与术语 canonical 撞车 → 丢
        {"name": "U型卡", "aliases": ["卡缆"]},  # 新 → 保留
    ]
    out = _merge_pins(terms, legacy)
    assert out[0] == {"name": "锚杆", "aliases": ["锚杆Φ22", "树脂锚杆"]}
    assert out[1] == {"name": "钢绞线", "aliases": ["矿用钢绞线"]}
    assert out[2] == {"name": "U型卡", "aliases": ["卡缆"]}
    assert len(out) == 3


def test_legacy_alias_only_collision_dropped():
    # legacy 条目 canonical 是空但别名撞术语 canonical → 也算撞车（去空白归一化比对全体名）
    terms = [{"name": "锚杆", "aliases": []}]
    legacy = [{"name": "锚  杆", "aliases": ["x"]}]  # 归一化后 == 锚杆
    assert _merge_pins(terms, legacy) == terms


def test_empty_terms_passes_legacy_through():
    legacy = [{"name": "U型卡", "aliases": ["卡缆"]}]
    assert _merge_pins([], legacy) == legacy


def test_disabled_terms_not_imported_here():
    # 过滤 enabled 是 _load_terms_pins 的 SQL 职责;纯函数只管合并——文档性断言
    assert _merge_pins([], []) == []
