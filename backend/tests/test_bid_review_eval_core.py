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
