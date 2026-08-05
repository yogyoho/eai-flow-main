from scripts.parse_spec import parse_spec
from scripts.extract import build_report
from scripts.grounding_check import check


def _mini_outline():
    """两层的骨架层：只含节名/类别，源全部外置到 mapping。"""
    return {
        "report_title": "{项目名} 消防设计专篇",
        "sections": [
            {"fire": "1 概况", "class": "verbatim", "heading_level": 3},
            {"fire": "2 消防水", "class": "verbatim", "heading_level": 3},
            {"fire": "3 表", "class": "verbatim", "heading_level": 3},
        ],
        "templates": {},
    }


def _mini_mapping():
    """按索引与 _mini_outline().sections 对齐的源映射。"""
    return {"sources": [
        [{"kind": "para", "paras": [7]}],        # 1 概况 → 项目概况段
        [{"kind": "para", "paras": [12]}],       # 2 消防水 → 消防水量段
        [{"kind": "table", "no": "表2.1-1"}],    # 3 表 → 消防水量表
    ]}


def test_all_blocks_grounded(tiny_spec):
    s = parse_spec(tiny_spec)
    outline = _mini_outline()
    mapping = _mini_mapping()
    report = build_report(s, outline, mapping)
    res = check(report, s, outline, mapping)
    assert res["checked"] >= 3
    assert res["grounded"] == res["checked"]
    assert res["rate"] == 1.0
    assert res["missing_anchors"] == []


def test_missing_anchor_reported(tiny_spec):
    s = parse_spec(tiny_spec)
    outline = _mini_outline()
    mapping = _mini_mapping()
    mapping["sources"][0][0]["paras"] = [9999]
    res = check(build_report(s, outline, mapping), s, outline, mapping)
    assert len(res["missing_anchors"]) == 1
    assert res["missing_anchors"][0][0] == "1 概况"


def test_drift_detected(tiny_spec):
    s = parse_spec(tiny_spec)
    outline = _mini_outline()
    mapping = _mini_mapping()
    report = build_report(s, outline, mapping) + "\n\n这是一段说明书里没有的编造内容用于触发漂移检测。\n"
    res = check(report, s, outline, mapping)
    assert res["grounded"] < res["checked"]
    assert res["rate"] < 1.0


def test_conflict_assertions_checked(tiny_spec):
    s = parse_spec(tiny_spec)
    outline = _mini_outline()
    mapping = _mini_mapping()
    outline["sections"][1]["conflict_assertions"] = [{"must_contain": "30L/s", "must_not_contain": "DN150"}]
    res = check(build_report(s, outline, mapping), s, outline, mapping)
    assert res["conflict_failures"] == []
    # break it: require something absent
    outline["sections"][1]["conflict_assertions"] = [{"must_contain": "ZZZNOMATCH"}]
    res2 = check(build_report(s, outline, mapping), s, outline, mapping)
    assert len(res2["conflict_failures"]) == 1
