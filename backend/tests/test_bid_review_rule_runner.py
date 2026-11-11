import copy
import re
import unittest
from pathlib import Path

import pytest
import yaml

from app.extensions.bid_review.engine.eval_core import wrap_model_fn
from app.extensions.bid_review.engine.expr import validate_expr
from app.extensions.bid_review.engine.llm_runner import run_sem_rule
from app.extensions.bid_review.engine.rule_runner import Rule, RulePackError, load_rulepack, run_det_rule

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
    assert issues[0]["verdict"] == "FAIL" and issues[0]["severity"] == "fatal"
    assert "1,000,001" in issues[0]["message"]
    pre_false = {**bad, "bid.price_includes_tax": False, "tender.price_includes_tax": True}
    assert run_det_rule(rule, pre_false) == []
    assert run_det_rule(rule, {"bid.total_price": 1.0})[0]["verdict"] == "UNKNOWN"


def test_run_l3_006_structural_all_var_attr():
    """评审修正 A7 回归门:结构级 all 把行 dict 以 var 名并入 env 后求 cond;_tpl 走 _resolve(var-attr)+money 格式。"""
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L3-006"]
    fields = {"bid.total_price": 1000001.0, "bid.amount_occurrences": [{"where": "承诺函", "value": 900000.0}]}
    issues = run_det_rule(rule, fields)
    assert issues and issues[0]["verdict"] == "FAIL"
    assert "900,000.00" in issues[0]["message"] and "承诺函" in issues[0]["message"]
    assert not re.search(r"\{[\w.]+(?::\w+)?\}", issues[0]["message"]), f"残留占位符: {issues[0]['message']}"
    ok = {**fields, "bid.amount_occurrences": [{"where": "承诺函", "value": 1000001.0}]}
    assert run_det_rule(rule, ok) == []
    assert run_det_rule(rule, {"bid.total_price": 1.0})[0]["verdict"] == "UNKNOWN"


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


