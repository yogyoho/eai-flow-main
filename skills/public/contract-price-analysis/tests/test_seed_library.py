"""seed 库结构契约: 6 条内置规则,每条满足 seed 确认条件的最低字段。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds


def test_default_library_has_six_seeds():
    assert len(DEFAULT_TABLE_SEEDS) == 6
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
    ]
    out = normalize_seeds(raw)
    assert [s["id"] for s in out] == ["ok"]


def test_price_unit_exclude_guards_untaxed():
    """含税单价 seed 必须排除 不含税 列(子串陷阱)。"""
    gcl = next(s for s in DEFAULT_TABLE_SEEDS if s["id"] == "gcl-qd")
    assert "不含税" in gcl.get("exclude", {}).get("price_unit", [])
