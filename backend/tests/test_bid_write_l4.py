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
