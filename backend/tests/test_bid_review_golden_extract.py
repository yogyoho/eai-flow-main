"""抽取层金标准评分器测试(B立项 M0,spec 2026-11-04 §3,EAI-CUSTOM)。
四类检查(value/count/contains/shape)+R6 快照离线回归门+已知真值锚点。"""

from app.extensions.bid_review.golden.extract import (
    load_annotations,
    load_snapshot,
    score_fields,
    score_snapshots,
)


def _fields():
    return load_snapshot()["fields"]


def test_value_scalar_pass_and_fail():
    ann = {"checks": [{"path": "bid.total_price", "kind": "value", "expect": 980000}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1
    ann_bad = {"checks": [{"path": "bid.total_price", "kind": "value", "expect": 999}]}
    assert score_fields(_fields(), ann_bad)["summary"]["failed"] == 1


def test_value_duration_dict_normalized():
    ann = {"checks": [{"path": "bid.duration_main_text", "kind": "value", "expect": {"value": 180, "unit": "day"}}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1
    fields = {"bid.duration_main_text": {"value": "180", "unit": "day"}}
    assert score_fields(fields, ann)["summary"]["passed"] == 1


def test_count_exact():
    ann = {"checks": [{"path": "bid.attachment_index", "kind": "count", "expect": 3}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1
    ann_bad = {"checks": [{"path": "bid.attachment_index", "kind": "count", "expect": 2}]}
    assert score_fields(_fields(), ann_bad)["summary"]["failed"] == 1


def test_contains_dict_subset_with_name_normalization():
    ann = {"checks": [{"path": "tender.attachment_requirements", "kind": "contains", "expect": {"name": "安全生产许可证", "mandatory": "★", "min_count": 1}}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1
    ann2 = {"checks": [{"path": "bid.appendix_references", "kind": "contains", "expect": {"name": "营业执照"}}]}
    assert score_fields(_fields(), ann2)["summary"]["passed"] == 1
    ann3 = {"checks": [{"path": "bid.appendix_references", "kind": "contains", "expect": {"name": "不存在的附件"}}]}
    assert score_fields(_fields(), ann3)["summary"]["failed"] == 1


def test_contains_scalar_list():
    ann = {"checks": [{"path": "tender.substantive_clauses", "kind": "contains", "expect": "★附件2 安全生产许可证"}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1


def test_shape_requires_nonempty_dict_list_with_keys():
    ann = {"checks": [{"path": "bid.amount_occurrences", "kind": "shape", "expect": {"min_len": 1, "keys": ["value", "where"]}}]}
    assert score_fields(_fields(), ann)["summary"]["passed"] == 1
    for bad in (None, [], ["人民币"], [{"value": "x"}]):
        rep = score_fields({"bid.amount_occurrences": bad}, ann)
        assert rep["summary"]["failed"] == 1, bad


def test_missing_field_is_fail_not_crash():
    ann = {"checks": [{"path": "bid.nonexistent", "kind": "value", "expect": 1}]}
    assert score_fields({}, ann)["summary"]["failed"] == 1


def test_snapshot_anchors():
    """已知真值锚点(人工读原文,R6 活体已证)必须 pass。"""
    rep = score_fields(_fields(), load_annotations())
    by_path = {r["path"]: r["verdict"] for r in rep["rows"] if r["kind"] == "value"}
    assert by_path["bid.total_price"] == "pass"
    assert by_path["tender.max_price"] == "pass"
    appendix_rows = [r for r in rep["rows"] if r["path"] == "bid.appendix_references"]
    assert appendix_rows and all(r["verdict"] == "pass" for r in appendix_rows)


def test_snapshot_gate_baseline():
    """离线回归门:快照评分 ≥ meta.baseline_pass_rate(null=首标前仅要求跑通)。"""
    baseline = load_annotations()["meta"].get("baseline_pass_rate")
    rep = score_snapshots()
    assert rep["summary"]["total"] == 26
    if baseline is not None:
        assert rep["summary"]["pass_rate"] >= baseline
