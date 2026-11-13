"""SK-BL 投标函渲染(批二十 M1-f,EAI-CUSTOM 2026-11-13)——§2.1 骨架兑现:
模板段落 致→一、投标报价(大写+小写)→二、投标有效期→三、承诺→四、落款。
硬约束:①金额必须引用报价表结果(slots.total_amount_cn/num ← ps 产物);
②企业名称类事实只来自素材(material.bidder_profile),缺→"" 诚实缺件
(下游 BL-004 FAIL 面,不允许补写);③固定段原文内嵌 text(bl_fixed_similarity
=1.0 面);④deposit_forms 空表→"" 不猜。sign_date=人工 knob(缺→"" → BL-005
FAIL 面)。tender.purchaser_name/project_name/tender_no 走全量抽取路径(商务
子集外,缺→"" 诚实)。纯函数零 IO 零时钟。"""

from __future__ import annotations

FIXED_TEXT = "本投标函即为招标文件的组成部分,我方对函内全部承诺承担相应责任。"


def render_bid_letter(tender_fields: dict, price_sheet: dict, material: dict | None, *, sign_date: str = "", extra_commitments: list[dict] | None = None, letter_defaults: dict | None = None) -> dict:
    t = tender_fields or {}
    ps = price_sheet or {}
    profile = (material or {}).get("bidder_profile") or {}
    deposit_forms = t.get("tender.deposit_forms") or []
    purchaser = str(t.get("tender.purchaser_name") or "")
    project = str(t.get("tender.project_name") or "")
    tender_no = str(t.get("tender.tender_no") or "")
    # 批廿三 P1-β:policy.letter_defaults 兜底面——抽取缺席时配置值填槽+defaults_used
    # 标黄(D1 语义:默认值填充+标黄;SK-BL-003 对缺席 requirement 仍 CtxMissing
    # →ERROR 诚实,不因兜底变绿)。零 letter_defaults=现行为逐字节不变。
    defaults = letter_defaults or {}
    defaults_used: list[str] = []
    raw_valid = t.get("tender.required_validity_days")
    if raw_valid is not None:
        valid_days = raw_valid
    elif defaults.get("validity_days") is not None:
        valid_days = defaults["validity_days"]
        defaults_used.append("valid_days")
    else:
        valid_days = None
    raw_sign = str(sign_date or "")
    if raw_sign:
        sign = raw_sign
    elif defaults.get("sign_date"):
        sign = str(defaults["sign_date"])
        defaults_used.append("sign_date")
    else:
        sign = ""
    slots = {
        "tender_purchaser_name": purchaser,
        "project_name": project,
        "tender_no": tender_no,
        "total_amount_cn": str(ps.get("amount_cn") or ""),
        "total_amount_num": ps.get("detail_total"),
        "valid_days": valid_days,
        "deposit_amount": t.get("tender.deposit_required") if t.get("tender.deposit_required") is not None else "",
        "deposit_form": str(deposit_forms[0]) if deposit_forms else "",
        "bidder_name": str(profile.get("name") or ""),
        "legal_rep_name": str(profile.get("legal_rep") or ""),
        "sign_date": sign,
    }
    text = (
        f"致 {purchaser}:我方自愿参加{project}(招标编号:{tender_no})的投标。\n"
        f"一、投标报价:人民币大写{slots['total_amount_cn']}(小写:{slots['total_amount_num']}元)。\n"
        f"二、投标有效期:{slots['valid_days']}天(自开标之日起)。\n"
        f"三、承诺:按招标规定缴纳投标保证金{slots['deposit_amount']}元(形式:{slots['deposit_form']});"
        f"{FIXED_TEXT}\n"
        f"四、落款:{slots['bidder_name']}(法定代表人:{slots['legal_rep_name']})签署日期:{slots['sign_date']}。"
    )
    return {
        "slots": slots,
        "text": text,
        "fixed_text": FIXED_TEXT,
        "signature": {"seal_anchor": True, "sign_anchor": True},
        "extra_commitments": list(extra_commitments or []),
        "entity_refs": [],
        "defaults_used": defaults_used,
        "pending_items": [],
    }
