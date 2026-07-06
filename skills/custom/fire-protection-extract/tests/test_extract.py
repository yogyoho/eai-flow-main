import yaml
from pathlib import Path
from scripts.parse_spec import parse_spec
from scripts.extract import extract, build_report


def _structure(tiny_spec):
    return parse_spec(tiny_spec)


def _tiny_mapping():
    return {
        "report_title": "T 消防设计专篇",
        "sections": [
            {"fire": "2.1 概况", "class": "verbatim",
             "sources": [{"kind": "para", "paras": [7]}]},
            {"fire": "2.2 给水(冲突)", "class": "verbatim",
             "sources": [{"kind": "para", "paras": [12], "authoritative": True}]},
            {"fire": "2.3 表", "class": "verbatim",
             "sources": [{"kind": "table", "no": "表2.1-1"}]},
            {"fire": "3 投资", "class": "compute", "note": "无源"},
        ],
        "templates": {},
    }


def test_extract_verbatim_para_and_table(tiny_spec):
    body, cites = extract(_structure(tiny_spec), _tiny_mapping())
    assert "占地面积23.8亩" in body
    assert "30L/s（108m³/h）" in body
    assert "室外消火栓" in body and "水量" in body
    assert "[需计算]" in body
    assert ("2.2 给水(冲突)", "¶") in [(c[0], c[1]) for c in cites]


def test_extract_conflict_uses_authoritative_not_wrong_source(tiny_spec):
    body, _ = extract(_structure(tiny_spec), _tiny_mapping())
    assert "8L/s" not in body
    assert "DN150" not in body
    assert "30L/s" in body and "DN200" in body


def test_missing_anchor_is_flagged_not_silent(tiny_spec):
    m = _tiny_mapping()
    m["sections"][0]["sources"] = [{"kind": "para", "paras": [9999]}]
    body, _ = extract(_structure(tiny_spec), m)
    assert "[⚠未找到段落" in body


def test_build_report_has_title_and_headings(tiny_spec):
    md = build_report(_structure(tiny_spec), _tiny_mapping(), project_name="基地项目")
    assert md.startswith("# 基地项目 消防设计专篇")
    assert "## 2.1 概况" in md
