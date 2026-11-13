"""attachment_index 附件索引校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——
SK-AI-001..008 逐条兑现 yaml expr(SK-AI-009 为 delegates_to SK-CMN-005 的登记
条,不注册函数,runner 镜像)。素材六类实体 P1 落地前,entity/待补面按 M0 诚实
缺件口径(不静默省略)。"""

from __future__ import annotations

import re

from app.extensions.bid_write.executor.models import Outcome
from app.extensions.bid_write.executor.validators import need, norm_text, register

# 正文附件引用(见附件X;阿拉伯/中文序号)
_SEE_REF = re.compile(r"见附件([0-9A-Za-z]{1,8}|[一二三四五六七八九十]{1,3})")

_UNKNOWN_FINGERPRINTS = ("", "unknown_type")


def _index(ctx: dict) -> dict:
    return need(need(ctx, "products"), "attachment_index")


def _items(ctx: dict) -> list:
    return need(_index(ctx), "items")


@register("SK-AI-001")
def _ai001_no_unique(ctx: dict, adef) -> Outcome:
    """expr:no 去重后数量相等(编号规则生成,norm() 后可与 tender 对齐)。"""
    items = _items(ctx)
    nos = [norm_text(i.get("no")) for i in items]
    empty = sum(1 for n in nos if not n)
    dup = sorted({n for n in nos if n and nos.count(n) > 1})
    if empty or dup:
        msg = []
        if empty:
            msg.append(f"{empty} 行编号为空")
        if dup:
            msg.append("编号重复: " + ", ".join(dup))
        return Outcome(status="FAIL", message="; ".join(msg))
    return Outcome(status="PASS", message=f"{len(nos)} 行编号唯一")


@register("SK-AI-002")
def _ai002_requirement_aligned(ctx: dict, adef) -> Outcome:
    """expr:tender.attachment_requirements 每项均有索引项或标待补(要求集低置信
    →D0 索引不可生成)。匹配键=no 优先、名称兜底;待补行即覆盖(诚实缺件)。"""
    items = _items(ctx)
    reqs = need(need(ctx, "tender"), "tender.attachment_requirements")
    covered_nos = {norm_text(i.get("no")) for i in items}
    covered_names = {norm_text(i.get("name")) for i in items}
    missing: list[str] = []
    for r in reqs:
        no, nm = norm_text(r.get("no")), norm_text(r.get("name"))
        if (no and no in covered_nos) or (nm and nm in covered_names):
            continue
        missing.append(f"{no or '?'} {nm}")
    if missing:
        head = "; ".join(missing[:8])
        more = f" 等 {len(missing)} 项" if len(missing) > 8 else ""
        return Outcome(status="FAIL", message="要求缺索引项(或未标待补): " + head + more)
    return Outcome(status="PASS", message=f"要求 {len(reqs)} 项全覆盖(含待补行)")


@register("SK-AI-003")
def _ai003_no_dangling_ref(ctx: dict, adef) -> Outcome:
    """expr:正文「见附件X」全部可解析到索引项。"""
    items = _items(ctx)
    body = need(_index(ctx), "body_text")
    nos = {norm_text(i.get("no")) for i in items if norm_text(i.get("no"))}
    dangling = sorted({m.group(0) for m in _SEE_REF.finditer(str(body)) if m.group(1) not in nos})
    if dangling:
        return Outcome(status="FAIL", message="正文附件引用不可解析: " + ", ".join(dangling))
    return Outcome(status="PASS", message="正文附件引用全可解析")


