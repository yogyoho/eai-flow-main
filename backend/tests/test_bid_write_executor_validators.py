"""批二十 M1 全量 43 条校验器测试(EAI-CUSTOM 2026-11-13)——amount_cn 固定函数
边界值、wordscan 桶 pin(union==FORBIDDEN_WORDS keys)、逐技能正/负例、特免面
(PS-006 限价未确认/PS-010 历史价静默)、词级升级(BL-006 红线 D0/PS-009 无机制
D0)、CMN 扫描面排除 requirement_excerpt。"""

from __future__ import annotations

from decimal import Decimal

import pytest
from bid_write_exec_fixtures import get_result, green_ctx, statuses

from app.extensions.bid_write.contracts import FORBIDDEN_WORDS
from app.extensions.bid_write.executor.amount_cn import cn_to_num, num_to_cn
from app.extensions.bid_write.executor.runner import run_assertions
from app.extensions.bid_write.executor.validators import REGISTRY
from app.extensions.bid_write.executor.wordscan import CATEGORIES, scan_text, words_for

# ── amount_cn 固定函数(双向+canonical 拒收)───────────────────────────────────


@pytest.mark.parametrize(
    ("value", "cn"),
    [
        (0, "零元整"),
        (0.5, "伍角整"),
        (0.05, "伍分"),
        (1, "壹元整"),
        (1.5, "壹元伍角整"),
        (1.05, "壹元零伍分"),
        (1.55, "壹元伍角伍分"),
        (10, "壹拾元整"),
        (105, "壹佰零伍元整"),
        (1005, "壹仟零伍元整"),
        (10005, "壹万零伍元整"),
        (100000, "壹拾万元整"),
        (2000000, "贰佰万元整"),
        (100005000, "壹亿零伍仟元整"),
        (100000500, "壹亿零伍佰元整"),
        (100500000, "壹亿伍拾万元整"),
        (1000000000, "壹拾亿元整"),
        (123456789.05, "壹亿贰仟叁佰肆拾伍万陆仟柒佰捌拾玖元零伍分"),
        ("2000000", "贰佰万元整"),  # str 入参同值
    ],
)
def test_num_to_cn(value, cn):
    assert num_to_cn(value) == cn


def test_num_to_cn_half_up_edge():
    assert num_to_cn(0.005) == "壹分"  # 0.005 quantize(0.01, HALF_UP)=0.01
    assert num_to_cn(1.005) == "壹元零壹分"


def test_roundtrip_all_fixtures():
    for value in (0, 0.5, 0.05, 1.05, 105, 2000000, 100005000, 123456789.05):
        assert cn_to_num(num_to_cn(value)) == Decimal(str(value)).quantize(Decimal("0.01"))


@pytest.mark.parametrize(
    ("bad",),
    [
        ("贰佰万整",),  # 缺 元
        ("壹元伍角",),  # 角后无整无分(非 canonical)
        ("壹元伍角零伍分",),  # 零 间隔仅用于有元无角
        ("贰佰",),  # 无元尾缀
        ("整",),  # 孤整
        ("",),
    ],
)
def test_cn_to_num_rejects_non_canonical(bad):
    with pytest.raises(ValueError):
        cn_to_num(bad)


def test_cn_to_num_canonical_accepts():
    assert cn_to_num("贰佰万元整") == Decimal("2000000.00")
    assert cn_to_num("壹亿零伍仟元整") == Decimal("100005000.00")
    assert cn_to_num("零元整") == Decimal("0.00")
    assert cn_to_num("伍分") == Decimal("0.05")
    assert cn_to_num("壹元零伍分") == Decimal("1.05")


def test_num_to_cn_negative_rejected():
    with pytest.raises(ValueError):
        num_to_cn(-1)


# ── wordscan(桶 pin + 匹配语义)──────────────────────────────────────────────


def test_wordscan_buckets_cover_all_forbidden_words():
    union: set[str] = set()
    for words in CATEGORIES.values():
        assert not union & words, f"桶间重复: {union & words}"
        union |= words
    assert union == set(FORBIDDEN_WORDS.keys()), f"漏桶词: {set(FORBIDDEN_WORDS) - union}"