# 设计文档 §6.3 v1 落地清单(32 条):L1 det 13(021 声明函 W11 迁 L2-031,2026-11-07)+ L1 sem 1(L1-013)+ L1 hyb 2(003/007);L3 det 13 + L3 hyb 2(004/008);L2 det 1(L2-031)
# 追加登记:批二续文件级 L2-001/002/003;批六T5 +5 L1-017/L2-012/013/014/040(T3 落包,V1 代登记面 40 条,A-β6-④)
# 批七T2 +4 L1-004/L1-020/L1-022/L1-026(§6.1 ❌4 消费规则入包,V1 代登记面 44 条,A-β7-①②)
EXPECTED_V1_IDS = {
    "L1-001",
    "L1-002",
    "L1-003",
    "L1-004",
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
    "L1-017",
    "L1-019",
    "L1-020",
    "L1-022",
    "L1-026",
    "L2-001",
    "L2-002",
    "L2-003",
    "L2-012",
    "L2-013",
    "L2-014",
    "L2-031",
    "L2-040",
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


def test_text_typed_duration_fields_need_human_not_crash():
    """fix-round 评审项回归门:normalize_unit 目标字段(工期/质保)以原始文本回流时,
    run_det_rule 必须落 need_human 而非抛 ValueError(expr._normalize_unit 强转失败
    → KeyError,复用 on_missing_input=need_human 既有通路);L1-014/L1-015(Task 18
    新增)与 L3-005(M1 既有,先例已漏过一次)同规。"""
    pack = load_rulepack(PACK)
    rules = {r.id: r for r in pack.rules}
    cases = [
        ("L1-014", {"bid.duration_main_text": "540日历天", "tender.max_duration": 600}),
        ("L1-015", {"bid.warranty_period": "24个月", "tender.min_warranty_period": 12}),
        ("L3-005", {"bid.duration_main_text": "540日历天", "bid.duration_schedule": {"value": 540, "unit": "day"}, "bid.duration_commitment_letter": {"value": 540, "unit": "day"}}),
    ]
    for rid, fields in cases:
        issues = run_det_rule(rules[rid], fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "UNKNOWN" and issues[0]["need_human"] is True, f"{rid} 文本型工期/质保字段应 UNKNOWN(need_human 旗),得 {issues}"


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
    assert len(by_type.get("deterministic", [])) == 51, (
        "L1 15 + L2 21 + L3 15 = 51(批九T1 +1:L2-052 年份连续性,A-β9-①;前值 50=批七T2 +1:L1-026;前值 49=批六T3 +5 要件级;前前值 44=批二续T3 +3)"
    )
    assert len(by_type.get("hybrid", [])) == 7, "L1 hyb 003/007/004(批七T2)/022(批七T2) + L3 hyb 004/008 + L2-023 指纹通道 = 7(批七T2 +2:L1-004/L1-022,A-β7-②;前值 5=整合版对齐 W1)"
    assert len(by_type.get("semantic", [])) == 2, "L1-013 + L1-020(批七T2 +1,A-β7-②);前值 L1-013 唯一 sem 规则"
    for r in pack.rules:
        if r.type == "hybrid":
            # L2-023 为 op 型粗筛(att_missing_rows,spec 2026-11-04 §2.3 门=det_expr 或 op),
            # 例外放行;其余 hyb 仍须带 det_expr。
            if not (r.check.get("det_expr") or r.check.get("op")):
                raise AssertionError(f"{r.id} hybrid 缺 det_expr/op(粗筛永不触发)")
            if r.check.get("det_expr"):
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
        assert issues[0]["verdict"] == "UNKNOWN" and issues[0]["need_human"] is True, f"{rule.id} 空 fields 应 UNKNOWN(need_human 旗)"
        assert issues[0]["rule_id"] == rule.id and issues[0]["source"] == "engine"


def test_l3019_missing_amount_key_degrades_to_need_human():
    """1.0.0.yaml L3-019 注释对存量线程的承诺钉测:行缺 amount 键(旧线程存量字段)
    → KeyError → 整规则 need_human 诚实降级,禁 TypeError 逃逸/误报 violation。"""
    pack = load_rulepack(PACK)
    rule = next(r for r in pack.rules if r.id == "L3-019")
    issues = run_det_rule(rule, {"bid.boq_rows": [{"id": "R1", "qty": 3, "price": 100}]})
    assert len(issues) == 1 and issues[0]["verdict"] == "UNKNOWN" and issues[0]["need_human"] is True
    assert "r.amount" in issues[0]["message"]  # 缺键点名(求值期字段缺失 'r.amount')


def test_attach_evidence_from_provenance():
    """EAI-CUSTOM 2026-10-30(spec D7/D9):provenance ∩ rule.inputs 回填 evidence;
    dedup_key 不含证据(旧问题不因补证据重发);无 provenance 维持 []。"""
    from app.extensions.bid_review.engine.rule_runner import Rule, attach_evidence, run_det_rule

    rule = Rule(
        id="L1-009",
        name="总价不超限价",
        layer="L1",
        type="deterministic",
        applies_to=["*"],
        inputs=["bid.total_price", "tender.max_price"],
        check={"op": "lte", "left": "bid.total_price", "right": "tender.max_price"},
        severity="fatal",
        evidence=[],
        message_tpl="超限价",
        fix_tpl="",
        confidence_gate=1.0,
        enabled=True,
    )
    issues = run_det_rule(rule, {"bid.total_price": 100.0, "tender.max_price": 90.0})
    assert issues and issues[0]["evidence"] == []  # det 本体不带证据

    prov = {"bid.total_price": {"doc_id": "bid.docx", "page": 3, "quote": "总价100万"}, "tender.max_price": {"doc_id": "t.pdf", "page": None, "quote": "限价90万"}, "bid.subtotal": {"doc_id": "x", "page": 1, "quote": "非本规则输入不收"}}
    out = attach_evidence(issues, rule, prov)
    ev = out[0]["evidence"]
    assert [e["section_path"] for e in ev] == ["bid.total_price", "tender.max_price"]  # 只收 inputs 交集
    assert ev[0] == {"doc_id": "bid.docx", "page": 3, "section_path": "bid.total_price", "text": "总价100万"}
    assert ev[1]["page"] is None  # docx 无页码诚实 null
    assert attach_evidence(issues, rule, None) is issues and issues[0]["evidence"]  # 原地回填,空 provenance 不动


# ── L2 P1:att_check / att_count 专用分支(spec 2026-11-02 §3,镜像 set_eq 先例) ──

ATT_REQS = [
    {"no": "A-1", "name": "投标函", "mandatory": "★", "min_count": None},
    {"no": "A-2", "name": "业绩证明", "mandatory": "★", "min_count": 3},
    {"no": "", "name": "不出席也行", "mandatory": "建议", "min_count": None},
]
ATT_PROV = [
    {"no": "A-1", "name": "投标函", "page": 2},
    {"no": "A-2", "name": "业绩证明", "page": 118},
    {"no": "A-2", "name": "业绩证明", "page": 121},
    {"no": "", "name": "企业宣传册", "page": 310},
]
ATT_FIELDS = {"tender.attachment_requirements": ATT_REQS, "bid.attachment_index": ATT_PROV}


def _att_rule(op, rid=None):
    return Rule(
        id=rid or ("L2-020" if op == "att_check" else "L2-024"),
        name="附件",
        layer="L2",
        type="deterministic",
        applies_to=["*"],
        inputs=["tender.attachment_requirements", "bid.attachment_index"],
        check={"op": op, "left": "tender.attachment_requirements", "right": "bid.attachment_index"},
        severity="fatal" if op == "att_check" else "major",
        evidence=[],
        message_tpl="附件问题:{missing}{insufficient}",
        fix_tpl=None,
        confidence_gate=0.0,
        enabled=True,
    )


def test_att_check_reports_missing_only():
    """att_check 只列 MISSING req(编号+名称);PARTIAL/MATCHED 不进 message。"""
    issues = run_det_rule(_att_rule("att_check"), ATT_FIELDS)
    assert len(issues) == 1
    assert issues[0]["verdict"] == "FAIL"
    assert "不出席也行" in issues[0]["message"]
    assert "业绩证明" not in issues[0]["message"]  # PARTIAL 不进 att_check


def test_att_check_all_matched_no_issue():
    fields = {
        "tender.attachment_requirements": [{"no": "A-1", "name": "投标函"}],
        "bid.attachment_index": [{"no": "A-1", "name": "投标函", "page": 2}],
    }
    assert run_det_rule(_att_rule("att_check"), fields) == []


def test_att_count_reports_partial_only():
    issues = run_det_rule(_att_rule("att_count"), ATT_FIELDS)
    assert len(issues) == 1
    assert "业绩证明" in issues[0]["message"]
    assert "3" in issues[0]["message"] and "2" in issues[0]["message"]  # 要求3份/提供2份


def test_att_ops_missing_field_need_human():
    """字段缺失 → need_human(既有链路,run_det_rule 层直验)。"""
    issues = run_det_rule(_att_rule("att_check"), {})
    assert len(issues) == 1 and issues[0]["need_human"] is True


def test_att_ops_whitelisted_at_load():
    """载入期白名单放行 att_check/att_count/att_missing_rows;L2 层三 att 规则(L2-020/024 det
    + L2-023 hyb 指纹通道,spec 2026-11-04)可加载;R2+ 2026-11-05 增 L2-022/041(op:all 逐行);
    整合版对齐 W5 层归位 2026-11-06 增 L2-015(op:all);W11 层归位 2026-11-07 增 L2-031(op:all,自 L1-021);
    P1-β批二 2026-11-07 增 L2-021(op:all,col 取列,W9 主责);
    P1-β批二续 2026-11-07 增 L2-001/002/003(steps subset_of×2 + gte 册数下限,steps 形态无 op 键=None);
    P1-β批二续 T2 2026-11-07 增 L2-004/050(op:all 逐行完好性)+ L2-051(op:eq regex 草稿残留);
    P1-β批二续 T3 2026-11-07 增 L2-030(op:all col 取签署位列)+ L2-032(steps 两件套存在性,None)
    + L2-033(op:eq 凭证存在性,C-17);
    P1-β批六 T3 2026-11-08 增 L2-012/013/014/040(op:all contains_any+keywords 惯用式,A-β6-⑦);
    P1-β批九 T2 2026-11-08 增 L2-052(op:att_year_span 年份连续性,A-β9-①②)。"""
    pack = load_rulepack(PACK)
    ops = {r.id: r.check.get("op") for r in pack.rules if r.layer == "L2"}
    assert ops == {
        "L2-001": None,
        "L2-002": "gte",
        "L2-003": None,
        "L2-004": "all",
        "L2-050": "all",
        "L2-051": "eq",
        "L2-015": "all",
        "L2-020": "att_check",
        "L2-021": "all",
        "L2-024": "att_count",
        "L2-023": "att_missing_rows",
        "L2-030": "all",
        "L2-032": None,
        "L2-033": "eq",
        "L2-041": "all",
        "L2-022": "all",
        "L2-031": "all",
        "L2-012": "all",
        "L2-013": "all",
        "L2-014": "all",
        "L2-040": "all",
        "L2-052": "att_year_span",
    }


def test_l2032_steps_any_false_violation_all_true_pass():
    """P1-β批二续 T3(A-续-②):L2-032 两件套存在性 steps——任一 False → violation(major),
    全 True → PASS 零发声;单边缺失字段 → need_human(on_missing_input 既有通路)。"""
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L2-032"]
    bad = run_det_rule(rule, {"bid.legal_id_proof_present": True, "bid.id_copy_present": False})
    assert len(bad) == 1 and bad[0]["verdict"] == "FAIL" and bad[0]["severity"] == "major"
    ok = run_det_rule(rule, {"bid.legal_id_proof_present": True, "bid.id_copy_present": True})
    assert ok == [], "两件齐备 → PASS 零发声"
    nh = run_det_rule(rule, {"bid.legal_id_proof_present": True})
    assert len(nh) == 1 and nh[0]["verdict"] == "UNKNOWN"


# ── L2 P2:UNKNOWN→need_human + 实体键(spec 2026-11-02 §7 挂账行) ──

COMP_REQS = [
    {"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "资质证书"}]},
]
COMP_FIELDS = {
    "tender.attachment_requirements": COMP_REQS,
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 40},  # 引用父号,归属不了 → 分组失败
    ],
}
COMP2_REQS = [
    {"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "资质证书"}]},
    {"no": "4", "name": "技术文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "4.1", "name": "安全生产许可证"}, {"no": "4.2", "name": "业绩合同"}]},
]
COMP2_FIELDS = {
    "tender.attachment_requirements": COMP2_REQS,
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 40},  # 引用父号 3,归属不了 → "3" 分组失败
        {"no": "4-9", "name": "验收报告", "page": 55},  # 引用父号 4,归属不了 → "4" 分组失败
    ],
}


def test_att_check_unknown_degrades_need_human():
    """分组失败 → 父行产 need_human(禁强行 PARTIAL/MISSING);不进 missing 列表。"""
    issues = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "UNKNOWN"
    assert "资格审查文件" in issues[0]["message"]


def test_att_issues_carry_entity_keys():
    """att issue 携带实体键 attachment:{no};无 no 用 name 通道。"""
    issues = run_det_rule(_att_rule("att_check"), ATT_FIELDS)
    assert issues[0]["entity_keys"] == ["attachment:name:不出席也行"]  # 只 MISSING 的是无编号件(A-2 是 PARTIAL 不进 att_check)
    nh = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert nh[0]["entity_keys"] == ["attachment:3"]


def test_att_issue_entity_keys_default_empty():
    """非 att 算子 issue 也带 entity_keys=[](形状统一,worker 透传零分支)。"""
    from app.extensions.bid_review.engine.rule_runner import _issue

    iss = _issue(_att_rule("att_check"), {}, {"missing": ["x"]})
    assert iss["entity_keys"] == []


def test_att_unknown_issues_unique_dedup_keys():
    """两个复合件同时分组失败 → 各自 need_human 的 dedup_key 按实体键派生(审查 I-1):
    彼此 distinct 且各含实体键——同附件跨重跑仍归并,异附件不再互吞。"""
    issues = run_det_rule(_att_rule("att_check"), COMP2_FIELDS)
    assert len(issues) == 2
    keys = {i["dedup_key"] for i in issues}
    assert keys == {"L2-020|-|attachment:3", "L2-020|-|attachment:4"}


def test_att_count_ignores_unknown():
    """att_count 对 UNKNOWN 行零 issue(审查 M-1):UNKNOWN 归 att_check 的 need_human 通道,钳位分工。"""
    assert run_det_rule(_att_rule("att_count"), COMP_FIELDS) == []


# ── L2 P3:UNKNOWN 成因分流措辞(spec 2026-11-03 §3.4) ──────────────────

NEAR_FIELDS = {
    "tender.attachment_requirements": [{"no": "E-2", "name": "中标通知书", "mandatory": "★", "min_count": None}],
    "bid.attachment_index": [{"no": "", "name": "中标通知书回执", "page": 40}],
}


def test_att_check_near_miss_message_mentions_candidate():
    """near_miss UNKNOWN → need_human,措辞带近似候选;entity/dedup 沿用实体键(I-1)。"""
    issues = run_det_rule(_att_rule("att_check"), NEAR_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "UNKNOWN"
    assert "近似候选" in issues[0]["message"]
    assert "中标通知书回执" in issues[0]["message"]
    assert "0.83" in issues[0]["message"]  # .2f 渲染钉(fixture ratio≈0.8333 确定性)
    assert issues[0]["entity_keys"] == ["attachment:E-2"]
    assert issues[0]["dedup_key"] == "L2-020|-|attachment:E-2"


def test_att_check_grouping_wording_unchanged():
    """回归面:分组失败措辞不变(golden L2-020-unknown-group-failure contains 依赖)。"""
    issues = run_det_rule(_att_rule("att_check"), COMP_FIELDS)
    assert issues[0]["need_human"] is True
    assert "无法自动分组" in issues[0]["message"]


# ── L2 P3.2:复合子行 near-miss 分流(spec 2026-11-03 §2) ──────────────────

SUB_NEAR_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "", "name": "中标通知书回执", "page": 40},  # 不引用父号,留池;sim≈0.83≥0.75
    ],
}

