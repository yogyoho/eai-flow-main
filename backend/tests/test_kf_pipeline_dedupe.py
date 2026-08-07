"""Unit tests for table_schemas result-layer dedup (P1, bug 膨胀).

Regression: 给排水 7 源表 → 26 schema, tbl_03_01 复用 5 次。
_dedupe_table_schemas 按 (caption, columns) 全局去重，保留叶子最深且文档序早的。
"""

from app.extensions.knowledge_factory.pipeline import _dedupe_table_schemas


def _table(table_id, caption, headers):
    return {
        "table_id": table_id,
        "caption": caption,
        "columns": [{"header": h} for h in headers],
    }


def _sec(id, tables, children=None):
    sec = {"id": id, "title": id, "table_schemas": tables}
    if children is not None:
        sec["children"] = children
    return sec


def test_dedupe_removes_same_caption_columns():
    """同 (caption, columns) 的 schema 只保留一份。"""
    t1 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位", "进界区压力"])
    t2 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位", "进界区压力"])
    sections = [
        _sec("sec_03", [t1]),
        _sec("sec_03_02", [t2]),
    ]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    # 保留叶子最深（sec_03_02 depth 2 > sec_03 depth 1）
    remaining = [t["table_id"] for s in sections for t in (s.get("table_schemas") or [])]
    assert len(remaining) == 1
    assert remaining == ["tbl_03_01"]


def test_dedupe_keeps_different_caption_same_columns():
    """不同 caption 同列（如吸水管/出水管）不误删。"""
    t1 = _table("tbl_08_01", "循环水泵吸水管水力计算表", ["输送水量", "管径", "流速", "i"])
    t2 = _table("tbl_08_02", "循环水泵出水管水力计算表", ["输送水量", "管径", "流速", "i"])
    sections = [_sec("sec_08", [t1, t2])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 0
    assert len(sections[0]["table_schemas"]) == 2


def test_dedupe_keeps_deepest_leaf():
    """同 (caption, cols)：父节(depth 1) 与叶子(depth 2) 并存 → 保留叶子。"""
    t_parent = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    t_leaf = _table("tbl_03_02_01", "循环水水量统计表", ["序号", "用水单位"])
    sections = [_sec("sec_03", [t_parent], children=[_sec("sec_03_02", [t_leaf])])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    # 叶子 sec_03_02 保留，父节 sec_03 的移除
    assert sections[0]["table_schemas"] == []
    assert sections[0]["children"][0]["table_schemas"] == [t_leaf]


def test_dedupe_keeps_earliest_when_same_depth():
    """同 (caption, cols) 同深度：保留文档序早的。"""
    t1 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    t2 = _table("tbl_03_01", "循环水水量统计表", ["序号", "用水单位"])
    sections = [_sec("sec_02_01", [t1]), _sec("sec_03_01", [t2])]
    removed = _dedupe_table_schemas(sections)
    assert removed == 1
    assert sections[0]["table_schemas"] == [t1]  # 文档序早的保留
    assert sections[1]["table_schemas"] == []
