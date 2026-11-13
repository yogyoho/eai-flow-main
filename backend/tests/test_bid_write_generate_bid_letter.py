"""批二十 M1-f BL 渲染测试(EAI-CUSTOM 2026-11-13)——金额引用报价表/主体信息
仅素材源/固定段锚/禁用词零命中/slots 11 键=green 逐键。"""

from bid_write_exec_fixtures import green_ctx

from app.extensions.bid_write.executor.wordscan import scan_text, words_for
from app.extensions.bid_write.generate.bid_letter import FIXED_TEXT, render_bid_letter

_FIELDS = {
    "tender.purchaser_name": "华源矿业集团有限公司",
    "tender.project_name": "某矿井智能化建设项目",
    "tender.tender_no": "TB-2026-001",
    "tender.required_validity_days": 90,
    "tender.deposit_required": 100000,
    "tender.deposit_forms": ["银行保函"],
}
_MATERIAL = {"bidder_profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"}}


def _render(ps, **kw):
    kw.setdefault("sign_date", "2026-11-20")
    kw.setdefault("material", _MATERIAL)
    return render_bid_letter(_FIELDS, ps, kw.pop("material"), extra_commitments=green_ctx()["products"]["bid_letter"]["extra_commitments"], **kw)


def test_green_slots_exact():
    """PS 产物+fields+素材 → slots 11 键与 green 逐键相等(金额三面引用报价表)。"""
    ps = green_ctx()["products"]["price_sheet"]
    bl = _render(ps)
    assert bl["slots"] == green_ctx()["products"]["bid_letter"]["slots"]
    assert bl["extra_commitments"] == green_ctx()["products"]["bid_letter"]["extra_commitments"]


def test_amount_follows_price_sheet():
    """改 PS 总额→投标函金额随动(§2.1 硬约束:金额必须引用报价表结果)。"""
    ps = dict(green_ctx()["products"]["price_sheet"], detail_total=3000000, amount_cn="叁佰万元整")
    bl = _render(ps)
    assert bl["slots"]["total_amount_num"] == 3000000
    assert bl["slots"]["total_amount_cn"] == "叁佰万元整"


def test_material_absent_honest_blank():
    """素材缺位→bidder/legal_rep 置空(§2.1 不允许补写企业名称事实;下游 BL-004 FAIL 面)。"""
    ps = green_ctx()["products"]["price_sheet"]
    bl = render_bid_letter(_FIELDS, ps, {}, sign_date="2026-11-20")
    assert bl["slots"]["bidder_name"] == "" and bl["slots"]["legal_rep_name"] == ""


def test_text_zero_forbidden_hits_and_fixed_anchor():
    """渲染正文 6 桶禁用词零命中;含固定段原文(bl_fixed_similarity=1.0 面)+盖章/签字锚。"""
    bl = _render(green_ctx()["products"]["price_sheet"])
    hits = scan_text(bl["text"], words_for(*[
        "placeholder", "absolute", "redline", "vague", "price_vague", "empty_answer",
    ]))
    assert hits == [], hits
    assert FIXED_TEXT in bl["text"]
    assert bl["fixed_text"] == FIXED_TEXT
    assert bl["signature"] == {"seal_anchor": True, "sign_anchor": True}


def test_deposit_form_missing_honest_blank():
    ps = green_ctx()["products"]["price_sheet"]
    bl = render_bid_letter({**_FIELDS, "tender.deposit_forms": []}, ps, _MATERIAL, sign_date="2026-11-20")
    assert bl["slots"]["deposit_form"] == ""
    bl2 = render_bid_letter({k: v for k, v in _FIELDS.items() if k != "tender.deposit_required"}, ps, _MATERIAL, sign_date="2026-11-20")
    assert bl2["slots"]["deposit_amount"] == ""


def test_deterministic():
    ps = green_ctx()["products"]["price_sheet"]
    assert _render(ps) == _render(ps)
