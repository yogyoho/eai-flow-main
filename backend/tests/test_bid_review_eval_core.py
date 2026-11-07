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
    assert any(i["verdict"] == "violation" and i["severity"] == "fatal" for i in by_rule["L1-009"])
    # L1-005 输入缺失 → need_human(缺字段约定)
    assert any(i["verdict"] == "need_human" for i in by_rule["L1-005"])


@pytest.mark.asyncio
async def test_none_fields_stripped_before_eval():
    pack = load_rulepack(PACK)
    fields = {"bid.total_price": 1000001.0, "tender.max_price": 1000000.0, "bid.price_includes_tax": True, "tender.price_includes_tax": None}
    issues = await evaluate_fields(pack, fields, model_fn=wrap_model_fn(_quiet_model()))
    l9 = [i for i in issues if i["rule_id"] == "L1-009"]
    assert all(i["verdict"] == "need_human" for i in l9)  # None 字段=缺字段,不判违规


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
    assert len(l9) == 1 and l9[0]["verdict"] == "need_human" and "boom" in l9[0]["message"]


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
    assert len(sem) == 1 and sem[0]["verdict"] == "violation" and not sem[0]["need_human"], "partial→violation;need_human=False 钉死 docs_text 位置(错位则证据对齐失配翻旗)"
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


def _iss(rule_id, entity_keys, verdict="violation"):
    return {"rule_id": rule_id, "verdict": verdict, "entity_keys": entity_keys, "message": f"{rule_id} {entity_keys}"}


def test_w9_suppress_folds_same_entity_l3012_only():
    """W9 四断言:①同实体(业绩合同)L3-012 violation 被 L2-021 violation 折叠移除;
    ②异实体(其他文件)L3-012 照常保留;③L3-012 need_human 不动;④无 L2-021 时原样返回。"""
    from app.extensions.bid_review.engine.eval_core import _suppress_l3012_by_l2021

    issues = [
        _iss("L2-021", ["业绩合同"]),
        _iss("L3-012", ["业绩合同"]),  # 同实体 → 折叠
        _iss("L3-012", ["其他文件"]),  # 异实体 → 保留
        _iss("L3-012", ["业绩合同"], verdict="need_human"),  # need_human 不动
    ]
    out = _suppress_l3012_by_l2021(issues)
    assert len(out) == 3, "仅同实体 violation 折叠一条,L2-021 本体与其余条目不动"
    l3 = [i for i in out if i["rule_id"] == "L3-012"]
    assert [i["entity_keys"] for i in l3] == [["其他文件"], ["业绩合同"]]  # ①②折叠/保留
    assert l3[1]["verdict"] == "need_human"  # ③ need_human 不动

    no_l2021 = [_iss("L3-012", ["业绩合同"]), _iss("L3-012", ["其他文件"], verdict="need_human")]
    assert _suppress_l3012_by_l2021(no_l2021) == no_l2021  # ④ 无 L2-021 → 原样返回(零折叠)
