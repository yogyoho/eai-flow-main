"""L4 独立包离线态(A-β2-③④⑤):加载/lint/映射/golden-scripted 两题;live-off=worker 单包不接线(构造性)。"""

from app.extensions.bid_review.engine import registry
from app.extensions.bid_review.engine.rule_runner import Rule, load_rulepack

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-l4/1.0.0.yaml"


def test_l4_pack_loads_and_lints():
    pack = load_rulepack(PACK)
    assert len(pack.rules) == 10
    assert registry.lint_rules(pack.rules) == []


def _l4_rule(**over):
    # Rule 字段集以 rule_runner 实际 dataclass 为准(plan 底稿缺 fix_tpl/confidence_gate 必填项,补齐)
    base = dict(
        id="L4-T",
        name="t",
        layer="L4",
        type="semantic",
        applies_to=["*"],
        inputs=["bid.full_text"],
        check={"per_clause": True, "steps": [], "verdict_set": ["full", "partial", "none", "unclear"]},
        severity="info",
        evidence=[],
        message_tpl="m",
        fix_tpl="f",
        confidence_gate=1.0,
        enabled=True,
    )
    base.update(over)
    return Rule(**base)


def test_l4_fatal_rejected():
    assert any("fatal" in p for p in registry.lint_rules([_l4_rule(severity="fatal")]))


def test_l4_severity_mapping_recorded():
    pack = load_rulepack(PACK)
    sev = {r.id: r.severity for r in pack.rules}
    assert sev["L4-001"] == "major" and sev["L4-008"] == "minor" and sev["L4-010"] == "info"


def test_l4_inputs_named_per_adjudication():
    pack = load_rulepack(PACK)
    all_in = {p for r in pack.rules for p in r.inputs}
    assert "bid.warranty_period" in all_in and "bid.warranty_months" not in all_in  # repo 名优先
    assert "bid.service_commitments" in all_in and "tender.clauses" in all_in  # 新路径规格名