@register("SK-AI-004")
def _ai004_page_valid(ctx: dict, adef) -> Outcome:
    """expr:page ≤ 总页数且与目录偏差 ≤ 1(page_offset 校正面;偏移>5 页降置信
    标注「页码待核对」)。目录估值 pre.toc_page_estimates 缺位→仅校验页≤总页。"""
    items = _items(ctx)
    total = need(_index(ctx), "total_pages")
    est = (ctx.get("pre") or {}).get("toc_page_estimates")
    bad_page: list[str] = []
    dev_bad: list[str] = []
    dev_far: list[str] = []
    for i in items:
        label = norm_text(i.get("no")) or norm_text(i.get("name")) or "?"
        page = i.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1 or page > total:
            bad_page.append(label)
            continue
        if isinstance(est, dict):
            e = est.get(norm_text(i.get("no")))
            if isinstance(e, int) and not isinstance(e, bool):
                dev = abs(page - e)
                if dev > 5:
                    dev_far.append(f"{label}(页 {page} vs 估值 {e})")
                elif dev > 1:
                    dev_bad.append(f"{label}(页 {page} vs 估值 {e})")
    if bad_page or dev_bad or dev_far:
        msg = []
        if bad_page:
            msg.append("页码无效(超总页/非法): " + ", ".join(bad_page))
        if dev_bad:
            msg.append("与目录偏差 >1: " + ", ".join(dev_bad))
        if dev_far:
            msg.append("页码待核对(偏移>5 页): " + ", ".join(dev_far))
        return Outcome(status="FAIL", message="; ".join(msg))
    note = None if isinstance(est, dict) else "目录估值未注入,仅校验页≤总页"
    return Outcome(status="PASS", message=f"{len(items)} 行页码有效", note=note)


@register("SK-AI-005")
def _ai005_copies_met(ctx: dict, adef) -> Outcome:
    """expr:copies ≥ tender.volume_specs 要求份数([{name,min_copies}],契约真源
    extract.py L126;按分册名称匹配)。"""
    items = _items(ctx)
    specs = need(need(ctx, "tender"), "tender.volume_specs")
    by_name: dict[str, dict] = {}
    for i in items:
        nm = norm_text(i.get("name"))
        if nm and nm not in by_name:
            by_name[nm] = i
    bad: list[str] = []
    for s in specs:
        nm = norm_text(s.get("name"))
        req = s.get("min_copies")
        got = by_name.get(nm, {}).get("copies")
        if not isinstance(got, (int, float)) or not isinstance(req, (int, float)) or got < req:
            bad.append(f"{nm or '?'}(要求 {req},实际 {got})")
    if bad:
        return Outcome(status="FAIL", message="份数未达标: " + "; ".join(bad[:8]))
    return Outcome(status="PASS", message=f"份数达标 {len(specs)} 册")


@register("SK-AI-006")
def _ai006_type_known(ctx: dict, adef) -> Outcome:
    """expr:type_fingerprint ≠ unknown_type(指纹字典批十九已外置;未识别→人工
    指定后重跑)。"""
    items = _items(ctx)
    unknown = [
        norm_text(i.get("no")) or norm_text(i.get("name")) or "?"
        for i in items
        if norm_text(i.get("type_fingerprint")) in _UNKNOWN_FINGERPRINTS
    ]
    if unknown:
        return Outcome(status="FAIL", message="附件类型未识别(unknown_type/缺失,人工指定后重跑): " + ", ".join(unknown))
    return Outcome(status="PASS", message=f"{len(items)} 行类型可识别")


@register("SK-AI-007")
def _ai007_no_orphan(ctx: dict, adef) -> Outcome:
    """expr:索引项均能定位到实际内容页(内容锚点 source 非空)。"""
    items = _items(ctx)
    orphan = [
        norm_text(i.get("no")) or norm_text(i.get("name")) or "?"
        for i in items
        if not norm_text(i.get("source"))
    ]
    if orphan:
        return Outcome(status="FAIL", message="索引项无内容锚点: " + ", ".join(orphan))
    return Outcome(status="PASS", message=f"{len(items)} 行均有内容锚点")


@register("SK-AI-008")
def _ai008_toc_consistent(ctx: dict, adef) -> Outcome:
    """expr:目录标题与正文标题逐条匹配(写作端新增)。"""
    idx = _index(ctx)
    toc = [norm_text(x) for x in need(idx, "toc_titles")]
    body = [norm_text(x) for x in need(idx, "body_headings")]
    if toc != body:
        first = next((k for k in range(min(len(toc), len(body))) if toc[k] != body[k]), min(len(toc), len(body)))
        return Outcome(
            status="FAIL",
            message=f"目录/正文标题失配(第 {first + 1} 项起;目录 {len(toc)} 条 vs 正文 {len(body)} 条)",
        )
    return Outcome(status="PASS", message=f"目录/正文 {len(toc)} 条逐条一致")