def test_wordscan_case_insensitive():
    hits = scan_text("计划 TBD 略", words_for("placeholder"))
    assert hits == ["TBD"]
    assert scan_text("计划 tbd 略", words_for("placeholder")) == ["TBD"]
    assert scan_text("xx 矿业", words_for("placeholder")) == ["XX"]


def test_wordscan_empty_bucket_rejected():
    with pytest.raises(ValueError):
        words_for()


# ── 逐技能负例(绿夹具变异→FAIL/词级升级)────────────────────────────────────


def _run(ctx, skills=None):
    return run_assertions(ctx, skills=skills)


def test_bl001_empty_slot_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["legal_rep_name"] = ""
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-001"] == "FAIL"
    assert "legal_rep_name" in get_result(_run(ctx, ("BL",)), "SK-BL-001").message


def test_bl002_cn_mismatch_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["total_amount_cn"] = "叁佰万元整"  # 与 num 2000000 不符且非该数 canonical
    r = get_result(_run(ctx, ("BL",)), "SK-BL-002")
    assert r.status == "FAIL" and "金额不一致" in r.message


def test_bl002_non_canonical_cn_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["total_amount_cn"] = "贰佰万"  # 缺 元/整
    r = get_result(_run(ctx, ("BL",)), "SK-BL-002")
    assert r.status == "FAIL" and "非 canonical" in r.message


def test_bl003_validity_short_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["valid_days"] = 60
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-003"] == "FAIL"


def test_bl004_bidder_mismatch_fails():
    ctx = green_ctx()
    ctx["material"]["bidder_profile"]["name"] = "ZZ装备股份有限公司"
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-004"] == "FAIL"


def test_bl004_material_missing_is_fail_not_error():
    ctx = green_ctx()
    del ctx["material"]
    r = get_result(_run(ctx, ("BL",)), "SK-BL-004")
    assert r.status == "FAIL" and "缺件" in r.message


def test_bl005_sign_after_deadline_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["sign_date"] = "2026-12-15"
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-005"] == "FAIL"


def test_bl005_bad_date_format_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["sign_date"] = "2026/12/15"
    r = get_result(_run(ctx, ("BL",)), "SK-BL-005")
    assert r.status == "FAIL" and "格式非法" in r.message


def test_bl006_redline_hit_escalates_d0():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["text"] = "我方确保包过,请放心。"
    r = get_result(_run(ctx, ("BL",)), "SK-BL-006")
    assert r.status == "FAIL" and r.level == "D0" and r.blocks_export is True


def test_bl006_vague_hit_stays_d1():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["text"] = "我方将尽量配合现场安排。"
    r = get_result(_run(ctx, ("BL",)), "SK-BL-006")
    assert r.status == "FAIL" and r.level == "D1" and r.blocks_export is False


def test_bl007_similarity_below_threshold():
    ctx = green_ctx()
    ctx["pre"]["bl_fixed_similarity"] = 0.95
    r = get_result(_run(ctx, ("BL",)), "SK-BL-007")
    assert r.status == "FAIL" and r.deterministic is False


def test_bl008_missing_seal_anchor():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["signature"]["seal_anchor"] = False
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-008"] == "FAIL"


def test_bl009_unresolved_entity_ref():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["entity_refs"] = ["ent:license", "ent:ghost"]
    r = get_result(_run(ctx, ("BL",)), "SK-BL-009")
    assert r.status == "FAIL" and "ent:ghost" in r.message


def test_bl010_commitment_without_trace():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["extra_commitments"].append({"text": "无溯源承诺"})
    st = statuses(_run(ctx, ("BL",)))
    assert st["SK-BL-010"] == "FAIL"


def test_ps001_extra_row_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["rows"].append({"id": "1.9", "name": "多余项", "qty": 1, "unit": "项", "unit_price": 1, "amount": 1})
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-001"] == "FAIL" and "多余行" in get_result(_run(ctx, ("PS",)), "SK-PS-001").message


def test_ps001_missing_row_fails():
    ctx = green_ctx()
    ctx["tender"]["tender.boq_items"].append({"id": "1.3", "name": "备品备件", "qty": 1, "unit": "批"})
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-001"] == "FAIL" and "1.3" in get_result(_run(ctx, ("PS",)), "SK-PS-001").message