SUB_NEAR_ORPHAN_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 39},  # 引用父号,归属不了 → 孤儿
        {"no": "X-7", "name": "中标通知书回执", "page": 40},
    ],
}


def test_att_check_sub_near_miss_message_names_subitem():
    """P3.2:子行 near_miss → need_human 点名父件+子件+候选;dedup 按子行实体键
    (I-1 同规);不得走 grouping 话术,不得渲染「无近似候选记录」(候选在场)。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_NEAR_FIELDS)
    assert len(issues) == 1
    assert issues[0]["need_human"] is True
    assert issues[0]["verdict"] == "UNKNOWN"
    assert "子件" in issues[0]["message"]
    assert "3.2" in issues[0]["message"]
    assert "中标通知书" in issues[0]["message"]
    assert "近似候选" in issues[0]["message"]
    assert "0.83" in issues[0]["message"]  # .2f 渲染钉(fixture ratio≈0.8333 确定性)
    assert "无法自动分组" not in issues[0]["message"]
    assert "无近似候选记录" not in issues[0]["message"]
    assert issues[0]["entity_keys"] == ["attachment:3.2"]
    assert issues[0]["dedup_key"] == "L2-020|-|attachment:3.2"


def test_att_check_orphan_and_sub_near_miss_both_messages():
    """孤儿+子近似并存:子近似消息+grouping 消息各自成话,dedup 键互异不互吞。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_NEAR_ORPHAN_FIELDS)
    assert len(issues) == 2
    assert {i["dedup_key"] for i in issues} == {"L2-020|-|attachment:3.2", "L2-020|-|attachment:3"}
    assert any("近似候选" in i["message"] for i in issues)
    assert any("无法自动分组" in i["message"] for i in issues)
    assert all(i["need_human"] is True for i in issues)
    sub_msg = next(i for i in issues if "近似候选" in i["message"])
    assert sub_msg["dedup_key"] == "L2-020|-|attachment:3.2"
    grp_msg = next(i for i in issues if "无法自动分组" in i["message"])
    assert grp_msg["dedup_key"] == "L2-020|-|attachment:3"


# ── L2-023 指纹通道:att_missing_rows 粗筛(spec 2026-11-04 §2.1) ──────────────────

FP_MISS_FIELDS = {
    "tender.attachment_requirements": [
        {"no": "5", "name": "安全生产许可证", "mandatory": "★", "min_count": None},
        {"no": "6", "name": "社保缴纳证明", "mandatory": "★", "min_count": None},
    ],
    "bid.attachment_index": [{"no": "", "name": "业绩合同", "page": 9}],
}


def _fp_rule(**check_extra):
    check = {"op": "att_missing_rows", "left": "tender.attachment_requirements", "right": "bid.attachment_index", **check_extra}
    return Rule(
        id="L2-023",
        name="附件类型指纹核对",
        layer="L2",
        type="hybrid",
        applies_to=["*"],
        inputs=["tender.attachment_requirements", "bid.attachment_index"],
        check=check,
        severity="major",
        evidence=[],
        message_tpl="附件「{clause_id}」疑似以其它名称提供(类型指纹命中):{reason}",
        fix_tpl=None,
        confidence_gate=0.75,
        enabled=True,
    )


def test_att_missing_rows_per_row_candidates():
    """L2-023 粗筛(spec 2026-11-04 §2.1):MISSING 行逐行 violation 候选,candidate_tpl
    渲染候选消息(message_tpl 是 sem 侧 {clause_id} 契约,两相分离),entity/dedup 按行实体键。"""
    issues = run_det_rule(_fp_rule(candidate_tpl="附件「{missing}」未见于投标提供清单"), FP_MISS_FIELDS)
    assert len(issues) == 2
    assert all(i["verdict"] == "FAIL" for i in issues)
    assert "安全生产许可证" in issues[0]["message"]
    assert "社保缴纳证明" in issues[1]["message"]
    assert "{" not in issues[0]["message"]  # 无占位残留
    assert issues[0]["entity_keys"] == ["attachment:5"]
    assert issues[1]["entity_keys"] == ["attachment:6"]
    assert issues[0]["dedup_key"] != issues[1]["dedup_key"]


def test_att_missing_rows_no_tpl_falls_back():
    """无 candidate_tpl → 默认候选消息,同样逐行。"""
    issues = run_det_rule(_fp_rule(), FP_MISS_FIELDS)
    assert len(issues) == 2
    assert "安全生产许可证" in issues[0]["message"]
    assert "{" not in issues[0]["message"]


def test_att_missing_rows_unknown_rows_silent():
    """UNKNOWN 行零发声(spec §2.1):近似行已有 L2-020 need_human 面,双规则重复=噪音。"""
    assert run_det_rule(_fp_rule(), SUB_NEAR_FIELDS) == []


def test_att_missing_rows_whitelisted_at_load(tmp_path):
    """算子入白名单:含 candidate_tpl 的规则包可载入(load_rulepack 不拒)。"""
    good = tmp_path / "good.yaml"
    good.write_text(
        "rules:\n- id: L2-023\n  name: 指纹\n  layer: L2\n  type: hybrid\n  severity: major\n"
        "  applies_to: ['*']\n  inputs: [tender.attachment_requirements, bid.attachment_index]\n  check: {op: att_missing_rows, left: tender.attachment_requirements, right: bid.attachment_index, candidate_tpl: \"附件「{missing}」x\"}\n"
        "  evidence: []\n  message_tpl: m\n  fix_tpl: f\n  confidence_gate: 1.0\n  enabled: true\n",
        encoding="utf-8",
    )
    assert load_rulepack(str(good)).rules[0].id == "L2-023"


