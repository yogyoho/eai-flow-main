"""RT 商务响应表校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——SK-RT-001..009 逐条
按注册表 expr 兑现(plan 契约表)。结论词汇=完全响应/正偏离/负偏离
(contracts.MATRIX_STRATEGIES 落地表);RT-008 偏离表述=执行器侧 marker 元组。"""

from __future__ import annotations

from decimal import Decimal

from app.extensions.bid_write.executor.models import CtxMissing, Outcome
from app.extensions.bid_write.executor.validators import (
    need,
    norm_text,
    opt,
    register,
    resolve_entity_refs,
)
from app.extensions.bid_write.executor.wordscan import hit_message, scan_text, words_for

_EMPTY_ANSWER_WORDS = words_for("empty_answer")
_PLACEHOLDER_WORDS = words_for("placeholder")
_RT_OVERLAP_MIN = Decimal("0.80")

# 结论=完全响应 时正文不得出现的偏离表述(RT-008;写作端新增,marker 面执行器自持)
_DEVIATION_MARKERS = ("无法满足", "不满足", "有异议", "不予响应", "难于满足", "负偏离")


def _rt_rows(products: dict) -> list[dict]:
    return [r for r in (opt(need(products, "response_table"), "rows") or []) if isinstance(r, dict)]


@register("SK-RT-001")
def _rt001_star_coverage(ctx: dict, adef) -> Outcome:
    """expr:response_matrix 所有 star=true 行均有响应行(★条款 100% 覆盖)。"""
    products = need(ctx, "products")
    rt = need(products, "response_table")
    star_ids = {norm_text(s) for s in (opt(rt, "matrix_star_clause_ids") or [])} - {""}
    row_ids = {norm_text(r.get("clause_id")) for r in _rt_rows(products)} - {""}
    uncovered = sorted(star_ids - row_ids)
    if uncovered:
        return Outcome(status="FAIL", level=adef.level, message=f"★条款未覆盖 {len(uncovered)}: {', '.join(uncovered)}")
    return Outcome(status="PASS", message=f"★条款 {len(star_ids)} 条全部有响应行")


@register("SK-RT-002")
def _rt002_star_no_negative(ctx: dict, adef) -> Outcome:
    """expr:不存在 star=true ∧ conclusion=负偏离 的行(★负偏离生成期即拦)。"""
    products = need(ctx, "products")
    offenders = [norm_text(r.get("clause_id")) or f"row[{i}]" for i, r in enumerate(_rt_rows(products)) if r.get("star") is True and norm_text(r.get("conclusion")) == "负偏离"]
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"★条款负偏离 {len(offenders)} 行(须改完全/正偏离+替代方案): {', '.join(offenders[:8])}")
    return Outcome(status="PASS", message="★条款零负偏离")


