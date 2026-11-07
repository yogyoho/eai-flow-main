"""共享分派核单测(金标准 spec §4):det/sem 分派、None 剥离、逐规则隔离、进度回调。
金标准尺子量生产同一段代码——本文件锁 eval_core 行为契约。"""

import json
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.rule_runner import load_rulepack

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")


def _quiet_model(responses: dict | None = None):
    """scripted model_fn:按规则卡「规则:<id>」路由;缺省回安静 full 应答(零条目)。"""
    table = responses or {}

    def model(messages):
        card = messages[0]["content"] if isinstance(messages, list) else str(messages)
        for rid, resp in table.items():
            if f"规则:{rid}" in card:
                return resp
        return json.dumps({"verdicts": [{"clause_id": "g", "verdict": "full", "confidence": 1.0, "reason": "quiet", "evidence": [{"doc_id": "g.pdf", "page": 1}]}]}, ensure_ascii=False)

    return model


@pytest.mark.asyncio
async def test_det_violation_and_need_human_dispatch():
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    by_rule = {}
    for i in issues:
        by_rule.setdefault(i["rule_id"], []).append(i)
    assert any(i["verdict"] == "FAIL" and i["severity"] == "fatal" for i in by_rule["L1-009"])
    # L1-005 输入缺失 → UNKNOWN(缺字段约定,旗标 need_human=True)
    assert any(i["verdict"] == "UNKNOWN" for i in by_rule["L1-005"])


@pytest.mark.asyncio
async def test_none_fields_stripped_before_eval():
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": None}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    l9 = [i for i in issues if i["rule_id"] == "L1-009"]
    assert all(i["verdict"] == "UNKNOWN" for i in l9)  # None 字段=缺字段,不判违规


@pytest.mark.asyncio
async def test_rule_crash_isolated_to_need_human(monkeypatch):
    from app.extensions.bid_review.engine import eval_core

    pack = load_rulepack(PACK)

    def boom(rule, fields):
        if rule.id == "L1-009":
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(eval_core, "run_det_rule", boom)
    issues = await evaluate_fields(pack, {}, model_fn=wrap_model_fn(_quiet_model()))
    l9 = [i for i in issues if i["rule_id"] == "L1-009"]
    assert len(l9) == 1 and l9[0]["verdict"] == "ERROR" and "boom" in l9[0]["message"]  # 逐规则隔离降级 ERROR(P1-β批三 五值域)


@pytest.mark.asyncio
async def test_on_progress_reports_each_rule():
    pack = load_rulepack(PACK)
    seen = []

    async def cb(i, total, rule):
        seen.append((i, total, rule.id))

    await evaluate_fields(pack, {}, model_fn=wrap_model_fn(_quiet_model()), on_progress=cb)
    ids = [r for _, _, r in seen]
    assert len(seen) == sum(1 for r in pack.rules if r.enabled)
    assert ids[0] and ids[-1]  # 逐规则推进


# ── 最小 inline 包(F2/F3 专用;test_bid_review_worker_sem.py _TMP_RULEPACK 惯例):
# 产线 34 规则包内容会漂移,sem 分派/进度/disabled 契约用最小包锁定——1 det + 1 sem + 1 disabled。
_EVAL_TMP_RULEPACK = """\
conventions:
  on_missing_input: need_human
rules:
  - id: ED-001
    name: 测试总价不超限价
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.total_price, tender.max_price]
    check:
      op: lte
      left: bid.total_price
      right: tender.max_price
    severity: fatal
    evidence: []
    message_tpl: "投标总价 {bid.total_price:money} 超过最高限价 {tender.max_price:money}"
    fix_tpl: 复核报价汇总
    confidence_gate: 1.0
    enabled: true
  - id: ES-001
    name: 测试实质性条款逐条响应
    layer: L1
    type: semantic
    applies_to: ["*"]
    inputs: [tender.substantive_clauses]
    check:
      per_clause: true
      verdict_set: [full, partial, none, unclear]
      steps: []
    severity: major
    evidence: []
    message_tpl: "实质性条款 {clause_id} 响应为 {verdict}:{reason}"
    fix_tpl: 逐条补实质性响应
    confidence_gate: 0.75
    enabled: true
  - id: EX-001
    name: 禁用规则不得进分派
    layer: L2
    type: semantic
    applies_to: ["*"]
    inputs: [x.anything]
    check:
      per_clause: true
      verdict_set: [full, partial, none, unclear]
      steps: []
    severity: minor
    evidence: []
    message_tpl: "禁用规则 {clause_id}"
    fix_tpl: 无
    confidence_gate: 0.75
    enabled: false
"""