# ── L2 混合态:子近似+子真缺失 issue 面枚举(spec 2026-11-03 §4) ──────────────────

SUB_MIXED_FIELDS = {
    "tender.attachment_requirements": [{"no": "3", "name": "资格审查文件", "mandatory": "★", "min_count": None, "sub_items": [{"no": "3.1", "name": "营业执照"}, {"no": "3.2", "name": "中标通知书"}, {"no": "3.3", "name": "完税证明"}]}],
    "bid.attachment_index": [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "", "name": "中标通知书回执", "page": 40},  # 3.2 近似(sim≈0.83≥门)
        # 3.3 完税证明:池内零近似 → 真缺失
    ],
}


def test_att_check_mixed_parent_missing_subs_enumerated():
    """L2 混合态(spec 2026-11-03 §1):混合父行(子近似+子真缺失)——近似子件候选话术
    不变,真缺失子件逐个独立 need_human 点名父件+子件;dedup 按子行实体键互异。
    纯 near_miss 父行不多发已由 test_att_check_sub_near_miss_message_names_subitem
    len==1 钉住(spec §4)。"""
    issues = run_det_rule(_att_rule("att_check"), SUB_MIXED_FIELDS)
    assert len(issues) == 2
    near = next(i for i in issues if "近似候选" in i["message"])
    assert near["dedup_key"] == "L2-020|-|attachment:3.2"
    miss = next(i for i in issues if "缺失" in i["message"])
    assert miss["need_human"] is True
    assert "资格审查文件" in miss["message"]
    assert "3.3" in miss["message"]
    assert "完税证明" in miss["message"]
    assert miss["entity_keys"] == ["attachment:3.3"]
    assert miss["dedup_key"] == "L2-020|-|attachment:3.3"


def test_dedup_key_canonical_and_bounded():
    """T4 质量轮(I-1/I-2,2026-11-07):_dedup_key canonical json 序列化(sort_keys)
    保同内容不同键序跨 run 同键;超 200 字符实体截断接 ``#``+md5 前 12 位有界化——
    models.dedup_key String(256) 硬限,PG 不截断、超长 DataError 断整 run 持久化;
    总长 ≈224 < 256(给 llm_runner "|confirm-failed" 组合留头寸)。"""
    from app.extensions.bid_review.engine.rule_runner import Rule, _dedup_key

    rule = Rule(id="L2-021", name="t", layer="L2", type="deterministic", applies_to=["*"], inputs=[], check={}, severity="major", evidence=[], message_tpl="", fix_tpl="", confidence_gate=1.0, enabled=True)
    wide = {"r": {"name": "附" * 300, "no": "附件一"}}
    key = _dedup_key(rule, wide)
    assert len(key) < 256 and "#" in key, "超宽实体截断+md5 后缀,总长有界 <256"
    assert _dedup_key(rule, {"r": {"no": "附件一", "name": "附" * 300}}) == key, "同内容不同键序 → 同键(canonical sort_keys 证)"
    assert _dedup_key(rule, None).endswith("|-"), "无 env 用 '-' 占位"


# ── P1-β批六 T3:五条新 det 规则直跑(A-β6-⑥⑦;L1-017 and-form=引擎 chk['all'] 表达式
# 列表实态(plan 拟 left/right 双键非 and 分支形态,缺 all 键→KeyError→need_human,按实态落);
# L2-012/013/014/040 contains_any(col(...)+keywords 惯用式,A-β6-⑦:list hay 走 str() repr 串搜子串) ──


class TestBeta6DetRules(unittest.TestCase):
    """批六五条 det 规则(A-β6-⑥⑦):L1-017/L2-012/L2-013/L2-014/L2-040。
    直跑形态沿文件惯例:load_rulepack(PACK) → id 索引 → run_det_rule。"""

    def _run(self, rule_id, fields):
        pack = load_rulepack(PACK)
        rule = {r.id: r for r in pack.rules}[rule_id]
        return run_det_rule(rule, fields)

    def test_l1017_consortium_precondition_skip(self):
        # 非联合体:SKIP(precondition 不成立→[])A-β6-⑥
        assert self._run("L1-017", {"bid.is_consortium": False, "tender.consortium_allowed": True, "bid.consortium": []}) == []

    def test_l1017_not_allowed_or_no_agreement_fails(self):
        iss = self._run("L1-017", {"bid.is_consortium": True, "tender.consortium_allowed": False, "bid.consortium": [{"lead": "甲", "members": ["乙"]}]})
        assert len(iss) == 1 and iss[0]["verdict"] == "FAIL"
        iss2 = self._run("L1-017", {"bid.is_consortium": True, "tender.consortium_allowed": True, "bid.consortium": []})
        assert len(iss2) == 1 and iss2[0]["verdict"] == "FAIL"

    def test_l2012_missing_required_section_per_row(self):
        fields = {"tender.tech_sections_required": ["总体方案", "应急预案"], "bid.section_tree": [{"code": "1", "title": "第一章 总体方案", "is_empty": False}]}
        iss = self._run("L2-012", fields)
        assert len(iss) == 1 and "应急预案" in iss[0]["message"]  # per-row(A-β6-⑦)

    def test_l2013_commitment_subset(self):
        fields = {"tender.commitment_sections": ["质量承诺"], "bid.section_tree": []}
        iss = self._run("L2-013", fields)
        assert len(iss) == 1 and "质量承诺" in iss[0]["message"]

    def test_l2014_figures_minor(self):
        fields = {"tender.required_figures": [{"id": "F1", "name": "总平面图"}], "bid.figures": []}
        iss = self._run("L2-014", fields)
        assert len(iss) == 1 and iss[0]["severity"] == "minor"

    def test_l2040_tables_fatal(self):
        fields = {"tender.required_tables": ["报价汇总表"], "bid.tables": [{"name": "分项报价表", "source": "d1"}]}
        iss = self._run("L2-040", fields)
        assert len(iss) == 1 and iss[0]["severity"] == "fatal"

    def test_l2040_present_table_passes(self):
        fields = {"tender.required_tables": ["报价汇总表"], "bid.tables": [{"name": "第一章 报价汇总表", "source": "d1"}]}
        assert self._run("L2-040", fields) == []  # contains_any repr 子串命中(A-β6-⑦)


# ── P1-β批六 T4:⚠️2 兑付(A-β6-⑧)——L1-003 inputs 富化(det 冻结)/ L1-006 forms step ──
# 实态裁决(plan 草拟「check=dict 列表+per-step message_tpl」不可达,已声明):steps 分支实态
# =step 为 expr 串、任一失败单发 rule 级 message_tpl,无 per-step message 键;且缺字段门
# (fields_used 首段+inputs 二段)先于任何 precondition 咬新路径——「夹具无新字段行为不变」
# yaml-only 不可达。按 A-β6-⑧ 回退授权落 steps dict 形态 {expr, precondition, optional,
# message_tpl, fix_tpl, dedup_ent}:引擎 run_det_rule/_collect_exprs 增量支持,legacy 字符串
# steps 单 issue 语义逐字节保留(L1-008/L2-032 既有钉测为证)。set_eq op 对 str 列表实态=
# 裸 set 差集无 norm,forms 判定改用 subset_of×2(expr 版集合等价,元素 strip 归一)。
# plan 三测试扩为七:补金额消息逐字冻结钉/前置门语义不变钉/空数组前置门钉/双 step 独立消息钉
# (各守 A-β6-⑧ 一条硬线)。


