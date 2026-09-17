"""seed 库结构契约: 7 条内置规则,每条满足 seed 确认条件的最低字段。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds


def test_default_library_has_seven_seeds():
    assert len(DEFAULT_TABLE_SEEDS) == 7
    for s in DEFAULT_TABLE_SEEDS:
        assert s["id"] and s["display_name"]
        assert s["columns"]["name"], f"{s['id']} 缺 name 锚点"
        assert s["columns"]["price_unit"] or s["columns"]["price_total"], (
            f"{s['id']} 缺价格锚点"
        )


def test_normalize_seeds_drops_invalid_and_fills_defaults():
    raw = [
        {"id": "ok", "display_name": "x", "columns": {"name": ["品名"], "price_unit": ["单价"]}},
        {"id": "", "display_name": "bad"},
        "not-a-dict",
        {"id": "nocost", "display_name": "y", "columns": {"name": ["品名"]}},
        # 敌意输入: 非 list 列锚点 + 非 dict exclude —— 必须被丢弃而非崩溃
        {"id": "h", "display_name": "x", "columns": {"name": ["品名"], "price_unit": "单价"}, "exclude": "不含税"},
        # 重复 id: keep-first
        {"id": "ok", "display_name": "dup", "columns": {"name": ["品名"], "price_unit": ["单价"]}},
    ]
    out = normalize_seeds(raw)
    assert [s["id"] for s in out] == ["ok"]
    # 存活条目全形: 7 列角色齐备/exclude 缺省 {} /source 缺省 None
    assert sorted(out[0]["columns"].keys()) == ["name", "price_total", "price_unit", "price_untaxed", "qty", "spec", "unit"]
    assert out[0]["exclude"] == {}
    assert out[0]["source"] is None


def test_price_unit_exclude_guards_untaxed():
    """含税单价 seed 必须排除 不含税 列(子串陷阱)——遍历全部 seed。"""
    for s in DEFAULT_TABLE_SEEDS:
        if any("含税" in t for t in s["columns"]["price_unit"]):
            assert "不含税" in s.get("exclude", {}).get("price_unit", []), (
                f"{s['id']} 含税单价未排除 不含税 列"
            )
