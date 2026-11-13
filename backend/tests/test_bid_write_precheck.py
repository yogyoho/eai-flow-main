"""批廿一 M2-a/M2-b:F6 规则层预审查+导出前置校验(纯函数面)。

投影契约:products→bid.* 平面字段(同尺);det-only scope;缺口=UNKNOWN 诚实。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from bid_write_generate_fixtures import closure_inputs

from app.extensions.bid_write.generate import build_ctx
from app.extensions.bid_write.precheck import project_bid_fields, run_export_gate, run_rule_precheck


def _green_ctx():
    t, rows, mat, knobs = closure_inputs()
    return build_ctx(t, rows, mat, **knobs)


def test_projection_green_shape():
    """green 产物→bid.* 平面字段:金额三键同源/大写透传/boq 保 id/无凭证诚实 False。"""
    fields = project_bid_fields(_green_ctx())
    assert fields["bid.total_price"] == fields["bid.subtotal"] == 2000000  # 1.6M+0.4M
    assert fields["bid.total_price_words"] == "贰佰万元整"
    assert fields["bid.validity_days"] == 90
    assert {r["id"] for r in fields["bid.boq_items"]} == {"1.1", "1.2"}
    assert len(fields["bid.detail_rows"]) == 2
    assert fields["bid.deposit_amount"] == 100000
    assert fields["bid.deposit_forms"] == ["银行保函"]
    assert fields["bid.deposit_receipt_present"] is False  # M0 无凭证面,诚实
    assert fields["bid.alternative_price_offers"] == []  # 生成器不造替代方案
    assert fields["bid.tax_rate_occurrences"][0]["value"] is not None


def test_projection_omits_absent():
    """缺件不投影:bidder_name 空→bid.entity_name_occurrences 缺席(UNKNOWN 面)。"""
    t, rows, _mat, knobs = closure_inputs()
    ctx = build_ctx(t, rows, {}, **knobs)  # 素材清空
    fields = project_bid_fields(ctx)
    assert "bid.entity_name_occurrences" not in fields


@pytest.mark.asyncio
async def test_precheck_green_no_l1_fatal():
    """green 产物:无 L1 fatal FAIL→不阻断;UNKNOWN 计数>0(缺口诚实)。"""
    pre = await run_rule_precheck(project_bid_fields(_green_ctx()))
    assert pre["blocked"] is False and pre["l1_fatal_fail"] == []
    assert pre["counts"].get("UNKNOWN", 0) > 0
    assert pre["scope_note"]["det_rules"] == 51  # smoke 实测锚


@pytest.mark.asyncio
async def test_precheck_tampered_total_blocks():
    """破坏总额→L1-010 fatal FAIL→阻断(明细和≠总价面)。"""
    fields = project_bid_fields(_green_ctx())
    fields["bid.total_price"] = 2000001
    pre = await run_rule_precheck(fields)
    assert pre["blocked"] is True and "L1-010" in pre["l1_fatal_fail"]


@pytest.mark.asyncio
async def test_precheck_no_error_verdicts():
    """det-only scope:零 ERROR(sem 规则整体排除,不喂模型零伪 ERROR)。"""
    pre = await run_rule_precheck(project_bid_fields(_green_ctx()))
    assert pre["counts"].get("ERROR", 0) == 0


def test_block_export_levels_pinned():
    """口径钉死:阻断层级=D0(gate_verdict 同律);水印常量存在。"""
    from app.extensions.bid_write.contracts import BLOCK_EXPORT_LEVELS, EXPORT_RISK_WATERMARK

    assert BLOCK_EXPORT_LEVELS == ("D0",)
    assert EXPORT_RISK_WATERMARK == "商务风险未确认"


@pytest.mark.asyncio
async def test_export_gate_green():
    """green 闭环:43 断言全 PASS→不阻断;水印恒加(L4 未跑模型=未确认语义)。"""
    ctx = _green_ctx()
    export = await run_export_gate(ctx)
    assert export["blocked"] is False and export["reasons"] == []
    assert export["watermark"] == "商务风险未确认"
    assert export["assertion_counts"]["PASS"] == 43
    assert export["rule_counts"].get("FAIL", 0) <= 1  # L2-033 诚实非阻断
    assert export["l1_fatal_fail"] == []


@pytest.mark.asyncio
async def test_export_gate_d0_blocks():
    """D0 面阻断:缺单价→PS-007 FAIL→blocked+reasons;水印仍在。"""
    t, rows, mat, knobs = closure_inputs()
    knobs = dict(knobs)
    knobs["unit_prices"] = {"1.1": "800000"}  # 缺 1.2
    export = await run_export_gate(build_ctx(t, rows, mat, **knobs))
    assert export["blocked"] is True and "SK-PS-007" in export["reasons"]


@pytest.mark.asyncio
async def test_export_gate_rule_layer_blocks():
    """规则层阻断:产物总额被篡改→L1-010 fatal FAIL→blocked 并入 reasons。"""
    ctx = _green_ctx()
    ctx["products"]["price_sheet"]["detail_total"] = 2000001
    export = await run_export_gate(ctx)
    assert export["blocked"] is True and "L1-010" in export["reasons"]