class TestBeta6RuleExtensions(unittest.TestCase):
    """批六 ⚠️2 兑付(A-β6-⑧):L1-003 inputs 富化 / L1-006 forms step 独立消息。
    直跑形态沿文件惯例:load_rulepack(PACK) → id 索引 → run_det_rule。"""

    def _run(self, rule_id, fields):
        pack = load_rulepack(PACK)
        rule = {r.id: r for r in pack.rules}[rule_id]
        return run_det_rule(rule, fields)

    def test_l1003_inputs_enriched_unchanged_det(self):
        pack = load_rulepack(PACK)
        r = {x.id: x for x in pack.rules}["L1-003"]
        assert "tender.min_performance_amount" in r.inputs
        assert "tender.performance_window_months" in r.inputs
        # det_expr/message_tpl/fix_tpl 逐字冻结(A-β6-⑧ golden contains 面)
        assert r.check["det_expr"] == "count(bid.similar_performances) >= tender.min_similar_performance_count"
        assert r.message_tpl == "类似业绩 {bid.similar_performances} 数量少于招标要求 {tender.min_similar_performance_count} 项"
        assert r.fix_tpl == "补附满足数量与年限要求的类似业绩证明(中标通知书/合同/验收证明)"

    def test_l1006_forms_step_fires_on_mismatch(self):
        fields = {
            "bid.deposit_amount": 100000,
            "tender.deposit_required": 100000,
            "bid.deposit_receipt_present": True,
            "tender.deposit_forms": ["银行保函"],
            "bid.deposit_forms": ["现金"],
        }
        iss = self._run("L1-006", fields)
        assert len(iss) == 1 and iss[0]["verdict"] == "FAIL"
        assert "银行保函" in iss[0]["message"] and "现金" in iss[0]["message"]
        assert "缴纳形式" in iss[0]["message"]  # forms 独立消息,非金额消息(禁合并回单消息)
        assert "{" not in iss[0]["message"]  # 无占位残留
        assert iss[0]["severity"] == "fatal" and iss[0]["need_human"] is False

    def test_l1006_forms_step_silent_when_fields_absent(self):
        # 夹具无新字段 → 行为不变(golden 数字锁兼容,A-β6-⑧;optional 声明使缺字段门不咬)
        fields = {"bid.deposit_amount": 100000, "tender.deposit_required": 100000, "bid.deposit_receipt_present": True}
        assert self._run("L1-006", fields) == []  # 金额一致且 forms 前置门未开

    def test_l1006_amount_message_frozen_verbatim(self):
        # 金额判定与既有消息/fix 逐字不动(A-β6-⑧ 冻结令直钉);forms 缺席不伴发 need_human
        fields = {"bid.deposit_amount": 50000, "tender.deposit_required": 100000, "bid.deposit_receipt_present": True}
        iss = self._run("L1-006", fields)
        assert len(iss) == 1 and iss[0]["verdict"] == "FAIL"
        assert iss[0]["message"] == "投标保证金 ¥50,000.00 与招标要求 ¥100,000.00 不一致"
        assert iss[0]["fix"] == "按招标文件载明金额缴纳并附凭证,金额/缴纳凭证一致后重传"
        assert iss[0]["dedup_key"] == "L1|L1-006|-"  # 既有实体键逐字节不动(查重连续性)

    def test_l1006_two_steps_fire_independent_messages(self):
        # 双 step 同败:两条 issue 各带各的消息,dedup 键互异不互吞(crud upsert 按
        # (task_id, dedup_key) 合并,同键第二条消息会被吞——dedup_ent=forms 独立实体键)
        fields = {
            "bid.deposit_amount": 50000,
            "tender.deposit_required": 100000,
            "bid.deposit_receipt_present": True,
            "tender.deposit_forms": ["银行保函"],
            "bid.deposit_forms": ["现金"],
        }
        iss = self._run("L1-006", fields)
        assert len(iss) == 2 and all(i["verdict"] == "FAIL" for i in iss)
        msgs = {i["message"] for i in iss}
        assert "投标保证金 ¥50,000.00 与招标要求 ¥100,000.00 不一致" in msgs
        assert any("缴纳形式" in m and "银行保函" in m and "现金" in m for m in msgs)
        assert len({i["dedup_key"] for i in iss}) == 2

    def test_l1006_precondition_gate_unchanged(self):
        # 免缴(deposit_required=0)/凭证缺失:前置不成立=不适用(op 形态既有语义,steps 化不改)
        assert self._run("L1-006", {"bid.deposit_amount": 100000, "tender.deposit_required": 0, "bid.deposit_receipt_present": True}) == []
        assert self._run("L1-006", {"bid.deposit_amount": 90000, "tender.deposit_required": 100000, "bid.deposit_receipt_present": False}) == []

    def test_l1006_forms_precondition_empty_lists_silent(self):
        # 生产契约「无明示给空数组」:路径在场但空 → count>=1 双侧前置门关门,零发声
        fields = {
            "bid.deposit_amount": 100000,
            "tender.deposit_required": 100000,
            "bid.deposit_receipt_present": True,
            "tender.deposit_forms": [],
            "bid.deposit_forms": [],
        }
        assert self._run("L1-006", fields) == []


