"""C-11 src→severity 覆盖(P1-β批一 Task 4;裁决 A-β1-③:rg→fatal 保守侧,合并 issue 取成员行最严档,未知/空 src 不覆盖)。

计划稿五测试 + 红相判别四测试:L2-020(att_check)默认 severity=fatal,与 tender_mandatory/
regulation 覆盖目标同值——仅凭计划稿五测无法显红,故增 internal_template 下行覆盖
(fatal→minor)与 att_count/att_missing_rows(L2-024/L2-023 默认 major)两分支判别面,
令「应覆盖而未覆盖」在实现前必红(TDD),实现后同锁三分支接线。
"""

from app.extensions.bid_review.engine.rule_runner import load_rulepack, run_det_rule

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml"


def _att_rule(op="att_check"):
    pack = load_rulepack(PACK)
    cands = [r for r in pack.rules if r.check.get("op") == op]
    assert len(cands) == 1, f"op={op} 规则应唯一(防未来扩包静默取首): {[r.id for r in cands]}"
    return cands[0]


def _fields(reqs, prov=None):
    # att 三规则真实 inputs=[tender.attachment_requirements, bid.attachment_index]
    # (计划稿的 bid.attachments 非 att 消费面,按真实代码适配,测试语义不变)
    return {"tender.attachment_requirements": reqs, "bid.attachment_index": prov or []}


# ── 计划稿五测试(原文保留;L2-020 默认 fatal 与覆盖目标同值,作行为锁)──


def test_src_tender_mandatory_overrides_to_fatal():
    reqs = [{"no": "A1", "name": "营业执照", "src": "tender_mandatory"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == "fatal"


def test_empty_src_keeps_rule_default():
    reqs = [{"no": "A2", "name": "业绩合同", "src": ""}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == _att_rule().severity  # 缺省不覆盖,golden 存量零回归


def test_unknown_src_keeps_rule_default():
    reqs = [{"no": "A3", "name": "x", "src": "whatever"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == _att_rule().severity


def test_mixed_rows_take_strictest():
    reqs = [{"no": "A4", "name": "a", "src": "internal_template"}, {"no": "A5", "name": "b", "src": "tender_mandatory"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == "fatal"  # 合并 issue 取 max


def test_regulation_maps_fatal_conservative():
    reqs = [{"no": "A6", "name": "x", "src": "regulation"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == "fatal"


# ── 红相判别四测试:覆盖方向与规则默认可区分(实现前必红,实现后同锁三分支)──


def test_src_internal_template_downgrades_att_check_to_minor():
    # L2-020 默认 fatal,internal_template 行须下行覆盖为 minor——「覆盖真的发生了」判别面
    reqs = [{"no": "A7", "name": "模板惯例件", "src": "internal_template"}]
    issues = run_det_rule(_att_rule(), _fields(reqs))
    miss = [i for i in issues if i["verdict"] == "FAIL"]
    assert miss and miss[0]["severity"] == "minor"


def test_att_count_partial_tender_mandatory_overrides_to_fatal():
    # L2-024(att_count PARTIAL)默认 major → tender_mandatory 上行 fatal
    reqs = [{"no": "B1", "name": "银行保函", "min_count": 2, "src": "tender_mandatory"}]
    prov = [{"no": "B1", "name": "银行保函"}]
    issues = run_det_rule(_att_rule("att_count"), _fields(reqs, prov))
    partial = [i for i in issues if i["verdict"] == "FAIL"]
    assert partial and partial[0]["severity"] == "fatal"


def test_att_count_partial_internal_template_overrides_to_minor():
    # L2-024(att_count PARTIAL)默认 major → internal_template 下行 minor
    reqs = [{"no": "B2", "name": "授权委托书模板", "min_count": 2, "src": "internal_template"}]
    prov = [{"no": "B2", "name": "授权委托书模板"}]
    issues = run_det_rule(_att_rule("att_count"), _fields(reqs, prov))
    partial = [i for i in issues if i["verdict"] == "FAIL"]
    assert partial and partial[0]["severity"] == "minor"


def test_att_missing_rows_tender_mandatory_overrides_to_fatal():
    # L2-023(att_missing_rows 候选,单行覆盖)默认 major → tender_mandatory fatal
    reqs = [{"no": "D1", "name": "公证书", "src": "tender_mandatory"}]
    issues = run_det_rule(_att_rule("att_missing_rows"), _fields(reqs))
    cand = [i for i in issues if i["verdict"] == "FAIL"]
    assert cand and cand[0]["severity"] == "fatal"


# ── 抽取契约面:src 枚举入串,既有短语零丢失 ──


def test_extract_contract_declares_src_enum_without_losing_phrases():
    from app.extensions.bid_review.engine import extract as extract_mod

    c = extract_mod.FIELD_TYPE_CONTRACTS["tender.attachment_requirements"]
    assert all(k in c for k in ("src", "tender_mandatory", "tender_required", "regulation", "internal_template", "logical_necessary"))
    # 既有短语零丢失(前车之鉴:Task 2 计划替换串丢过短语)
    assert all(k in c for k in ("no", "name", "clause", "mandatory", "min_count", "year_span", "禁止编造", "无编号填空串", "资格审查条款"))
