from scripts.parse_spec import parse_spec
from scripts.extract import build_report
from scripts.grounding_check import check, corpus


def _mapping():
    return {
        "report_title": "T",
        "sections": [
            {"fire": "1 概况", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "占地面积23.8亩"}]},
            {"fire": "2 消防水", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "室外消火栓水量30L/s"}]},
            {"fire": "3 表", "class": "verbatim",
             "sources": [{"kind": "table", "no": "表2.1-1"}]},
        ],
        "templates": {},
    }


def test_all_blocks_grounded(tiny_spec):
    s = parse_spec(tiny_spec)
    report = build_report(s, _mapping())
    res = check(report, s, _mapping())
    assert res["checked"] >= 3
    assert res["grounded"] == res["checked"]
    assert res["rate"] == 1.0
    assert res["missing_anchors"] == []


def test_missing_anchor_reported(tiny_spec):
    s = parse_spec(tiny_spec)
    m = _mapping()
    m["sections"][0]["sources"][0]["anchor"] = "不存在ZZZ"
    res = check(build_report(s, m), s, m)
    assert len(res["missing_anchors"]) == 1
    assert res["missing_anchors"][0][0] == "1 概况"


def test_drift_detected(tiny_spec):
    s = parse_spec(tiny_spec)
    report = build_report(s, _mapping()) + "\n\n这是一段说明书里没有的编造内容用于触发漂移检测。\n"
    res = check(report, s, _mapping())
    assert res["grounded"] < res["checked"]
    assert res["rate"] < 1.0