# ── P1-β批七 T2:4 条新消费规则(A-β7-①..⑥ 修订版,2026-11-08)——L1-004 项目负责人(hyb 双键,
# A-β7-④ 窄化)/L1-020 分包承诺(sem,L1-013 steps:[] 形态门先例)/L1-022 格式密封(hyb op:and
# 合规式,A-β7-② 裁决;severity major 固定 A-β7-⑥)/L1-026 递交时间(det,L3-014 字符串日期比较
# 先例 A-β7-⑤)。controller 裁决单(2026-11-08)落定形态:
# ① 裁决③ inputs 全部叶平键(容器键 bid.pm/tender.pm_req/tender.subcontract_limit/tender.format_requirements/
#   bid.format 不入 flat 字段,消费死锁)——夹具 10/6/3 叶键全在场非 None(bug-4227:null=不在场陷阱)。
# ② 裁决② L1-022 op:or 违规式 → op:and 合规式(L1-017 先例):任一支失败(份数不等/目录=False/
#   页码=False)→ 候选;null-skip 支(x==null or y==null or x==y)保护招标侧未明示维。
# ③ L1-020 夹具 evidence 非空数组(铁律2,check_schema 第1道),plan 逐字 evidence:[] 等价修正。
# ④ hyb 候选实体 join 键=C1(候选同序枚举 cand_map 契约)。
class TestBeta7Rules:
    """批七:4 条新消费规则(L1-004 hyb/L1-020 sem/L1-022 hyb op:and/L1-026 det)。"""

    def _rule(self, rid):
        pack = load_rulepack(PACK)
        return next(r for r in pack.rules if r.id == rid)

    # ── L1-026 det 三态(plan 逐字)──

    def test_l1_026_late_submission_fails(self):
        rule = self._rule("L1-026")
        fields = {"bid.submit_time": "2026-11-09 09:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1
        assert issues[0]["verdict"] == "FAIL"
        assert "递交" in issues[0]["message"]

    def test_l1_026_in_time_passes(self):
        rule = self._rule("L1-026")
        fields = {"bid.submit_time": "2026-11-08 09:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
        assert run_det_rule(rule, fields) == []

    def test_l1_026_missing_fields_need_human(self):
        rule = self._rule("L1-026")
        issues = run_det_rule(rule, {"bid.submit_time": "2026-11-08 09:00:00"})
        assert issues[0]["verdict"] == "UNKNOWN"

    # ── L1-020 sem 管线(inputs 叶平键裁决③;evidence 非空见区块注③)──

    @pytest.mark.asyncio
    async def test_l1_020_sem_pipeline_runs(self):
        rule = self._rule("L1-020")
        script = '{"verdicts": [{"clause_id": "SC-1", "verdict": "none", "confidence": 0.9, "reason": "承诺含转包表述", "evidence": [{"doc_id": "bid.pdf", "page": 1, "text": "承诺含转包表述"}]}]}'

        class R:
            content = script

        fields = {"tender.subcontract_limit.allowed": False, "tender.subcontract_limit.scope": "主体工程", "bid.service_commitments": [{"item": "分包", "value": "允许转包", "section": "承诺函"}]}
        issues = await run_sem_rule(rule, fields, "", wrap_model_fn(lambda m: R()), "")
        assert any(i["rule_id"] == "L1-020" and i["verdict"] == "FAIL" for i in issues)

    # ── L1-004 hyb 管线(粗筛候选=证书清单非空;inputs 6 叶键全在场非 None,裁决③)──

    @pytest.mark.asyncio
    async def test_l1_004_hyb_pipeline_candidate_confirmed(self):
        rule = self._rule("L1-004")
        script = '{"verdicts": [{"clause_id": "C1", "verdict": "partial", "confidence": 0.9, "reason": "证书类别与招标要求不符", "evidence": [{"doc_id": "bid.pdf", "page": 1, "text": "一级建造师"}]}]}'

        class R:
            content = script

        fields = {
            "bid.pm.certs": ["一级建造师"],
            "bid.pm.social_months": 24,
            "bid.pm.on_other_project": False,
            "tender.pm_req.certs": ["一级建造师"],
            "tender.pm_req.social_months": 12,
            "tender.pm_req.exclusive": True,
        }
        issues = await run_sem_rule(rule, fields, "", wrap_model_fn(lambda m: R()), "")
        assert any(i["rule_id"] == "L1-004" and i["verdict"] == "FAIL" for i in issues)

    # ── L1-004 det 粗筛合规向(F-1,批七T2 review)──
    # 实测勘误(申报):F-1 机制注记「det_expr count>=1 成立→prefilter 过→不进模型」与引擎
    # 实态相反——hyb prefilter 语义=det 命中即候选(op:eq left=count(certs) right=0 → 非空
    # 即命中,plan 逐字「证书清单非空出候选」),命中必进模型确认;「model_fn 零调用」唯一
    # 通路=零命中(certs 空)。双景单测落地:a) certs=[] 零命中 → 零候选零模型调用(F-1 两
    # 断言真形态);b) F-1 原夹具(certs 非空且与招标一致)→ 粗筛命中进模型,scripted full
    # 确认合规 → 驳回候选零 issue 落地(进模型 1 次系设计内粗筛语义,已 pin 防漂移)。

    @pytest.mark.asyncio
    async def test_l1_004_hyb_prefilter_compliant_zero_issue_paths(self):
        rule = self._rule("L1-004")
        full_script = '{"verdicts": [{"clause_id": "C1", "verdict": "full", "confidence": 0.9, "reason": "资格要件合规", "evidence": [{"doc_id": "bid.pdf", "page": 1, "text": "一级建造师"}]}]}'

        class R:
            content = full_script

        calls = 0

        def counting_model(messages):
            nonlocal calls
            calls += 1
            return R()

        base = {
            "bid.pm.social_months": 24,
            "bid.pm.on_other_project": False,
            "tender.pm_req.certs": ["一级建造师"],
            "tender.pm_req.social_months": 12,
            "tender.pm_req.exclusive": True,
        }
        issues = await run_sem_rule(rule, {**base, "bid.pm.certs": []}, "", wrap_model_fn(counting_model), "")
        assert issues == []  # a) 零命中(certs 空,count==0 过 eq 门)→ 零候选零 issue
        assert calls == 0  # a) 零命中 → 不进模型(F-1「model_fn 零调用」真形态)

        issues = await run_sem_rule(rule, {**base, "bid.pm.certs": ["一级建造师"]}, "", wrap_model_fn(counting_model), "")
        assert issues == []  # b) 模型 full 确认合规 → 驳回候选,零 issue 落地
        assert calls == 1  # b) 粗筛命中必进模型恰 1 次(实态勘误见区块注,申报 controller)

    # ── L1-022 hyb 管线 + op:and 合规式三钉(裁决②:a 全合规 0 候选 / b 违规→候选→scripted
    #    判定(上方 async 测) / c null-skip 招标侧未明示 → 0 候选)──

    @pytest.mark.asyncio
    async def test_l1_022_hyb_pipeline_candidate_confirmed(self):
        rule = self._rule("L1-022")
        script = '{"verdicts": [{"clause_id": "C1", "verdict": "partial", "confidence": 0.9, "reason": "份数与招标要求不符", "evidence": [{"doc_id": "bid.pdf", "page": 1, "text": "正本贰份"}]}]}'

        class R:
            content = script

        fields = {
            "tender.format_requirements.copies": 4,
            "tender.format_requirements.toc": True,
            "tender.format_requirements.page_numbering": True,
            "tender.format_requirements.font": "宋体小四",
            "tender.format_requirements.sealing": "密封标识",
            "bid.format.copies": 4,
            "bid.format.toc": False,
            "bid.format.page_numbering": True,
            "bid.format.font": "宋体小四",
            "bid.format.sealing_label": "已密封",
        }
        issues = await run_sem_rule(rule, fields, "", wrap_model_fn(lambda m: R()), "")
        assert any(i["rule_id"] == "L1-022" and i["verdict"] == "FAIL" for i in issues)

    def test_l1_022_and_compliance_direction_pinned(self):
        # op:and 合规式钉测(裁决②):任一支失败→候选;全合规/null-skip→零候选零模型调用。
        rule = self._rule("L1-022")
        compliant = {
            "tender.format_requirements.copies": 4,
            "tender.format_requirements.toc": True,
            "tender.format_requirements.page_numbering": True,
            "tender.format_requirements.font": "宋体小四",
            "tender.format_requirements.sealing": "密封标识",
            "bid.format.copies": 4,
            "bid.format.toc": True,
            "bid.format.page_numbering": True,
            "bid.format.font": "宋体小四",
            "bid.format.sealing_label": "已密封",
        }
        toc_false = {**compliant, "bid.format.toc": False}
        copies_mismatch = {**compliant, "bid.format.copies": 2}
        null_skip = {**compliant, "tender.format_requirements.copies": None}
        assert run_det_rule(rule, compliant) == []  # a) 全合规 → 零候选
        assert len(run_det_rule(rule, toc_false)) == 1  # b) 目录=False → 候选(scripted 判定见 async 测)
        assert len(run_det_rule(rule, copies_mismatch)) == 1  # b') 份数不等 → 候选
        assert run_det_rule(rule, null_skip) == []  # c) 招标侧 copies=null(未明示)+投标有值 → null-skip 零候选

    def test_pack_pins(self):
        pack = load_rulepack(PACK)
        dets = [r for r in pack.rules if r.type == "deterministic"]
        assert len(pack.rules) == 60  # 批九T1 +1 L2-052(前值 59=批七T5)
        assert len(dets) == 51  # 批九T1 +1 L2-052(前值 50=批七T2)


# ── P1-β批七 T3(A-β7-③,2026-11-08):L1-007 inputs 富化(tender.required_signatures 入
# hyb 规则卡)+ 引擎左移(steps dict 项缺 expr → 载入期拒载;原态 load 静默漏收——
# _collect_exprs 对 dict 项只收 expr/precondition,缺 expr 即漏,实评 run_det_rule
# str(st["expr"]) 才 KeyError→伪装「求值期字段缺失」need_human 错位降级)。
# 实态勘误(plan 申报):plan 拟 build_rule_card(rule, fields, "") 直传——函数真实存在
# (llm_runner.build_rule_card),但 rule 入参走 .get 契约(纯 dict),Rule 数据类直传
# AttributeError;真通路=run_sem_rule 入口 dataclasses.asdict 归一后构造卡。测试按实态
# 走 run_sem_rule 抓模型入参卡文案(富化字段经「已算字段」段渲染进卡)。


class TestBeta7L1007Extension:
    """批七 T3:L1-007 签章完整 inputs 富化 + steps dict 缺 expr 左移拒载(A-β7-③)。"""

    def _rule(self, rid):
        pack = load_rulepack(PACK)
        return next(r for r in pack.rules if r.id == rid)

    def test_l1_007_inputs_enriched(self):
        rule = self._rule("L1-007")
        assert "bid.missing_signature_pages" in rule.inputs
        assert "tender.required_signatures" in rule.inputs
        # det/op/message 逐字冻结(A-β7-③:加 input 不加规则,golden contains 面零扰动)
        assert rule.check["det_expr"] == "count(bid.missing_signature_pages) == 0"
        assert rule.message_tpl == "签章缺失页:{bid.missing_signature_pages}"

    @pytest.mark.asyncio
    async def test_l1_007_required_signatures_enriches_prompt(self):
        rule = self._rule("L1-007")
        captured = {}

        def cap_model(messages):
            captured["card"] = messages[0]["content"]

            class R:
                content = '{"verdicts": [{"clause_id": "C1", "verdict": "full", "confidence": 0.9, "reason": "签章合规", "evidence": [{"doc_id": "bid.pdf", "page": 3, "text": "法定代表人签字"}]}]}'

            return R()

        # 粗筛命中(missing 非空)→ 候选进模型;卡「已算字段」段须含富化字段值(法定代表人签字)
        fields = {"bid.missing_signature_pages": ["第3页"], "tender.required_signatures": ["法定代表人签字", "公章"]}
        issues = await run_sem_rule(rule, fields, "", wrap_model_fn(cap_model), "")
        assert "法定代表人签字" in captured["card"]
        assert "tender.required_signatures" in captured["card"]
        assert issues == []  # full=驳回候选,合规落地零 issue

    def test_dict_step_missing_expr_rejected_at_load(self, tmp_path):
        # 批八T1(A-β8-③):_validate_dict_steps 扩面改名 _validate_list_items,steps 缺 expr 门语义/文案逐字不变
        from app.extensions.bid_review.engine.rule_runner import _validate_list_items

        # 直调:校验函数本体按 rid 点名拒载
        with pytest.raises(RulePackError, match="expr"):
            _validate_list_items({"steps": [{"message_tpl": "x"}]}, "T-001")

        # 走 load_rulepack:deepcopy L1-006,dict step 弹掉 expr 键 → 载入期 raise
        raw = yaml.safe_load(Path(PACK).read_text(encoding="utf-8"))
        target = copy.deepcopy(next(r for r in raw["rules"] if r["id"] == "L1-006"))
        next(s for s in target["check"]["steps"] if isinstance(s, dict)).pop("expr")
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.safe_dump({"rules": [target]}, allow_unicode=True), encoding="utf-8")
        with pytest.raises(RulePackError, match="expr"):
            load_rulepack(str(p))


# ── P1-β批八 T1(A-β8-③,2026-11-08):列表项形态门收窄——dict 形态项仅 steps 合法
# (批七 expr 门维持),all/any/values 出现 dict 项载入期拒载:eval 面对三键列表只
# str(e)(rule_runner op:and/op:or,dict 渲染垃圾串),values 更无任何 op 消费——
# 静默放行=校验面谎报覆盖。存量包零触:现包四键全字符串项,载入零噪声。


class TestBeta8ListItemsNarrowing:
    """批八 T1:_collect_exprs dict 分支收窄 + _validate_list_items 载入期拒载(A-β8-③)。"""

    def test_all_list_dict_item_rejected_at_load(self, tmp_path):
        from app.extensions.bid_review.engine.rule_runner import _validate_list_items

        # 直调:文案含列表键名(all)与规则 id
        with pytest.raises(RulePackError) as ei:
            _validate_list_items({"all": ["a == a", {"op": "and", "all": []}]}, "T-002")
        assert "all" in str(ei.value) and "T-002" in str(ei.value)

        # 走 load_rulepack:deepcopy 现包首个 op:and 规则(L3-001 先例),all 列表注入 dict 项 → 载入期 raise
        raw = yaml.safe_load(Path(PACK).read_text(encoding="utf-8"))
        target = copy.deepcopy(next(r for r in raw["rules"] if r["check"].get("op") == "and"))
        assert target["check"]["all"] and all(isinstance(e, str) for e in target["check"]["all"])
        target["check"]["all"] = [*target["check"]["all"], {"injected": True}]
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.safe_dump({"rules": [target]}, allow_unicode=True), encoding="utf-8")
        with pytest.raises(RulePackError) as ei:
            load_rulepack(str(p))
        assert "all" in str(ei.value) and target["id"] in str(ei.value)

    def test_existing_core_pack_loads_zero_noise(self):
        # 真包回归钉:收窄前置态自证——现包 all/any/values 三键全字符串项(零 dict),
        # 新形态门对存量包零扰动(load_rulepack 全量载入不抛)。
        pack = load_rulepack(PACK)
        assert pack.rules, "核心包零规则=载入异常"
        for r in pack.rules:
            for key in ("all", "any", "values"):
                bad = [e for e in (r.check.get(key) or []) if isinstance(e, dict)]
                assert not bad, f"{r.id} {key} 出现 dict 项(收窄门应拒载): {bad}"