@register("SK-RT-003")
def _rt003_empty_answer(ctx: dict, adef) -> Outcome:
    """expr:响应文本无空应答命中(满足招标文件要求/符合招标文件要求/按招标文件
    执行/无异议=无参数化内容即 D0)。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    for r in _rt_rows(products):
        hits = scan_text(norm_text(opt(r, "response_text")), _EMPTY_ANSWER_WORDS)
        if hits:
            offenders.append(f"{norm_text(r.get('clause_id')) or 'row'}: {hit_message(hits)}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"空应答 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message="响应文本无空应答")


@register("SK-RT-004")
def _rt004_excerpt_overlap(ctx: dict, adef) -> Outcome:
    """expr:requirement_excerpt 与招标原文重合率 ≥ 0.80(重合率=装配核产出,
    执行器读 pre 值,deterministic=False);行有摘录但 pre 无值→CtxMissing
    (锚点缺失不得静默)。"""
    products = need(ctx, "products")
    overlaps = need(need(ctx, "pre"), "rt_excerpt_overlaps")
    offenders: list[str] = []
    checked = 0
    rows = _rt_rows(products)
    for i, r in enumerate(rows):
        if not norm_text(opt(r, "requirement_excerpt")):
            continue
        cid = norm_text(r.get("clause_id"))
        key = cid or f"row[{i}]"
        if cid not in overlaps:
            raise CtxMissing(f"pre.rt_excerpt_overlaps[{cid or i}]")
        v = Decimal(str(overlaps[cid]))
        checked += 1
        if v < _RT_OVERLAP_MIN:
            offenders.append(f"{key}: {v:.2f} < {_RT_OVERLAP_MIN}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, deterministic=False, message=f"摘录重合率不足 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", deterministic=False, message=f"摘录重合率 {checked} 行全部 ≥ {_RT_OVERLAP_MIN}" if checked else "无摘录行(诚实零)")


@register("SK-RT-005")
def _rt005_deviation_loop(ctx: dict, adef) -> Outcome:
    """expr:每条负偏离含偏离原因+替代方案(闭环;缺任一=FAIL)。"""
    products = need(ctx, "products")
    rows = _rt_rows(products)
    offenders: list[str] = []
    for r in rows:
        if norm_text(r.get("conclusion")) != "负偏离":
            continue
        cid = norm_text(r.get("clause_id")) or "row"
        missing = [f for f in ("deviation_reason", "replacement_plan") if not norm_text(opt(r, f))]
        if missing:
            offenders.append(f"{cid} 缺 {('、'.join(missing))}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"负偏离未闭环 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    if _has_negative(rows):
        return Outcome(status="PASS", message="负偏离均带原因+替代方案")
    return Outcome(status="PASS", message="无负偏离(诚实零)")


def _has_negative(rows: list[dict]) -> bool:
    return any(norm_text(r.get("conclusion")) == "负偏离" for r in rows)


@register("SK-RT-006")
def _rt006_cross_field(ctx: dict, adef) -> Outcome:
    """expr:响应值与正文/报价表同字段一致(跨字段一致性=装配核产出 rt_cross_field
    逐字段 {rt, other} 相等;执行器纯数据比对,deterministic=True)。"""
    cross = need(need(ctx, "pre"), "rt_cross_field")
    bad: list[str] = []
    for field in sorted(cross):
        pair = cross[field]
        if not isinstance(pair, dict) or "rt" not in pair or "other" not in pair:
            raise CtxMissing(f"pre.rt_cross_field[{field}].rt/other")
        if Decimal(str(pair["rt"])) != Decimal(str(pair["other"])):
            bad.append(f"{field}: 响应表 {pair['rt']} ≠ 正文 {pair['other']}")
    if bad:
        return Outcome(status="FAIL", level=adef.level, message=f"跨字段不一致 {len(bad)} 处: {'; '.join(bad[:8])}")
    return Outcome(status="PASS", message=f"跨字段一致 {len(cross)} 项")


@register("SK-RT-007")
def _rt007_evidence(ctx: dict, adef) -> Outcome:
    """expr:每行 evidence_refs 非空且实体存在(M0 素材库缺位→全部 D0 待补,
    诚实伪零);行级 entity_refs 可解析到 material.entities。"""
    products = need(ctx, "products")
    rows = _rt_rows(products)
    entities = opt(opt(ctx, "material") or {}, "entities")
    if entities is None:
        return Outcome(status="FAIL", level=adef.level, message=f"素材库缺位(material.entities 缺失),{len(rows)} 行全部待补(诚实伪零)")
    offenders: list[str] = []
    for i, r in enumerate(rows):
        cid = norm_text(r.get("clause_id")) or f"row[{i}]"
        refs = r.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            offenders.append(f"{cid}: evidence_refs 空")
            continue
        unresolved, _total = resolve_entity_refs(opt(r, "entity_refs") or [], entities or {})
        if unresolved:
            offenders.append(f"{cid}: 实体缺件 {', '.join(unresolved[:4])}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"证据缺面 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message=f"{len(rows)} 行证据齐备且实体可解析")


@register("SK-RT-008")
def _rt008_conclusion_match(ctx: dict, adef) -> Outcome:
    """expr:结论=完全响应时正文无偏离表述(marker=执行器侧元组,冲突以招标要求
    为基准回退并写入报告——执行器面只判 FAIL 留待人工)。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    for r in _rt_rows(products):
        if norm_text(r.get("conclusion")) != "完全响应":
            continue
        text = norm_text(opt(r, "response_text"))
        markers = [m for m in _DEVIATION_MARKERS if m in text]
        if markers:
            offenders.append(f"{norm_text(r.get('clause_id')) or 'row'}: {'、'.join(markers)}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"「完全响应」行含偏离表述 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message="完全响应行正文无偏离表述")


@register("SK-RT-009")
def _rt009_placeholder(ctx: dict, adef) -> Outcome:
    """expr:响应文本占位符扫描 0 命中(待补充/待定/TBD/XX)。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    for r in _rt_rows(products):
        hits = scan_text(norm_text(opt(r, "response_text")), _PLACEHOLDER_WORDS)
        if hits:
            offenders.append(f"{norm_text(r.get('clause_id')) or 'row'}: {hit_message(hits)}")
    if offenders:
        return Outcome(status="FAIL", level=adef.level, message=f"响应文本占位符 {len(offenders)} 行: {'; '.join(offenders[:8])}")
    return Outcome(status="PASS", message="响应文本无占位符")
