"""BL 投标函校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——SK-BL-001..010 逐条按
注册表 expr 兑现(plan 契约表)。BL-001 11 槽位=expr 点名(「12 个」第 12 无 repo
真源,挂账 spec F4 模板落地时锁);BL-006 五类禁用词=absolute/redline/vague/
placeholder/price_vague(空应答属 RT 面 RT-003)。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.extensions.bid_write.executor.amount_cn import cn_to_num, num_to_cn
from app.extensions.bid_write.executor.models import Outcome
from app.extensions.bid_write.executor.validators import (
    need,
    norm_text,
    opt,
    register,
    resolve_entity_refs,
)
from app.extensions.bid_write.executor.wordscan import hit_message, scan_text, static_level, words_for

# BL-001:expr 点名 11 槽位(section_no 可选不计;第 12 槽位挂账 spec F4)
REQUIRED_LETTER_SLOTS = (
    "tender_purchaser_name",
    "project_name",
    "tender_no",
    "total_amount_cn",
    "total_amount_num",
    "valid_days",
    "deposit_amount",
    "deposit_form",
    "bidder_name",
    "legal_rep_name",
    "sign_date",
)

_BL_WORDS = words_for("absolute", "redline", "vague", "placeholder", "price_vague")


@register("SK-BL-001")
def _bl001_slots(ctx: dict, adef) -> Outcome:
    """expr:必填槽位全部非空(值非 None 且 strip 非空串)。"""
    products = need(ctx, "products")
    slots = need(need(products, "bid_letter"), "slots")
    empty = [k for k in REQUIRED_LETTER_SLOTS if not norm_text(slots.get(k))]
    if empty:
        return Outcome(status="FAIL", level=adef.level, message=f"必填槽位空 {len(empty)} 项: {', '.join(empty)}")
    return Outcome(status="PASS", message=f"必填槽位 {len(REQUIRED_LETTER_SLOTS)} 项全部非空")


@register("SK-BL-002")
def _bl002_amount(ctx: dict, adef) -> Outcome:
    """expr:大写(小写)双向转换相等,且等于 price_sheet 产出的 total_amount
    (投标函金额只读引用;非 canonical 大写=FAIL,固定函数见 executor/amount_cn)。"""
    products = need(ctx, "products")
    slots = need(need(products, "bid_letter"), "slots")
    cn = norm_text(need(slots, "total_amount_cn"))
    num = need(slots, "total_amount_num")
    detail = need(need(products, "price_sheet"), "detail_total")
    try:
        parsed = cn_to_num(cn)
    except ValueError as exc:
        return Outcome(status="FAIL", level=adef.level, message=f"大写金额非 canonical: {exc}")
    num_d = Decimal(str(num))
    detail_d = Decimal(str(detail))
    bad = []
    if parsed != num_d:
        bad.append(f"cn_to_num({cn})={parsed} ≠ 小写 {num_d}")
    if num_to_cn(num_d) != cn:
        bad.append(f"num_to_cn({num_d})={num_to_cn(num_d)} ≠ 大写「{cn}」")
    if num_d != detail_d:
        bad.append(f"投标函 {num_d} ≠ price_sheet.total {detail_d}")
    if bad:
        return Outcome(status="FAIL", level=adef.level, message="金额不一致: " + "; ".join(bad))
    return Outcome(status="PASS", message=f"金额三面一致({cn} = {num_d})")


@register("SK-BL-003")
def _bl003_validity(ctx: dict, adef) -> Outcome:
    """expr:valid_days ≥ tender.required_validity_days(操作数缺→CtxMissing)。"""
    products = need(ctx, "products")
    slots = need(need(products, "bid_letter"), "slots")
    days = need(slots, "valid_days")
    required = need(need(ctx, "tender"), "tender.required_validity_days")
    try:
        d, r = int(days), int(required)
    except (TypeError, ValueError):
        return Outcome(status="FAIL", level=adef.level, message=f"有效期非法数值: {days!r} / {required!r}")
    if d < r:
        return Outcome(status="FAIL", level=adef.level, message=f"投标有效期 {d} 天 < 要求 {r} 天")
    return Outcome(status="PASS", message=f"投标有效期 {d} 天 ≥ 要求 {r} 天")


@register("SK-BL-004")
def _bl004_bidder(ctx: dict, adef) -> Outcome:
    """expr:投标人名称与 material.bidder_profile 完全一致(素材缺位=缺件 FAIL,
    禁止模型补写;opt 不用 CtxMissing——缺件是业务判定面非上下文缺陷)。"""
    products = need(ctx, "products")
    name = norm_text(need(need(products, "bid_letter"), "slots").get("bidder_name"))
    profile = opt(opt(ctx, "material") or {}, "bidder_profile") or {}
    expected = norm_text(profile.get("name"))
    if not expected:
        return Outcome(status="FAIL", level=adef.level, message="素材缺件:material.bidder_profile.name 缺失,主体一致性无法核验")
    if name != expected:
        return Outcome(status="FAIL", level=adef.level, message=f"主体不一致:投标函「{name}」≠ 营业执照「{expected}」")
    return Outcome(status="PASS", message=f"主体一致({expected})")


@register("SK-BL-005")
def _bl005_sign_date(ctx: dict, adef) -> Outcome:
    """expr:sign_date ≤ tender.bid_deadline(时序校验;格式非法=FAIL 非 ERROR)。"""
    products = need(ctx, "products")
    sign_raw = norm_text(need(need(products, "bid_letter"), "slots").get("sign_date"))
    deadline_raw = norm_text(need(need(ctx, "tender"), "tender.bid_deadline"))
    try:
        sign = datetime.fromisoformat(sign_raw)
    except ValueError:
        return Outcome(status="FAIL", level=adef.level, message=f"签署日期格式非法: {sign_raw!r}")
    try:
        deadline = datetime.fromisoformat(deadline_raw)
    except ValueError:
        return Outcome(status="FAIL", level=adef.level, message=f"截止时间格式非法: {deadline_raw!r}")
    if sign > deadline:
        return Outcome(status="FAIL", level=adef.level, message=f"签署日期 {sign_raw} 晚于投标截止 {deadline_raw}")
    return Outcome(status="PASS", message=f"签署日期 {sign_raw} ≤ 截止 {deadline_raw}")


@register("SK-BL-006")
def _bl006_forbidden(ctx: dict, adef) -> Outcome:
    """expr:投标函正文五类禁用词扫描 0 命中;final=命中词静态级 max(红线/占位符
    词命中升 D0 阻断,词级升级)。requirement 类引用面归 CMN(排除在外)。"""
    products = need(ctx, "products")
    text = norm_text(opt(need(products, "bid_letter"), "text"))
    hits = scan_text(text, _BL_WORDS)
    if hits:
        worst = max(static_level(w) for w in hits)
        return Outcome(status="FAIL", level=worst, message=f"投标函措辞命中: {hit_message(hits)}")
    return Outcome(status="PASS", message="投标函无禁用词")


@register("SK-BL-007")
def _bl007_fixed_similarity(ctx: dict, adef) -> Outcome:
    """expr:固定段相似度 ≥ 0.98(相似度=生成核产出,执行器只读 pre 值——
    非执行器可复算面,deterministic=False)。"""
    sim = need(need(ctx, "pre"), "bl_fixed_similarity")
    try:
        v = float(sim)
    except (TypeError, ValueError):
        return Outcome(status="FAIL", level=adef.level, message=f"相似度非法: {sim!r}")
    if v < 0.98:
        return Outcome(status="FAIL", level=adef.level, deterministic=False, message=f"固定段相似度 {v:.4f} < 0.98(法律表述漂移)")
    return Outcome(status="PASS", deterministic=False, message=f"固定段相似度 {v:.4f} ≥ 0.98")


@register("SK-BL-008")
def _bl008_signature(ctx: dict, adef) -> Outcome:
    """expr:盖章位+签字位锚点均存在。"""
    products = need(ctx, "products")
    sig = opt(need(products, "bid_letter"), "signature") or {}
    missing = [k for k in ("seal_anchor", "sign_anchor") if sig.get(k) is not True]
    if missing:
        return Outcome(status="FAIL", level=adef.level, message=f"签章锚点缺失: {', '.join(missing)}")
    return Outcome(status="PASS", message="盖章/签字锚点均存在")


@register("SK-BL-009")
def _bl009_entity_refs(ctx: dict, adef) -> Outcome:
    """expr:投标函 ref(entity_id) 槽位全部可解析到素材实体(M0 素材库缺位→
    一律 D0 缺件,诚实不编造)。全切片引用面归 CMN-003,本条只查投标函。"""
    products = need(ctx, "products")
    refs = opt(need(products, "bid_letter"), "entity_refs") or []
    entities = opt(opt(ctx, "material") or {}, "entities") or {}
    unresolved, total = resolve_entity_refs(refs, entities)
    if unresolved:
        return Outcome(status="FAIL", level=adef.level, message=f"投标函实体引用缺件 {len(unresolved)}/{total}: {', '.join(unresolved[:8])}")
    return Outcome(status="PASS", message=f"投标函实体引用 {total} 条全部可解析" if total else "投标函无实体引用(诚实零)")


@register("SK-BL-010")
def _bl010_commitments(ctx: dict, adef) -> Outcome:
    """expr:extra_commitments 每条含 clause_id 溯源或显式 tag「通用承诺」。"""
    products = need(ctx, "products")
    items = opt(need(products, "bid_letter"), "extra_commitments") or []
    offenders = []
    for i, c in enumerate(items):
        if not isinstance(c, dict):
            offenders.append(f"[{i}] 非对象")
            continue
        if not norm_text(c.get("clause_id")) and norm_text(c.get("tag")) != "通用承诺":
            offenders.append(f"[{i}] {norm_text(c.get('text'))[:24]}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"承诺缺溯源 {len(offenders)} 条: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message=f"承诺 {len(items)} 条全部可溯源" if items else "无附加承诺(诚实零)")