# ── P1-β批九 T1:att_year_span 附件年份连续性算子(A-β9-②,2026-11-08;rulepack 零触→五锁钉零扰动,
#    仅算子层直调,镜像 att_count 直调先例:构造 Rule → run_det_rule,不经 load)──


class TestBeta9AttYearSpan:
    """批九 T1:att_year_span 算子分支八钉(A-β9-② 逐条;含勘误② findall 同名多 token 钉,controller 2026-11-08)。"""

    def _rule(self):
        return Rule(
            id="L2-052",
            name="附件年份连续性",
            layer="L2",
            type="deterministic",
            applies_to=["*"],
            inputs=["tender.attachment_requirements", "bid.attachment_index"],
            check={"op": "att_year_span", "left": "tender.attachment_requirements", "right": "bid.attachment_index"},
            severity="major",
            evidence=[],
            message_tpl="附件年份覆盖问题:{span_fail}",
            fix_tpl=None,
            confidence_gate=0.0,
            enabled=True,
        )

    @staticmethod
    def _fields(reqs, prov):
        return {"tender.attachment_requirements": reqs, "bid.attachment_index": prov}

    def test_compliant_span_zero_issue(self):
        # 合规:要求3年,命中行年份 2023/2024/2024/2025 → 去重={2023,2024,2025} 数量足且连续 → 零 issue
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 3}]
        prov = [
            {"no": "A-1", "name": "2023年度审计报告"},
            {"no": "A-1", "name": "2024年度审计报告"},
            {"no": "A-1", "name": "2024年度审计报告(副本)"},
            {"no": "A-1", "name": "2025年1-6月财务报表"},
        ]
        assert run_det_rule(self._rule(), self._fields(reqs, prov)) == []

    def test_span_short_reports_require_vs_cover(self):
        # 不足(PARTIAL 行参与门):min_count=3 提供两份 → PARTIAL;Y={2023,2024} → 「要求3年/覆盖2年」
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 3, "min_count": 3}]
        prov = [
            {"no": "A-1", "name": "2023年度审计报告"},
            {"no": "A-1", "name": "2024年度审计报告"},
        ]
        issues = run_det_rule(self._rule(), self._fields(reqs, prov))
        assert len(issues) == 1 and issues[0]["verdict"] == "FAIL"
        assert "要求3年/覆盖2年" in issues[0]["message"]
        assert issues[0]["entity_keys"] == ["attachment:A-1"]
        assert issues[0]["dedup_key"] == "L2-052|-|attachment:A-1"

    def test_span_gap_reports_discontinuity(self):
        # 断档:要求2年,Y={2022,2024}(份数足但中间缺 2023)→「覆盖年份断档 2022-2024」
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 2}]
        prov = [
            {"no": "A-1", "name": "2022年度审计报告"},
            {"no": "A-1", "name": "2024年度审计报告"},
        ]
        issues = run_det_rule(self._rule(), self._fields(reqs, prov))
        assert len(issues) == 1
        assert "断档" in issues[0]["message"] and "2022-2024" in issues[0]["message"]

    def test_multi_token_name_years_all_collected(self):
        # 勘误②判别钉(controller 2026-11-08):同名多年份 token 全收(findall)——search 只收首 token 会误报「不足」
        reqs = [{"no": "A-1", "name": "近年审计报告", "year_span": 2}]
        prov = [{"no": "A-1", "name": "2023及2025年审计报告"}]
        issues = run_det_rule(self._rule(), self._fields(reqs, prov))
        assert len(issues) == 1
        assert "断档" in issues[0]["message"] and "2023-2025" in issues[0]["message"]

    def test_unparsable_years_degrades_need_human(self):
        # 零解析(③):命中行 name 无 4 位年份 → need_human;带 entity_keys+dedup_key(att UNKNOWN 行同构)
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 3}]
        prov = [{"no": "A-1", "name": "财务报告合集"}]
        issues = run_det_rule(self._rule(), self._fields(reqs, prov))
        assert len(issues) == 1 and issues[0]["need_human"] is True and issues[0]["verdict"] == "UNKNOWN"
        assert "无一可解析年份" in issues[0]["message"]
        assert issues[0]["entity_keys"] == ["attachment:A-1"]
        assert issues[0]["dedup_key"] == "L2-052|-|attachment:A-1"

    def test_null_or_missing_year_span_zero_participation(self):
        # year_span null/缺失 → 零参与零发声(命中行年份可解析也不发声)
        reqs = [
            {"no": "A-1", "name": "近年财务报告", "year_span": None},
            {"no": "A-2", "name": "业绩证明"},
        ]
        prov = [
            {"no": "A-1", "name": "2023年度审计报告"},
            {"no": "A-2", "name": "2020-2021年业绩证明"},
        ]
        assert run_det_rule(self._rule(), self._fields(reqs, prov)) == []

    def test_missing_status_zero_participation(self):
        # MISSING 行零参与(④:L2-020/023 属地,零双报);year_span 合法亦不发声
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 3}]
        assert run_det_rule(self._rule(), self._fields(reqs, [])) == []

    def test_both_causes_single_issue_two_entries(self):
        # ⑥ 两因并存=一条 violation 两条目(不足+断档不互吞):year_span=4,Y={2022,2024}
        reqs = [{"no": "A-1", "name": "近年财务报告", "year_span": 4}]
        prov = [
            {"no": "A-1", "name": "2022年度审计报告"},
            {"no": "A-1", "name": "2024年度审计报告"},
        ]
        issues = run_det_rule(self._rule(), self._fields(reqs, prov))
        assert len(issues) == 1
        assert "要求4年/覆盖2年" in issues[0]["message"] and "断档" in issues[0]["message"]


