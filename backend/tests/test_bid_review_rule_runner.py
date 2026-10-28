import re
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.rule_runner import RulePackError, load_rulepack, run_det_rule

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")


def test_load_and_validate():
    pack = load_rulepack(PACK)
    ids = {r.id for r in pack.rules}
    assert {"L1-009", "L1-010", "L1-011", "L3-001", "L3-003", "L3-005", "L3-006"} <= ids


def test_unknown_operator_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "rules:\n- id: X-001\n  name: 坏规则\n  layer: L1\n  type: deterministic\n  severity: fatal\n"
        "  applies_to: ['*']\n  inputs: [a]\n  check: {op: explode}\n  evidence: []\n"
        "  message_tpl: m\n  fix_tpl: f\n  confidence_gate: 1.0\n  enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(RulePackError):
        load_rulepack(str(bad))


def test_run_l1_009_violation_and_need_human():
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-009"]
    bad = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
    issues = run_det_rule(rule, bad)
    assert issues[0]["verdict"] == "violation" and issues[0]["severity"] == "fatal"
    assert "1,000,001" in issues[0]["message"]
    pre_false = {**bad, "bid.price_includes_tax": False, "tender.price_includes_tax": True}
    assert run_det_rule(rule, pre_false) == []
    assert run_det_rule(rule, {"bid.total_price": 1.0})[0]["verdict"] == "need_human"


def test_run_l3_006_structural_all_var_attr():
    """评审修正 A7 回归门:结构级 all 把行 dict 以 var 名并入 env 后求 cond;_tpl 走 _resolve(var-attr)+money 格式。"""
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L3-006"]
    fields = {"bid.total_price": 1000001.0, "bid.amount_occurrences": [{"where": "承诺函", "value": 900000.0}]}
    issues = run_det_rule(rule, fields)
    assert issues and issues[0]["verdict"] == "violation"
    assert "900,000.00" in issues[0]["message"] and "承诺函" in issues[0]["message"]
    assert not re.search(r"\{[\w.]+(?::\w+)?\}", issues[0]["message"]), f"残留占位符: {issues[0]['message']}"
    ok = {**fields, "bid.amount_occurrences": [{"where": "承诺函", "value": 1000001.0}]}
    assert run_det_rule(rule, ok) == []
    assert run_det_rule(rule, {"bid.total_price": 1.0})[0]["verdict"] == "need_human"


def test_run_l3_006_empty_and_none_where_no_none_literal():
    """评审修正 A11a(2) 回归门:空串 where 按原文传递(() 形态);None where 不渲染 "None" 字面量;金额数字完整无残缺。"""
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L3-006"]
    for where in ("", None):
        fields = {"bid.total_price": 1000001.0, "bid.amount_occurrences": [{"where": where, "value": 900000.0}]}
        msg = run_det_rule(rule, fields)[0]["message"]
        assert "¥900,000.00" in msg and "¥1,000,001.00" in msg, f"L3-006 where={where!r} 数字不完整: {msg}"
        assert "None" not in msg, f"L3-006 where={where!r} 泄漏 None 字面量: {msg}"
        assert not re.search(r"\{[\w.]+(?::\w+)?\}", msg), f"残留占位符: {msg}"
