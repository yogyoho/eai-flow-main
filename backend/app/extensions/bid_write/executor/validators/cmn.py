"""CMN 共享层校验器(批二十 M1,EAI-CUSTOM 2026-11-13)——导出级全文扫描,
技能级断言只做本技能范围(yaml meta.shared_layer)。本批落 SK-CMN-005(待补负
证据,SK-AI-009 delegates_to 单实现于此);001-004 随 Task 3 全量批补齐。"""

from __future__ import annotations

from app.extensions.bid_write.executor.models import Outcome
from app.extensions.bid_write.executor.validators import need, norm_text, register


@register("SK-CMN-005")
def _cmn005_pending_negative_evidence(ctx: dict, adef) -> Outcome:
    """expr:status=待补 项全部带 negative_evidence(检索章节/匹配键/最接近候选;
    沿审查端 MISSING 负证据口径——素材缺失不静默省略)。products 各切片的
    pending_items[] 逐项查;无待补项=诚实 PASS。"""
    products = need(ctx, "products")
    offenders: list[str] = []
    checked = 0
    for name, prod in products.items():
        if not isinstance(prod, dict):
            continue
        for i, item in enumerate(prod.get("pending_items") or []):
            if norm_text(item.get("status")) != "待补":
                continue
            checked += 1
            ev = item.get("negative_evidence")
            if not isinstance(ev, dict) or not any(norm_text(k) for k in ev.values()):
                offenders.append(f"{name}[{i}] {norm_text(item.get('item'))}")
    if offenders:
        return Outcome(
            status="FAIL",
            message="待补项缺负证据(须记录检索章节/匹配键/最接近候选): " + "; ".join(offenders[:8]),
        )
    return Outcome(status="PASS", message=f"待补项 {checked} 条全部带负证据" if checked else "无待补项(诚实零)")