def test_l1_009_realcase_container_shapes():
    # 批十四(W-real-1,2026-11-11):真实件形态钉——抽取容器键 {value,unit} 与元缀/千分位文本
    # 经 num() 归一后比较;修复前 str<=dict TypeError 逃 KeyError 网 → ERROR。
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-009"]
    base = {"bid.price_includes_tax": True, "tender.price_includes_tax": True}
    within = {**base, "bid.total_price": "225,000元", "tender.max_price": {"value": 230000, "unit": "元"}}
    assert run_det_rule(rule, within) == []
    over = {**base, "bid.total_price": "230,001元", "tender.max_price": {"value": 230000, "unit": "元"}}
    issues = run_det_rule(rule, over)
    assert issues[0]["verdict"] == "FAIL" and issues[0]["severity"] == "fatal"
    bad_container = {**base, "bid.total_price": 1.0, "tender.max_price": {"amount": 5}}
    assert run_det_rule(rule, bad_container)[0]["verdict"] == "UNKNOWN"


def test_l1_012_percent_text_no_false_positive():
    # 批十四(W-real-2,2026-11-11):「6%」文本 vs 6 数值假阳性消失钉;6% vs 7 仍真 FAIL。
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-012"]
    ok = {"bid.tax_rate_occurrences": [{"where": "报价汇总表", "value": "6%"}], "tender.tax_rate": 6}
    assert run_det_rule(rule, ok) == []
    bad = {**ok, "tender.tax_rate": 7}
    issues = run_det_rule(rule, bad)
    assert issues[0]["verdict"] == "FAIL" and "6%" in issues[0]["message"]


def test_l1_011_none_code_clean_render():
    # 批十四(W-real-3,2026-11-11):codes() falsy 过滤——None/缺码行不入 missing/extra 集,
    # message 无「None」/「, 」垃圾(修复前「漏项 ,增项 None」)。
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-011"]
    fields = {
        "tender.boq_items": [{"code": "BM-001"}, {"code": "BM-003"}, {"name": "无码行"}],
        "bid.boq_items": [{"code": "BM-001"}, {"code": None}],
    }
    issues = run_det_rule(rule, fields)
    assert issues and issues[0]["verdict"] == "FAIL"
    msg = issues[0]["message"]
    # tpl 恒含「漏项/增项」字样,只钉 None 垃圾与漏项码;两侧皆空集时 runner 不出 issue
    assert "BM-003" in msg and "None" not in msg
    assert run_det_rule(rule, {k: v for k, v in fields.items()}) is not None
    clean = {
        "tender.boq_items": [{"code": "BM-001"}, {"name": "无码行"}],
        "bid.boq_items": [{"code": "BM-001"}, {"code": None}],
    }
    assert run_det_rule(rule, clean) == []


def test_l1_026_submit_method_dimension():
    # 批十六(A-ADJ-1 方式集维,2026-11-11):dict-step optional 三态——
    # ① 新键双侧缺席=step 零参与(时间维旧行为逐字节保留,批六T4「夹具无新字段行为不变」);
    # ② 方式在允许集合外=FAIL(per-step message_tpl 独立话);
    # ③ 方式在允许集合内=零 issue。
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-026"]
    on_time = {"bid.submit_time": "2026-11-08 16:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
    # ① 缺席零参与:准时+无方式集键 → 零 issue
    assert run_det_rule(rule, dict(on_time)) == []
    # ① 缺席零参与:逾期仍只时间维 FAIL,message 不含方式集话
    late = {"bid.submit_time": "2026-11-08 18:00:00", "tender.bid_deadline": "2026-11-08 17:00:00"}
    issues = run_det_rule(rule, late)
    assert len(issues) == 1 and "递交时间晚于投标截止" in issues[0]["message"]
    # ② 方式在外:准时但方式不在集合 → 1 条方式集 FAIL
    outside = {**on_time, "bid.submit_method": "现场纸质", "tender.allowed_submit_methods": ["电子版上传", "纸质"]}
    issues = run_det_rule(rule, outside)
    assert len(issues) == 1 and issues[0]["verdict"] == "FAIL" and "现场纸质" in issues[0]["message"]
    # ③ 方式在内:准时+方式在集合 → 零 issue
    inside = {**on_time, "bid.submit_method": "纸质", "tender.allowed_submit_methods": ["电子版上传", "纸质"]}
    assert run_det_rule(rule, inside) == []
    # 单侧缺席(allowed 在场 method 缺席)= step 零参与(optional any-absent skip)
    half = {**on_time, "tender.allowed_submit_methods": ["电子版上传"]}
    assert run_det_rule(rule, half) == []


def test_l1_026_covers_null_routes_need_human():
    # 批十六(covers(null) 硬化端到端,2026-11-11):方式集键在场但值 None(直评面,eval_core
    # 剥 None 后活体不可达)→ covers KeyError → run_det_rule KeyError 网 → UNKNOWN(need_human),
    # 修复前为 False → FAIL 错位。
    pack = load_rulepack(PACK)
    rule = {r.id: r for r in pack.rules}["L1-026"]
    fields = {
        "bid.submit_time": "2026-11-08 16:00:00",
        "tender.bid_deadline": "2026-11-08 17:00:00",
        "bid.submit_method": "现场纸质",
        "tender.allowed_submit_methods": None,
    }
    issues = run_det_rule(rule, fields)
    assert issues[0]["verdict"] == "UNKNOWN" and "need_human" in issues[0]["message"]
