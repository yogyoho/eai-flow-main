"""批廿四 P1-γ L4 语义审查面测试:投影/参与卡筛选/摘除条件/gate 形参/worker 接线。

advisory-only 铁律:L4 永不入 blocked/reasons(meta counts_toward_bid_gate=false);
水印摘除=executed ∧ 参与卡零 FAIL/ERROR/need_human/UNKNOWN(unclear=未确认→保持)。
默认 knobs(无 general_commitments)→参与卡空→L4 不执行→水印恒加=绿跑零行为。
"""

import json
from types import SimpleNamespace

import pytest

from app.extensions.bid_write import contracts
from app.extensions.bid_write.precheck import project_bid_fields


def _ctx_with_commitments():
    """最小 ctx:BL 带 general_commitments(经 build_ctx 纯装配),tender 带实质性条款。"""
    from app.extensions.bid_write.generate import build_ctx

    return build_ctx(
        {"tender.boq_items": [{"id": "1", "name": "设备A", "qty": 1, "unit": "项"}], "tender.substantive_clauses": ["投标人不得转包"]},
        [],  # 矩阵行空;承诺全走 general_commitments knob
        None,
        general_commitments=[{"text": "额外承诺:终身免费维保", "clause_id": ""}],
    )


def _stub_model(verdict="full", confidence=0.95):
    """L4 模型 stub:_call_model 契约=callable 返回带 .content 对象。"""

    def _fn(messages):
        payload = {"verdicts": [{"clause_id": "C1", "verdict": verdict, "confidence": confidence, "reason": "stub", "evidence": [{"doc_id": "bid", "page": 1, "text": "stub"}]}]}
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    return _fn


def _l4_fields():
    """L4-003/004 参与最小字段面。"""
    return {
        "bid.service_commitments": [{"text": "终身免费维保", "clause_id": ""}],
        "bid.full_text": "承诺:终身免费维保",
        "tender.substantive_clauses": ["投标人不得转包"],
    }


def test_project_bid_fields_l4_projections():
    """commitments 非空→bid.service_commitments;bl.text 非空→bid.full_text;
    无 commitments→service_commitments 缺席(零行为面:绿跑参与卡空→L4 不执行)。"""
    out = project_bid_fields(_ctx_with_commitments())
    assert out["bid.service_commitments"] == [{"text": "额外承诺:终身免费维保", "clause_id": ""}]
    assert out["bid.full_text"]
    bare = project_bid_fields({"products": {"bid_letter": {"slots": {}, "text": "x"}, "price_sheet": {}}})
    assert "bid.service_commitments" not in bare


@pytest.mark.asyncio
async def test_l4_no_participants_not_executed():
    """无承诺→参与卡空→executed=False 不烧模型(零行为面);缺输入卡诚实列名。"""
    from app.extensions.bid_write.precheck import run_l4_review

    out = await run_l4_review({}, "", _stub_model())
    assert out["executed"] is False
    assert out["watermark_removed"] is False
    assert len(out["input_missing"]) >= 8  # 多数卡缺输入诚实列名


@pytest.mark.asyncio
async def test_l4_all_pass_removes_watermark():
    """L4-003/004 参与(L4-005 缺 tender.clauses 列 input_missing);全 full→零条目→摘除。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    from app.extensions.bid_write.precheck import run_l4_review

    out = await run_l4_review(_l4_fields(), "承诺:终身免费维保", wrap_model_fn(_stub_model("full")))
    assert out["executed"] is True
    assert set(out["participants"]) == {"L4-003", "L4-004"}
    assert "L4-005" in out["input_missing"]
    assert out["watermark_removed"] is True


@pytest.mark.asyncio
async def test_l4_fail_or_unclear_keeps_watermark():
    """none→FAIL 条目;unclear→need_human;两者都不摘(未确认=未确认)。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    from app.extensions.bid_write.precheck import run_l4_review

    fail = await run_l4_review(_l4_fields(), "x", wrap_model_fn(_stub_model("none")))
    assert fail["executed"] is True and fail["watermark_removed"] is False
    unclear = await run_l4_review(_l4_fields(), "x", wrap_model_fn(_stub_model("unclear", confidence=0.5)))
    assert unclear["watermark_removed"] is False


@pytest.mark.asyncio
async def test_l4_model_missing_degrades_error_keeps_watermark():
    """恒抛闭包→逐规则隔离 ERROR→水印保持(诚实,绝不假绿)。"""
    from app.extensions.bid_review.worker import ModelNotConfigured

    from app.extensions.bid_write.precheck import run_l4_review

    def _boom(messages):
        raise ModelNotConfigured("no model")

    out = await run_l4_review(_l4_fields(), "x", _boom)
    assert out["executed"] is True and out["watermark_removed"] is False
    assert out["counts"].get("ERROR", 0) >= 1


@pytest.mark.asyncio
async def test_export_gate_l4_advisory_and_watermark():
    """gate 形:l4 摘除→watermark=None;不供 l4_model_fn→恒加(既有面零破坏);
    L4 零贡献 blocked(advisory-only 铁律)。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn

    from app.extensions.bid_write.precheck import run_export_gate

    ctx = _ctx_with_commitments()
    gone = await run_export_gate(ctx, l4_model_fn=wrap_model_fn(_stub_model("full")))
    assert gone["watermark"] is None
    assert gone["l4"]["executed"] is True
    keep = await run_export_gate(ctx)  # 既有签名零破坏
    assert keep["watermark"] == contracts.EXPORT_RISK_WATERMARK
    assert keep["l4"] is None
    fail = await run_export_gate(ctx, l4_model_fn=wrap_model_fn(_stub_model("none")))
    assert fail["watermark"] == contracts.EXPORT_RISK_WATERMARK
