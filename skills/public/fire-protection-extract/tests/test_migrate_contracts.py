import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate_contracts


def _struct():
    return {"paras": [{"i": 0, "text": "段落甲 消防 DN200"}, {"i": 1, "text": "段落乙 给水 DN150"}, {"i": 2, "text": "段落丙"}], "tables": {}, "headings": []}


def test_empty_anchor_returns_none():
    assert migrate_contracts.find_para_index(_struct(), "") is None
    assert migrate_contracts.find_para_index(_struct(), None) is None


def test_convert_old_para_anchor_to_index():
    src = {"kind": "para", "anchor": "消防 DN200"}
    out = migrate_contracts.convert_source(src, _struct())
    assert out == {"kind": "para", "paras": [0]}


def test_convert_old_range_from_to():
    src = {"kind": "para_run", "from": "消防 DN200", "to": "段落丙"}
    out = migrate_contracts.convert_source(src, _struct())
    assert out == {"kind": "range", "paras": [0, 2]}


def test_convert_unresolvable_returns_none():
    assert migrate_contracts.convert_source({"kind": "para", "anchor": "不存在的内容"}, _struct()) is None
    assert migrate_contracts.convert_source({"kind": "para_run", "from": "不存在", "to": "段落丙"}, _struct()) is None


def test_section_number_no_overmatch():
    # 5.1 与 5.11 必须不互吞
    old = {"sections": [{"fire": "5.1 室外消防水系统", "sources": [{"kind": "para", "anchor": "消防 DN200"}], "conflict_assertions": [{"must_contain": "DN200"}]},
                        {"fire": "5.11 其他", "sources": []}]}
    outline = {"sections": [
        {"fire": "5.1 室外消防水系统", "class": "verbatim"},
        {"fire": "5.11 其他", "class": "verbatim"},
    ]}
    out = migrate_contracts.align_to_outline(old, _struct(), outline)
    assert out["sources"][0] and out["sources"][0][0]["paras"] == [0]
    assert out["sources"][1] is None


def test_main_rejects_already_migrated():
    import tempfile, os, json
    old = {"sources": []}  # 已是两层格式
    with tempfile.TemporaryDirectory() as d:
        oldp = os.path.join(d, "old.json")
        json.dump(old, open(oldp, "w", encoding="utf-8"))
        rc = migrate_contracts.main([oldp, "x.json", "基础设计", "outline.json", "out.json"])
        assert rc == 3