def test_ps002_qty_mismatch_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["rows"][0]["qty"] = 3
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-002"] == "FAIL"


def test_ps003_summary_drift_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["summary_total"] = 2000001
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-003"] == "FAIL"


def test_ps004_non_canonical_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["amount_cn"] = "贰佰万元"  # 缺 整
    r = get_result(_run(ctx, ("PS",)), "SK-PS-004")
    assert r.status == "FAIL"


def test_ps005_bad_mode_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["price_mode"] = "含税加价"
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-005"] == "FAIL"


def test_ps006_over_max_price_fails_d0():
    ctx = green_ctx()
    ctx["tender"]["tender.max_price"] = 1500000
    r = get_result(_run(ctx, ("PS",)), "SK-PS-006")
    assert r.status == "FAIL" and r.level == "D0"


def test_ps006_no_max_price_skips_d2():
    ctx = green_ctx()
    del ctx["tender"]["tender.max_price"]
    r = get_result(_run(ctx, ("PS",)), "SK-PS-006")
    assert r.status == "SKIPPED" and r.level == "D2"
    assert r.skipped_reason == "no_signal" and "限价未确认" in r.message


def test_ps007_zero_unit_price_fails():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["rows"][1]["unit_price"] = 0
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-007"] == "FAIL" and "1.2" in get_result(_run(ctx, ("PS",)), "SK-PS-007").message


def test_ps008_replay_drift_fails():
    ctx = green_ctx()
    ctx["pre"]["ps_replay_equal"] = False
    st = statuses(_run(ctx, ("PS",)))
    assert st["SK-PS-008"] == "FAIL" and get_result(_run(ctx, ("PS",)), "SK-PS-008").deterministic is False


def test_ps009_vague_price_with_mechanism_d1():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["note"] = "单价暂估,随市场调整。"
    r = get_result(_run(ctx, ("PS",)), "SK-PS-009")
    assert r.status == "FAIL" and r.level == "D1"


def test_ps009_vague_price_no_mechanism_escalates_d0():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["note"] = "单价暂估。"
    ctx["products"]["price_sheet"]["price_adjust_mechanism"] = False
    r = get_result(_run(ctx, ("PS",)), "SK-PS-009")
    assert r.status == "FAIL" and r.level == "D0" and r.blocks_export is True


def test_ps010_abnormal_low_fails_d2():
    ctx = green_ctx()
    ps = ctx["products"]["price_sheet"]
    ps["detail_total"] = 800000  # < 0.7×2000000
    ps["amount_cn"] = "捌拾万元整"
    ps["summary_total"] = ps["open_letter_total"] = 800000  # 四面同步否则 PS-003 D0 短路殃及本条
    ctx["products"]["bid_letter"]["slots"]["total_amount_num"] = 800000
    ps["rows"][0]["amount"] = 400000
    ps["rows"][0]["unit_price"] = 200000
    r = get_result(_run(ctx, ("PS",)), "SK-PS-010")
    assert r.status == "FAIL" and r.level == "D2"


def test_ps010_no_history_skips_d3():
    ctx = green_ctx()
    ctx["material"]["price_history"] = []
    r = get_result(_run(ctx, ("PS",)), "SK-PS-010")
    assert r.status == "SKIPPED" and r.level == "D3" and r.skipped_reason == "no_signal"


def test_rt001_star_uncovered_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["matrix_star_clause_ids"].append("att:2")
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-001"] == "FAIL" and "att:2" in get_result(_run(ctx, ("RT",)), "SK-RT-001").message


def test_rt002_star_negative_deviation_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0]["conclusion"] = "负偏离"
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-002"] == "FAIL"
    # RT-005 同场景:负偏离闭环面独立可测(star=False 免 RT-002 短路)


def test_rt003_empty_answer_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][1]["response_text"] = "满足招标文件要求。"
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-003"] == "FAIL"


def test_rt004_low_overlap_fails():
    ctx = green_ctx()
    ctx["pre"]["rt_excerpt_overlaps"]["att:1"] = 0.5
    r = get_result(_run(ctx, ("RT",)), "SK-RT-004")
    assert r.status == "FAIL" and r.deterministic is False