# sem 应答(verdict 须在 check.verdict_set 内;partial→violation 映射见 llm_runner.VERDICT_TO_ISSUE。
# 证据带逐字摘录使 docs_text 位置加载性:错位则七道第2道证据对齐失配翻 need_human 旗,
# 故 F2 以 need_human=False 钉死 docs_text 传参顺序)
_SEM_RESP = json.dumps({"verdicts": [{"clause_id": "c1", "verdict": "partial", "confidence": 0.9, "reason": "响应偏离招标要求", "evidence": [{"doc_id": "d.pdf", "page": 1, "text": "条款c1原文摘录"}]}]}, ensure_ascii=False)
_MATERIALS = "待审材料哨兵 MATERIALS_SENTINEL_T1 独一无二"
_DOCS_TEXT = {"d.pdf": {1: "证据正文哨兵 DOCS_SENTINEL_T1 ★ 条款c1原文摘录"}}


def _mini_pack(tmp_path):
    p = tmp_path / "mini-pack.yaml"
    p.write_text(_EVAL_TMP_RULEPACK, encoding="utf-8")
    return load_rulepack(p)


@pytest.mark.asyncio
async def test_sem_dispatch_partial_maps_to_violation_and_args_ordered(tmp_path):
    """F2:sem 分支真断言(现有产线包测试 sem 全走安静 full,分派错序/传参错位抓不住):
    partial→violation 映射、rule_id 浮出、materials/docs_text 位置传参哨兵、det 分支零模型
    调用、disabled 规则不进分派。"""
    pack = _mini_pack(tmp_path)
    calls: list[str] = []
    cards: list[str] = []
    table = {"ES-001": _SEM_RESP, "EX-001": _SEM_RESP}  # EX-001 若误进分派,partial 应答必浮条目被抓

    def model(messages):
        card = messages[0]["content"]
        cards.append(card)
        rid = next((r for r in table if f"规则:{r} " in card), "?")
        calls.append(rid)
        return table[rid]

    fields = {"bid.total_price": 100.0, "tender.max_price": 200.0, "tender.substantive_clauses": ["条款c1原文摘录"]}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(model), materials=_MATERIALS, docs_text=_DOCS_TEXT)
    assert calls == ["ES-001"], f"仅 sem 规则应调模型(det 干净零调用/disabled 不分派),实际 {calls}"
    assert _MATERIALS in cards[0], "materials 须原样注入规则卡待审材料段(错位即字典 repr)"
    sem = [i for i in issues if i["rule_id"] == "ES-001"]
    assert len(sem) == 1 and sem[0]["verdict"] == "FAIL" and not sem[0]["need_human"], "partial→FAIL;need_human=False 钉死 docs_text 位置(错位则证据对齐失配翻旗)"
    assert sem[0]["severity"] == "major" and sem[0]["clause_id"] == "c1"
    assert all(i["rule_id"] != "EX-001" for i in issues), "disabled 规则不得产出条目"


@pytest.mark.asyncio
async def test_progress_skips_disabled_and_sequence_is_dense(tmp_path):
    """F3:进度契约——enabled=false 规则不出现;序号恰为 1..n 连续无重复;total 恒等于 enabled 数。"""
    pack = _mini_pack(tmp_path)
    seen: list[tuple[int, int, str]] = []

    async def cb(i, total, rule):
        seen.append((i, total, rule.id))

    await evaluate_fields(pack, {}, model_fn=wrap_model_fn(_quiet_model()), on_progress=cb)
    enabled = [r.id for r in pack.rules if r.enabled]
    assert [rid for _, _, rid in seen] == enabled, "disabled 规则不进分派,顺序=包内声明序"
    assert [i for i, _, _ in seen] == list(range(1, len(enabled) + 1)), "序号恰为 1..n 连续无重复"
    assert {t for _, t, _ in seen} == {len(enabled)}, "total 恒等于 enabled 数"


