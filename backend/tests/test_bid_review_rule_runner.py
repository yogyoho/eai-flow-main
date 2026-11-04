import re
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.expr import validate_expr
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
        assert len(issues) == 1 and issues[0]["verdict"] == "need_human" and issues[0]["need_human"] is True, f"{rid} 文本型工期/质保字段应 need_human,得 {issues}"


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
    assert len(by_type.get("deterministic", [])) == 29, "L1 det 14 + L3 det 13 + L2 det 2(L2-020/024,spec 2026-11-02) = 29"
    assert len(by_type.get("hybrid", [])) == 5, "L1 hyb 003/007 + L3 hyb 004/008 + L2-021 指纹通道(spec 2026-11-04) = 5"
    assert len(by_type.get("semantic", [])) == 1, "L1-013 唯一 sem 规则"
    for r in pack.rules:
        if r.type == "hybrid":
            # L2-021 为 op 型粗筛(att_missing_rows,spec 2026-11-04 §2.3 门=det_expr 或 op),
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
        assert issues[0]["verdict"] == "need_human" and issues[0]["need_human"] is True, f"{rule.id} 空 fields 应 need_human"
        assert issues[0]["rule_id"] == rule.id and issues[0]["source"] == "engine"


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
    assert issues[0]["verdict"] == "violation"
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
    """载入期白名单放行 att_check/att_count/att_missing_rows;L2 层三规则(L2-020/024 det
    + L2-021 hyb 指纹通道,spec 2026-11-04)可加载。"""
    pack = load_rulepack(PACK)
    ops = {r.id: r.check.get("op") for r in pack.rules if r.layer == "L2"}
    assert ops == {"L2-020": "att_check", "L2-024": "att_count", "L2-021": "att_missing_rows"}


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
    assert issues[0]["verdict"] == "need_human"
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
    assert issues[0]["verdict"] == "need_human"
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
    assert issues[0]["verdict"] == "need_human"
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


# ── L2-021 指纹通道:att_missing_rows 粗筛(spec 2026-11-04 §2.1) ──────────────────

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
        id="L2-021",
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
    """L2-021 粗筛(spec 2026-11-04 §2.1):MISSING 行逐行 violation 候选,candidate_tpl
    渲染候选消息(message_tpl 是 sem 侧 {clause_id} 契约,两相分离),entity/dedup 按行实体键。"""
    issues = run_det_rule(_fp_rule(candidate_tpl="附件「{missing}」未见于投标提供清单"), FP_MISS_FIELDS)
    assert len(issues) == 2
    assert all(i["verdict"] == "violation" for i in issues)
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
        "rules:\n- id: L2-021\n  name: 指纹\n  layer: L2\n  type: hybrid\n  severity: major\n"
        "  applies_to: ['*']\n  inputs: [tender.attachment_requirements, bid.attachment_index]\n  check: {op: att_missing_rows, left: tender.attachment_requirements, right: bid.attachment_index, candidate_tpl: \"附件「{missing}」x\"}\n"
        "  evidence: []\n  message_tpl: m\n  fix_tpl: f\n  confidence_gate: 1.0\n  enabled: true\n",
        encoding="utf-8",
    )
    assert load_rulepack(str(good)).rules[0].id == "L2-021"


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