def test_rt005_negative_without_plan_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0].update({"star": False, "conclusion": "负偏离", "deviation_reason": "产能不足", "replacement_plan": None})
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-005"] == "FAIL"


def test_rt006_cross_field_drift_fails():
    ctx = green_ctx()
    ctx["pre"]["rt_cross_field"]["total_amount"]["other"] = 1900000
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-006"] == "FAIL" and get_result(_run(ctx, ("RT",)), "SK-RT-006").deterministic is True


def test_rt007_empty_evidence_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0]["evidence_refs"] = []
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-007"] == "FAIL"


def test_rt007_material_entities_missing_fails_all():
    ctx = green_ctx()
    del ctx["material"]["entities"]
    r = get_result(_run(ctx, ("RT",)), "SK-RT-007")
    assert r.status == "FAIL" and "素材库缺位" in r.message


def test_rt008_deviation_marker_in_full_response():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0]["response_text"] = "我方无法满足该条款,建议协商。"
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-008"] == "FAIL"


def test_rt009_placeholder_in_response_fails():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0]["response_text"] = "按待补充资料提供。"
    st = statuses(_run(ctx, ("RT",)))
    assert st["SK-RT-009"] == "FAIL"


# ── CMN 全文扫描面(占位/措辞/实体/回放/负证据)────────────────────────────


def test_cmn001_placeholder_anywhere_d0():
    ctx = green_ctx()
    ctx["products"]["attachment_index"]["body_text"] = "技术方案详见附件待补充。"
    r = get_result(_run(ctx), "SK-CMN-001")
    assert r.status == "FAIL" and r.level == "D0" and "待补充" in r.message


def test_cmn001_excludes_requirement_excerpt():
    ctx = green_ctx()
    ctx["products"]["response_table"]["rows"][0]["requirement_excerpt"] = "投标人须按招标文件执行并加盖公章(原文含空应答词:满足招标文件要求)。"
    st = statuses(_run(ctx))
    assert st["SK-CMN-001"] == "PASS"  # 引用原文不算我方表述;RT-003 只扫 response_text 也不扫 excerpt
    assert st["SK-RT-003"] == "PASS"


def test_cmn001_unclosed_interp_fails():
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["text"] = "报价详见 {{calc(表1。"
    st = statuses(_run(ctx))
    assert st["SK-CMN-001"] == "FAIL" and "未闭合插值" in get_result(_run(ctx), "SK-CMN-001").message


def test_cmn002_redline_any_slice_escalates_d0():
    ctx = green_ctx()
    ctx["products"]["price_sheet"]["note"] = "配合业主内部渠道操作。"
    r = get_result(_run(ctx), "SK-CMN-002")
    assert r.status == "FAIL" and r.level == "D0"


def test_cmn003_unresolved_ref_in_any_slice():
    ctx = green_ctx()
    ctx["products"]["response_table"]["entity_refs"] = ["ent:ghost"]
    r = get_result(_run(ctx), "SK-CMN-003")
    assert r.status == "FAIL" and "ent:ghost" in r.message


def test_cmn004_replay_drift_fails_d0():
    ctx = green_ctx()
    ctx["pre"]["kernel_replay_equal"] = False
    r = get_result(_run(ctx), "SK-CMN-004")
    assert r.status == "FAIL" and r.level == "D0" and r.blocks_export is True


def test_cmn005_pending_without_evidence_fails():
    ctx = green_ctx()
    ctx["products"]["attachment_index"]["pending_items"] = [
        {"item": "安全生产许可证", "status": "待补", "negative_evidence": {}},
        {"item": "业绩证明", "status": "待补", "negative_evidence": {"nearest": "同类A-2025"}},
    ]
    r = get_result(_run(ctx), "SK-CMN-005")
    assert r.status == "FAIL" and "安全生产许可证" in r.message
    st = statuses(_run(ctx))
    assert st["SK-AI-009"] == "FAIL" and get_result(_run(ctx), "SK-AI-009").source_id == "SK-CMN-005"


def test_registry_count_unchanged():
    """43 条注册、42 函数(AI-009 委托镜像)——防注册漂移。"""
    assert len(REGISTRY) == 42
