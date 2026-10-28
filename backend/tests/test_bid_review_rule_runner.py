import re
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.expr import validate_expr
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


# 设计文档 §6.3 v1 落地清单(32 条):L1 det 14 + L1 sem 1(L1-013)+ L1 hyb 2(003/007);L3 det 13 + L3 hyb 2(004/008)
EXPECTED_V1_IDS = {
    "L1-001",
    "L1-002",
    "L1-003",
    "L1-005",
    "L1-006",
    "L1-007",
    "L1-008",
    "L1-009",
    "L1-010",
    "L1-011",
    "L1-012",
    "L1-013",
    "L1-014",
    "L1-015",
    "L1-016",
    "L1-019",
    "L1-021",
    "L3-001",
    "L3-002",
    "L3-003",
    "L3-004",
    "L3-005",
    "L3-006",
    "L3-007",
    "L3-008",
    "L3-009",
    "L3-010",
    "L3-012",
    "L3-013",
    "L3-014",
    "L3-016",
    "L3-018",
}


def test_full_pack_loads():
    """Task 18:全量规则包 1.0.0.yaml 转录门——ids>=32 且覆盖 §6.3 v1 清单;load_rulepack 逐条
    白名单校验(未知算子/函数/形态不识别即拒载,转录错误当场暴露);hyb 规则必须带 det_expr 粗筛
    标记且可解析(缺它 _hyb_det_prefilter 永不触发,hyb 静默退化纯语义)。"""
    pack = load_rulepack(PACK)
    ids = {r.id for r in pack.rules}
    assert len(ids) >= 32 and EXPECTED_V1_IDS <= ids, f"v1 清单缺规则: {sorted(EXPECTED_V1_IDS - ids)}"
    assert len(ids) == len(pack.rules), f"存在重复规则 id: {[r.id for r in pack.rules]}"
    by_type = {}
    for r in pack.rules:
        by_type.setdefault(r.type, []).append(r.id)
    assert len(by_type.get("deterministic", [])) == 27, "L1 det 14 + L3 det 13 = 27"
    assert len(by_type.get("hybrid", [])) == 4, "L1 hyb 003/007 + L3 hyb 004/008 = 4"
    assert len(by_type.get("semantic", [])) == 1, "L1-013 唯一 sem 规则"
    for r in pack.rules:
        if r.type == "hybrid":
            assert r.check.get("det_expr"), f"{r.id} hybrid 缺 det_expr(粗筛永不触发)"
            validate_expr(str(r.check["det_expr"]))


def test_det_rules_empty_fields_need_human_no_exprerror():
    """Task 18 Step 2:det/hyb 规则逐条用空 fields 跑一遍,全部返回 need_human 而非抛
    ExprError——证明每条表达式在缺字段下也合法(on_missing_input=need_human 短路生效);
    sem 规则无 det 执行路径(run_sem_rule 规则卡管线),不入本断言。"""
    pack = load_rulepack(PACK)
    executable = [r for r in pack.rules if r.type in ("deterministic", "hybrid")]
    assert len(executable) >= 31, f"det/hyb 可执行规则应 >=31 条,得 {len(executable)}"
    for rule in executable:
        issues = run_det_rule(rule, {})
        assert len(issues) == 1, f"{rule.id} 空 fields 应产 1 条 need_human,得 {issues}"
        assert issues[0]["verdict"] == "need_human" and issues[0]["need_human"] is True, f"{rule.id} 空 fields 应 need_human"
        assert issues[0]["rule_id"] == rule.id and issues[0]["source"] == "engine"
