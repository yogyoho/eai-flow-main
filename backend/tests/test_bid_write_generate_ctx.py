"""批二十 M1-i 金标闭环测试(EAI-CUSTOM 2026-11-13)——生成端→执行端契约闭合:
夹具输入→build_ctx→run_assertions 全 43 PASS;降级负例=缺单价(PS-007 诚实
FAIL)/缺素材(BL-004+RT-007 FAIL,伪零不静默);decl 承诺溯源(BL-010);二跑
字节级相等(确定性验收面)。"""

import json

from bid_write_exec_fixtures import get_result, statuses
from bid_write_generate_fixtures import closure_inputs

from app.extensions.bid_write.executor.gate import gate_verdict
from app.extensions.bid_write.executor.runner import run_assertions
from app.extensions.bid_write.generate import build_ctx


def _build(**overrides):
    fields, rows, material, knobs = closure_inputs(**overrides)
    return build_ctx(fields, rows, material, **knobs)


def test_golden_closure_all_pass():
    """闭环:生成端 ctx→执行器 43 条断言全 PASS(生成器与校验器契约零漂移)。"""
    report = run_assertions(_build())
    fails = {r.assertion_id: r.status for r in report.results if r.status != "PASS"}
    assert fails == {}, fails
    assert len(report.results) == 43
    assert gate_verdict(report)["blocked"] is False


def test_missing_unit_price_ps007_fail():
    """缺一张单价→留空暴露:PS-007 FAIL(不补价不近似,§2.2 降级 D0 面)。"""
    ctx = _build(unit_prices={"1.1": "800000"})
    report = run_assertions(ctx)
    r = get_result(report, "SK-PS-007")
    assert r.status == "FAIL" and "1.2" in r.message
    assert gate_verdict(report)["blocked"] is True


def test_material_missing_honest_fail():
    """素材缺位→BL-001 槽位空 D0 FAIL(bidder/legal 诚实缺件,短路 BL 后续)
    + RT-007 诚实伪零 FAIL;AI 全待补仍带负证据(CMN-005 PASS,不静默)。"""
    fields, rows, _material, knobs = closure_inputs()
    ctx = build_ctx(fields, rows, {}, **knobs)
    report = run_assertions(ctx)
    st = statuses(report)
    r = get_result(report, "SK-BL-001")
    assert r.status == "FAIL" and "bidder_name" in r.message
    assert st["SK-RT-007"] == "FAIL"
    assert st["SK-CMN-005"] == "PASS"


def test_decl_commitments_traced():
    """decl 矩阵行→投标函承诺逐条 clause_id 溯源(BL-010 PASS 面)。"""
    ctx = _build()
    commitments = ctx["products"]["bid_letter"]["extra_commitments"]
    decl_ids = [c["clause_id"] for c in commitments if c.get("clause_id")]
    assert len(decl_ids) == 2 and all(cid.startswith("decl:") for cid in decl_ids)
    assert get_result(run_assertions(ctx), "SK-BL-010").status == "PASS"


def test_two_runs_byte_equal():
    """同输入二跑 JSON 字节级相等(纯函数确定性,20× 验收面抽样)。"""
    a = json.dumps(_build(), sort_keys=True, ensure_ascii=False)
    b = json.dumps(_build(), sort_keys=True, ensure_ascii=False)
    assert a == b