# ── W9 抑制联动(P1-β批二 A-β2-⑦):L2-021 主责下同实体 L3-012 violation 折叠 ──


def _iss(rule_id, entity_keys, verdict="FAIL"):
    return {"rule_id": rule_id, "verdict": verdict, "entity_keys": entity_keys, "message": f"{rule_id} {entity_keys}"}


def test_w9_suppress_folds_same_entity_l3012_only():
    """W9 六断言:①同实体(业绩合同)L3-012 violation 被 L2-021 violation 折叠移除;
    ②异实体(其他文件)L3-012 照常保留;③L3-012 need_human 不动;④无 L2-021 时原样返回;
    ⑤L2-021 自身 need_human 不武装抑制(T4 质量轮 M-3);⑥message 全文禁入匹配面——
    消息含实体名而 entity_keys 不含的 L3-012 violation 不折叠(变异测试钉,M-3)。"""
    from app.extensions.bid_review.engine.eval_core import _suppress_l3012_by_l2021

    issues = [
        _iss("L2-021", ["业绩合同"]),
        _iss("L3-012", ["业绩合同"]),  # 同实体 → 折叠
        _iss("L3-012", ["其他文件"]),  # 异实体 → 保留
        _iss("L3-012", ["业绩合同"], verdict="UNKNOWN"),  # UNKNOWN 不动
    ]
    out = _suppress_l3012_by_l2021(issues)
    assert len(out) == 3, "仅同实体 FAIL 折叠一条,L2-021 本体与其余条目不动"
    l3 = [i for i in out if i["rule_id"] == "L3-012"]
    assert [i["entity_keys"] for i in l3] == [["其他文件"], ["业绩合同"]]  # ①②折叠/保留
    assert l3[1]["verdict"] == "UNKNOWN"  # ③ need_human(UNKNOWN)不动

    no_l2021 = [_iss("L3-012", ["业绩合同"]), _iss("L3-012", ["其他文件"], verdict="UNKNOWN")]
    assert _suppress_l3012_by_l2021(no_l2021) == no_l2021  # ④ 无 L2-021 → 原样返回(零折叠)

    nh_armed = [_iss("L2-021", ["业绩合同"], verdict="UNKNOWN"), _iss("L3-012", ["业绩合同"])]
    assert len(_suppress_l3012_by_l2021(nh_armed)) == 2, "⑤ L2-021 为 UNKNOWN 时武装抑制不启动,同实体 L3-012 FAIL 保留"

    msg_only = {"rule_id": "L3-012", "verdict": "FAIL", "entity_keys": ["无关锚"], "message": "L3-012 消息全文含「业绩合同」样板词"}
    out_msg = _suppress_l3012_by_l2021([_iss("L2-021", ["业绩合同"]), msg_only])
    assert len(out_msg) == 2, "⑥ 匹配面只认 entity_keys 结构化锚,message 全文含实体名不触发折叠"


# ── 主责折叠泛化(A-续-⑤,P1-β批二续):primary definite violation 下折叠 folded 规则 violation ──


def _fold_iss(rule_id, verdict="FAIL", need_human=None):
    """折叠单测条目:Rule 全字段 kwargs 构造在产线包侧(dedup_key 仿 _issue 三层键;
    need_human 缺省按 verdict 推,FAIL=False/其余=True,与 rule_runner 产物对齐)。"""
    nh = (verdict != "FAIL") if need_human is None else need_human
    return {"rule_id": rule_id, "verdict": verdict, "need_human": nh, "dedup_key": f"L{rule_id[1]}|{rule_id}|-", "message": f"{rule_id} msg"}


