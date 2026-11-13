"""CMN 共享层校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——导出级全文扫描,
技能级断言只做本技能范围(yaml meta.shared_layer)。CMN-001 占位符/未闭合插值
(D0)、CMN-002 绝对化+红线词(D1/D0 按词静态级)、CMN-003 实体引用可解析(D0)、
CMN-004 内核回放一致(D1)、CMN-005 待补负证据(SK-AI-009 delegates_to 单实现)。
扫描面=五切片正文(bid_letter.text / price_sheet.note / response rows'
response_text / attachment body_text+items[].name),**排除 requirement_excerpt**
(引用招标原文非我方表述)。"""

from __future__ import annotations

import re

from app.extensions.bid_write.executor.models import Outcome
from app.extensions.bid_write.executor.validators import need, opt, register, resolve_entity_refs
from app.extensions.bid_write.executor.wordscan import (
    hit_message,
    scan_text,
    static_level,
    words_for,
)

_PLACEHOLDER_WORDS = words_for("placeholder")
_TONE_WORDS = words_for("absolute", "redline")
_UNCLOSED = re.compile(r"\{\{(?:calc|ref)\(")


def _scan_texts(products: dict) -> list[tuple[str, str]]:
    """(标签, 文本) 全文扫描面;切片缺位=贡献零文本(整 products 缺失由 need 拦)。"""
    out: list[tuple[str, str]] = []
    bl = products.get("bid_letter") or {}
    if bl.get("text"):
        out.append(("bid_letter.text", str(bl["text"])))
    ps = products.get("price_sheet") or {}
    if ps.get("note"):
        out.append(("price_sheet.note", str(ps["note"])))
    rt = products.get("response_table") or {}
    for i, row in enumerate(rt.get("rows") or []):
        if isinstance(row, dict) and row.get("response_text"):
            cid = row.get("clause_id") or str(i)
            out.append((f"response_table[{cid}].response_text", str(row["response_text"])))
    ai = products.get("attachment_index") or {}
    if ai.get("body_text"):
        out.append(("attachment_index.body_text", str(ai["body_text"])))
    for i, item in enumerate(ai.get("items") or []):
        if isinstance(item, dict) and item.get("name"):
            out.append((f"attachment_index.items[{i}].name", str(item["name"])))
    return out


def _word_hits(products: dict, words: frozenset[str]) -> list[tuple[str, str]]:
    """全文扫描命中 [(标签, 词)];文本序遍历,词内字典序(scan_text 已排序)。"""
    hits: list[tuple[str, str]] = []
    for label, text in _scan_texts(products):
        for w in scan_text(text, words):
            hits.append((label, w))
    return hits


@register("SK-CMN-001")
def _cmn001_placeholder(ctx: dict, adef) -> Outcome:
    """expr:全文无占位符词(待补充/待定/TBD/XX)且无未闭合 {{calc(/{{ref( 插值;
    正文命中即 D0(渲染出去就是废页)。requirement_excerpt 不扫(招标原文)。"""
    products = need(ctx, "products")
    hits = _word_hits(products, _PLACEHOLDER_WORDS)
    unclosed: list[str] = []
    for label, text in _scan_texts(products):
        for m in _UNCLOSED.finditer(text):
            if "}}" not in text[m.start() :]:
                unclosed.append(f"{label}@{m.start()}")
                break  # 每文本报一次即可
    if hits or unclosed:
        msg = "占位符命中: " + hit_message([w for _, w in hits]) if hits else ""
        if unclosed:
            msg = (msg + "; " if msg else "") + "未闭合插值: " + ", ".join(unclosed[:5])
        return Outcome(status="FAIL", level=adef.level, message=msg)
    return Outcome(status="PASS", message="全文无占位符/未闭合插值")


@register("SK-CMN-002")
def _cmn002_tone(ctx: dict, adef) -> Outcome:
    """expr:全文无绝对化(无条件/绝不/无限期/终身,D1)与红线词(包过/保证中标/
    内部渠道/围标/串标,D0);final=命中词静态级最重者(词级升级,D0 即阻断)。"""
    products = need(ctx, "products")
    hits = _word_hits(products, _TONE_WORDS)
    if hits:
        worst = max(static_level(w) for _, w in hits)
        detail = "; ".join(f"{lab}: {hit_message([w])}" for lab, w in hits[:8])
        return Outcome(status="FAIL", level=worst, message=f"措辞命中: {detail}")
    return Outcome(status="PASS", message="全文无绝对化/红线词")


@register("SK-CMN-003")
def _cmn003_entity_refs(ctx: dict, adef) -> Outcome:
    """expr:各切片 entity_refs 全部可解析于 material.entities;无引用=诚实 PASS;
    素材缺位+存在引用=缺件 D0 FAIL(诚实伪零同律,不静默)。"""
    products = need(ctx, "products")
    refs: list[str] = []
    for prod in products.values():
        if isinstance(prod, dict):
            for r in prod.get("entity_refs") or []:
                refs.append(str(r))
    if not refs:
        return Outcome(status="PASS", message="无实体引用(诚实零)")
    material = opt(ctx, "material")
    entities = (material or {}).get("entities") or {}
    unresolved, total = resolve_entity_refs(refs, entities)
    if unresolved:
        return Outcome(
            status="FAIL",
            level=adef.level,
            message=f"实体引用缺件 {len(unresolved)}/{total}: {', '.join(unresolved[:8])}",
        )
    return Outcome(status="PASS", message=f"实体引用 {total} 条全部可解析")


@register("SK-CMN-004")
def _cmn004_kernel_replay(ctx: dict, adef) -> Outcome:
    """expr:pre.kernel_replay_equal=True(导出产物与内核态回放一致);价格表无行
    =空跑诚实 PASS(注记);False=渲染漂移 D0 FAIL(确定性核验)。"""
    pre = need(ctx, "pre")
    equal = need(pre, "kernel_replay_equal")
    products = need(ctx, "products")
    ps = opt(products, "price_sheet") or {}
    if not ps.get("rows"):
        return Outcome(status="PASS", note="价格表无行,回放核验空跑(诚实零)")
    if equal is not True:
        return Outcome(status="FAIL", level=adef.level, message="内核回放不一致(kernel_replay_equal=False)")
    return Outcome(status="PASS", message="内核回放一致")


@register("SK-CMN-005")
def _cmn005_pending_negative_evidence(ctx: dict, adef) -> Outcome:
    """expr:status=待补 项全部带 negative_evidence(检索章节/匹配键/最接近候选;
    沿审查端 MISSING 负证据口径——素材缺失不静默省略)。products 各切片的
    pending_items[] 逐项查;无待补项=诚实 PASS。SK-AI-009 delegates_to 本条。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    checked = 0
    for name, prod in products.items():
        if not isinstance(prod, dict):
            continue
        for i, item in enumerate(prod.get("pending_items") or []):
            if not isinstance(item, dict) or str(item.get("status") or "").strip() != "待补":
                continue
            checked += 1
            ev = item.get("negative_evidence")
            if not isinstance(ev, dict) or not any(str(v or "").strip() for v in ev.values()):
                offenders.append(f"{name}[{i}] {str(item.get('item') or '').strip()}")
    if offenders:
        return Outcome(
            status="FAIL",
            message="待补项缺负证据(须记录检索章节/匹配键/最接近候选): " + "; ".join(offenders[:8]),
        )
    return Outcome(status="PASS", message=f"待补项 {checked} 条全部带负证据" if checked else "无待补项(诚实零)")
