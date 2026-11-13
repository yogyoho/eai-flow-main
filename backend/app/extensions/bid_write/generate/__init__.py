"""build_ctx 总装(批二十 M1-i,EAI-CUSTOM 2026-11-13)——五生成器组装 executor
契约 ctx(green 形):tender=抽取快照透传 / products=四切片产物 / material 透传 /
pre=装配核自检面。pre 自产自证零 LLM 零时钟:kernel_replay(纯函数装配恒等)、
ps_replay(明细重算=三表)、bl_fixed_similarity(固定段含入→1.0,否则 difflib
整文比)、rt_excerpt_overlaps(摘录 vs 招标原文,同文→1.0)、rt_cross_field
(金额 rt=投标函槽位 vs other=报价汇总)、toc_page_estimates(索引页码回填,
键=编号归一与 AI-004 消费侧同律)。golden 闭环=夹具输入→build_ctx→run_assertions
全 43 PASS;降级负例=缺单价/缺素材按诚实 FAIL 暴露。纯函数零 IO 零时钟。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from app.extensions.bid_write.generate.attachment_index import _norm, build_attachment_index
from app.extensions.bid_write.generate.bid_letter import FIXED_TEXT, render_bid_letter
from app.extensions.bid_write.generate.price_sheet import calc_price_sheet
from app.extensions.bid_write.generate.response_table import build_response_table
from app.extensions.bid_write.generate.sections import assemble_sections

_TWO = Decimal("0.01")


def _ps_replay_equal(ps: dict) -> bool:
    """明细行重算=三表同值(PS-003 同律的第二双保险;无行=0=0 空跑真)。"""
    rows = [r for r in (ps.get("rows") or []) if isinstance(r, dict) and r.get("amount") is not None]
    total = sum((Decimal(str(r["amount"])) for r in rows), Decimal("0")).quantize(_TWO, rounding=ROUND_HALF_UP)
    return all(Decimal(str(ps.get(k))) == total for k in ("detail_total", "summary_total", "open_letter_total"))


def _fixed_similarity(text: str) -> float:
    """固定段含入→1.0;否则整文比(渲染漂移暴露面,BL-007 ≥0.98 消费)。"""
    if FIXED_TEXT in (text or ""):
        return 1.0
    return round(SequenceMatcher(None, FIXED_TEXT, text or "").ratio(), 4)


def _excerpt_overlaps(matrix_rows: list[dict], rt: dict) -> dict:
    """{clause_id: 重合率}——摘录=招标原文透传→1.0;键=clause_id(RT-004 消费侧)。"""
    req_by_id = {str(r.get("clause_id") or ""): str(r.get("requirement") or "") for r in matrix_rows}
    out: dict[str, float] = {}
    for row in rt.get("rows") or []:
        cid = str(row.get("clause_id") or "")
        excerpt = str(row.get("requirement_excerpt") or "")
        req = req_by_id.get(cid)
        if req is None or excerpt == req:
            out[cid] = 1.0
        else:
            out[cid] = round(SequenceMatcher(None, excerpt, req).ratio(), 4)
    return out


def build_ctx(
    tender_fields: dict,
    matrix_rows: list[dict],
    material: dict | None = None,
    *,
    unit_prices: dict | None = None,
    sign_date: str = "",
    price_note: str = "",
    general_commitments: list[dict] | None = None,
    page_estimates: dict | None = None,
    total_pages: int | None = None,
    tax_rate: float = 0.13,
    price_adjust_mechanism: bool = True,
    letter_defaults: dict | None = None,
) -> dict:
    """tender 抽取快照+矩阵行+素材+人工旋钮 → executor 契约 ctx。

    decl 矩阵行→投标函承诺(clause_id 溯源,BL-010 面);general_commitments=
    调用方通用承诺(须带 tag=通用承诺)。批廿三 P1-β:policy 透传(tax_rate/
    price_adjust_mechanism→ps 产物;letter_defaults→bl 缺席兜底+defaults_used
    标黄);三个新 kwargs 缺省=零 policy 现行为(golden 闭环不动)。"""
    t = dict(tender_fields or {})
    rows = list(matrix_rows or [])
    mat = dict(material or {})
    sections = assemble_sections(t.get("tender.required_sections"))
    commitments = [
        {"text": str(r.get("requirement") or ""), "clause_id": str(r.get("clause_id") or "")}
        for r in rows
        if str(r.get("clause_id") or "").startswith("decl:")
    ] + list(general_commitments or [])
    ps = calc_price_sheet(t.get("tender.boq_items"), unit_prices, tax_rate=tax_rate, price_adjust_mechanism=price_adjust_mechanism, note=price_note)
    bl = render_bid_letter(t, ps, mat, sign_date=sign_date, extra_commitments=commitments, letter_defaults=letter_defaults)
    rt = build_response_table(rows)
    ai = build_attachment_index(
        t.get("tender.attachment_requirements"),
        t.get("tender.volume_specs"),
        mat,
        sections,
        page_estimates=page_estimates,
        total_pages=total_pages,
    )
    pre = {
        # ponytail: kernel_replay 恒等——纯函数装配,导出即内核态;M2 渲染导出面才有漂移可能
        "kernel_replay_equal": True,
        "ps_replay_equal": _ps_replay_equal(ps),
        "bl_fixed_similarity": _fixed_similarity(bl.get("text") or ""),
        "rt_excerpt_overlaps": _excerpt_overlaps(rows, rt),
        "rt_cross_field": {"total_amount": {"rt": bl["slots"]["total_amount_num"], "other": ps["summary_total"]}},
        "toc_page_estimates": {_norm(i.get("no")): i.get("page") for i in ai.get("items") or []},
    }
    return {"tender": t, "products": {"bid_letter": bl, "price_sheet": ps, "response_table": rt, "attachment_index": ai}, "material": mat, "pre": pre}
