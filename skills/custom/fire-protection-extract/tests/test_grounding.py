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
             "sources": [{"kind": "para", "anchor": "生活用水量10L/s（36m³/h）"}]},
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


def test_conflict_assertions_checked(tiny_spec):
    s = parse_spec(tiny_spec)
    m = _mapping()
    m["sections"][1]["conflict_assertions"] = [{"must_contain": "30L/s", "must_not_contain": "DN150"}]
    res = check(build_report(s, m), s, m)
    assert res["conflict_failures"] == []
    # break it: require something absent
    m["sections"][1]["conflict_assertions"] = [{"must_contain": "ZZZNOMATCH"}]
    res2 = check(build_report(s, m), s, m)
    assert len(res2["conflict_failures"]) == 1