def test_fold_by_primary_folds_l3016_l3018_and_records_suppressed_by():
    """①L2-051 violation 存在 → 同面 L3-016/L3-018 violation 折叠移除,primary 条目落
    suppressed_by(被折叠 dedup_key 审计面——与 W9 只落日志的记账差异点);他规则条目不动。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    primary, l3016, l3018, other = _fold_iss("L2-051"), _fold_iss("L3-016"), _fold_iss("L3-018"), _fold_iss("L3-006")
    out = _fold_issues_by_primary([primary, l3016, l3018, other], "L2-051", ("L3-016", "L3-018"))
    assert [i["rule_id"] for i in out] == ["L2-051", "L3-006"], "仅 L3-016/L3-018 violation 折叠,primary 与他规则不动"
    assert primary["suppressed_by"] == ["L3|L3-016|-", "L3|L3-018|-"], "primary 落 suppressed_by(被折叠 dedup_key 列表,审计可反查)"


def test_fold_by_primary_keeps_folded_need_human():
    """②folded 规则 need_human 保留(need_human 不动不变式),且未折叠不记账。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    primary, l3016_nh = _fold_iss("L2-051"), _fold_iss("L3-016", verdict="UNKNOWN")
    out = _fold_issues_by_primary([primary, l3016_nh], "L2-051", ("L3-016", "L3-018"))
    assert [i["rule_id"] for i in out] == ["L2-051", "L3-016"] and out[1]["verdict"] == "UNKNOWN"
    assert "suppressed_by" not in primary, "零折叠时 primary 不落 suppressed_by"


def test_fold_by_primary_not_armed_by_primary_need_human():
    """③L2-051 仅 need_human 不武装折叠(照抄 w9⑤ 钉形):L3-016 violation 保留。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    primary_nh, l3016 = _fold_iss("L2-051", verdict="UNKNOWN"), _fold_iss("L3-016")
    out = _fold_issues_by_primary([primary_nh, l3016], "L2-051", ("L3-016", "L3-018"))
    assert len(out) == 2 and out[1]["verdict"] == "FAIL", "primary need_human(UNKNOWN)不武装,L3-016 FAIL 保留"


def test_fold_by_primary_fast_path_noop():
    """④零折叠快路径:primary 不在 → 原列表对象原样返回(W9 同款);primary 在但无 folded
    violation → 零折叠原样返回。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    issues = [_fold_iss("L3-016"), _fold_iss("L3-018", verdict="UNKNOWN")]
    assert _fold_issues_by_primary(list(issues), "L2-051", ("L3-016", "L3-018")) == issues, "primary 不在 → 原样返回(零折叠)"

    primary, other = _fold_iss("L2-051"), _fold_iss("L3-006")
    pair = [primary, other]
    assert _fold_issues_by_primary(pair, "L2-051", ("L3-016", "L3-018")) == pair, "无 folded violation → 原样返回(零折叠)"
    assert "suppressed_by" not in primary


@pytest.mark.asyncio
async def test_fold_wired_after_aggregation_in_evaluate_fields():
    """接线钉:evaluate_fields 聚合后单插入位(W9 行之后)——L2-051 violation 面上 L3-016
    violation 被主责折叠,primary 带 suppressed_by;生产包全链路走同一段分派+折叠核。"""
    pack = load_rulepack(PACK)
    fields = {
        "bid.full_text": "本投标文件为草稿版本,仅供内部评审使用",
        "bid.document_version": "V1.0",
        "bid.version_tag_occurrences": [{"value": "V2.0", "where": "页眉"}],
    }
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    assert any(i["rule_id"] == "L2-051" and i["verdict"] == "FAIL" for i in issues), "L2-051 regex 命中应出 FAIL"
    assert not any(i["rule_id"] == "L3-016" for i in issues), "L3-016 violation 应被 L2-051 主责折叠移除"
    prim = next(i for i in issues if i["rule_id"] == "L2-051")
    assert prim.get("suppressed_by"), "primary 条目带 suppressed_by 记账(接线后端到端)"


# ── L1-007→L2-030 条件折叠(A-续-①,P1-β批二续 Task3):签章位面上 L2-030 让位主责 ──


def test_fold_l1007_folds_l2030_and_records_suppressed_by():
    """A-续-①:L1-007 definite violation 存在 → 同面 L2-030 violation 折叠移除,
    primary 条目落 suppressed_by(被折叠 dedup_key 审计面,同 L2-051 helper 契约)。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    primary, l2030 = _fold_iss("L1-007"), _fold_iss("L2-030")
    out = _fold_issues_by_primary([primary, l2030], "L1-007", ("L2-030",))
    assert [i["rule_id"] for i in out] == ["L1-007"], "L2-030 violation 折叠,primary 保留"
    assert primary["suppressed_by"] == [l2030["dedup_key"]], "primary 落 suppressed_by"


def test_fold_l1007_need_human_keeps_l2030():
    """L1-007 仅 need_human(存在性未定)不武装折叠:L2-030 violation 独立面保留,不记账。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    primary_nh, l2030 = _fold_iss("L1-007", verdict="UNKNOWN"), _fold_iss("L2-030")
    out = _fold_issues_by_primary([primary_nh, l2030], "L1-007", ("L2-030",))
    assert len(out) == 2 and out[1]["rule_id"] == "L2-030" and out[1]["verdict"] == "FAIL"
    assert "suppressed_by" not in primary_nh


def test_fold_l1007_absent_keeps_l2030():
    """L1-007 不在(签章页全齐零候选)→ 零折叠快路径,L2-030 violation 保留。"""
    from app.extensions.bid_review.engine.eval_core import _fold_issues_by_primary

    l2030 = _fold_iss("L2-030")
    out = _fold_issues_by_primary([l2030], "L1-007", ("L2-030",))
    assert out == [l2030], "primary 不在 → 原样返回,L2-030 violation 保留"


@pytest.mark.asyncio
async def test_fold_l1007_definite_primary_folds_l2030_in_pipeline():
    """管线级正向半边(金标准面钉不到的半边):docs_text 注入使 L1-007 scripted 证据对齐
    → definite violation(need_human=false)→ L2-030 violation 被主责折叠移除,
    primary 落 suppressed_by。金标准面 docs_text 恒空 → verify 第2道把 sem issue 降级
    need_human=true,故金标准只钉负向共存半边(L2-030-l1007-folded.yaml),正向在此钉死。"""
    pack = load_rulepack(PACK)
    fields = {
        "bid.missing_signature_pages": ["第12页 缺少骑缝章"],
        "tender.signature_slots": [
            {"no": "法人章", "name": "法定代表人", "page": 12},
            {"no": "公章", "name": "投标人单位", "page": 12},
        ],
        "bid.signature_slots": [{"no": "法人章", "name": "法定代表人", "page": 12}],
    }
    docs_text = {"bid.pdf": {12: "第12页未见骑缝章"}}
    model_fn = wrap_model_fn(
        _quiet_model({"L1-007": '{"verdicts": [{"clause_id": "SG-1", "verdict": "partial", "confidence": 0.9, "reason": "骑缝章缺失", "evidence": [{"doc_id": "bid.pdf", "page": 12, "text": "第12页未见骑缝章"}]}]}'}),
    )
    issues = await evaluate_fields(pack, fields, model_fn=model_fn, docs_text=docs_text)
    l1007 = [i for i in issues if i["rule_id"] == "L1-007"]
    assert len(l1007) == 1 and l1007[0]["verdict"] == "FAIL" and not l1007[0]["need_human"], f"证据对齐 → L1-007 definite FAIL: {l1007}"
    assert not any(i["rule_id"] == "L2-030" for i in issues), "L2-030 violation 应被 definite L1-007 主责折叠移除"
    assert l1007[0].get("suppressed_by"), "primary 落 suppressed_by(管线端到端)"


# ── P1-β批三:verdict 五值域与别名归一(C-08 终章)───────────────────────────────


def test_normalize_verdict_aliases():
    from app.extensions.bid_review.engine.verdicts import (
        VERDICT_DOMAIN,
        normalize_verdict,
    )

    assert normalize_verdict("violation") == "FAIL"
    assert normalize_verdict("need_human") == "UNKNOWN"
    assert normalize_verdict("unclear") == "UNKNOWN"
    assert normalize_verdict("pass") == "PASS"
    for v in VERDICT_DOMAIN:  # 新值恒等
        assert normalize_verdict(v) == v
    assert normalize_verdict("false_positive") == "false_positive"  # 复核域透传
    assert normalize_verdict("") == ""  # 空/未知串防御性原样
    assert normalize_verdict(None) == ""
