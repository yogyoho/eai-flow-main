"""Contract price analysis MCP server — read-only price query tools for the agent.

Exposes the already-processed ``cpa_`` data (populated by the OCR pipeline /
management module) as MCP tools so the chat agent can answer price questions
directly via function-calling — NO bash / sandbox needed.

Read-only by construction: only SELECTs. Price stats use only
``validation_status IN (ok, corrected)`` items (needs_review excluded, same
rule as cluster stats). Pipeline triggering is intentionally NOT exposed here
(it belongs in the management module where human verification + admin control
happen — see SKILL.md).

DB: the ``cpa_`` tables live in the extensions DB; resolve via
``get_extensions_config().database.url`` (override: ``CPA_QUERY_DB_URL``).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


async def _resolve_db_url() -> str:
    if os.environ.get("CPA_QUERY_DB_URL"):
        return os.environ["CPA_QUERY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(await _resolve_db_url(), pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _stats(prices: list[float]) -> dict[str, Any]:
    """Mean/median/min/max/count over a list of (already-filtered) prices."""
    if not prices:
        return {"count": 0}
    s = sorted(prices)
    n = len(s)
    median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {
        "count": n,
        "mean": round(sum(s) / n, 2),
        "median": round(median, 2),
        "min": round(s[0], 2),
        "max": round(s[-1], 2),
    }


# ── tools ──

TOOLS = [
    Tool(
        name="price_analysis_summary",
        description=("合同价格分析数据总览:返回已入库的合同数、分项货物数、聚类组数、待核验数、含税单价全量区间与均值。用于回答'一共有多少货物/合同/价格总体情况'类问题。只读,不触发任何流水线。"),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="query_goods_price",
        description=(
            "按货物或服务名称【模糊】查询含税单价统计:返回匹配的货物、每种的"
            "均价/中位数/价格区间(仅基于已校验数据)、校验状态分布、异常高价、来源合同号、"
            "样本明细。用于回答'X货物单价是多少/均价/区间/对比'。"
            "只读;若该货物多为待核验,会标注'仅供参考'。"
        ),
        inputSchema={
            "type": "object",
            "properties": {"goods_name": {"type": "string", "description": "货物/服务名称关键字,如 多孔砖墙、热镀锌无缝钢管"}},
            "required": ["goods_name"],
        },
    ),
    Tool(
        name="list_price_outliers",
        description="列出所有被标记为异常高价的分项货物(聚类层离群检测),含单价与来源合同。只读。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="list_needs_review_items",
        description=("列出待核验(needs_review)的分项——OCR 数字粘连/量级不确定的价格,未进入统计均值,需人工溯源核验。用于回答'哪些价格还不确定/需要复核'。只读。"),
        inputSchema={"type": "object", "properties": {}},
    ),
]


# ── handlers ──


async def _handle_summary(arguments: dict) -> list[TextContent]:
    from sqlalchemy import func, select

    from app.extensions.contract_price.models import CpaCluster, CpaDocument, CpaItem

    async def _q(session):
        docs = await session.scalar(select(func.count()).select_from(CpaDocument)) or 0
        items = await session.scalar(select(func.count()).select_from(CpaItem)) or 0
        clusters = await session.scalar(select(func.count()).select_from(CpaCluster)) or 0
        pending = await session.scalar(select(func.count()).select_from(select(CpaCluster).where(CpaCluster.status == "pending").subquery())) or 0
        nr = await session.scalar(select(func.count()).select_from(select(CpaItem).where(CpaItem.validation_status == "needs_review").subquery())) or 0
        lo = await session.scalar(select(func.min(CpaItem.unit_price)))
        hi = await session.scalar(select(func.max(CpaItem.unit_price)))
        avg = await session.scalar(select(func.avg(CpaItem.unit_price)))
        return dict(
            docs=int(docs),
            items=int(items),
            clusters=int(clusters),
            pending_clusters=int(pending),
            needs_review=int(nr),
            price_min=float(lo) if lo is not None else None,
            price_max=float(hi) if hi is not None else None,
            price_avg=round(float(avg), 2) if avg is not None else None,
        )

    data = await _run_in_db(_q)
    return _ok({"success": True, **data})


async def _handle_query_goods(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.contract_price.models import CpaItem

    name = arguments["goods_name"]

    async def _q(session):
        rows = (await session.execute(select(CpaItem).where(CpaItem.goods_name.ilike(f"%{name}%")).order_by(CpaItem.created_at))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    if not rows:
        return _ok({"success": True, "matched": 0, "message": f"未找到名称含「{name}」的分项货物。请先在合同价格分析管理页面分析相关合同。"})

    by_name: dict[str, list] = {}
    for it in rows:
        by_name.setdefault(it.goods_name, []).append(it)

    groups = []
    for gname, items in by_name.items():
        priced = [float(i.unit_price) for i in items if i.unit_price is not None and i.validation_status in ("ok", "corrected")]
        nr = sum(1 for i in items if i.validation_status == "needs_review")
        ok = sum(1 for i in items if i.validation_status == "ok")
        corr = sum(1 for i in items if i.validation_status == "corrected")
        outliers = [{"unit_price": float(i.unit_price), "contract": i.source_contract_no} for i in items if i.is_outlier and i.unit_price is not None]
        contracts = sorted({(i.source_contract_no or "(未关联)") for i in items})
        samples = [
            {
                "unit_price": float(i.unit_price) if i.unit_price is not None else None,
                "price_untaxed": float(i.price_untaxed) if i.price_untaxed is not None else None,
                "quantity": float(i.quantity) if i.quantity is not None else None,
                "unit": i.unit,
                "validation_status": i.validation_status,
            }
            for i in items[:5]
        ]
        groups.append(
            {
                "goods_name": gname,
                "item_count": len(items),
                "price_stats": _stats(priced),
                "validation": {"ok": ok, "needs_review": nr, "corrected": corr},
                "outliers": outliers,
                "source_contracts": contracts,
                "samples": samples,
                "confidence_note": "价格待人工溯源核验,仅供参考" if nr >= ok + corr else None,
            }
        )

    return _ok({"success": True, "keyword": name, "matched_items": len(rows), "matched_names": len(by_name), "groups": groups})


async def _handle_outliers(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.contract_price.models import CpaItem

    async def _q(session):
        rows = (await session.execute(select(CpaItem).where(CpaItem.is_outlier.is_(True)).order_by(CpaItem.unit_price.desc()))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    return _ok({"success": True, "count": len(rows), "outliers": [{"goods_name": r.goods_name, "unit_price": float(r.unit_price) if r.unit_price is not None else None, "source_contract_no": r.source_contract_no} for r in rows[:50]]})


async def _handle_needs_review(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.contract_price.models import CpaItem

    async def _q(session):
        rows = (await session.execute(select(CpaItem).where(CpaItem.validation_status == "needs_review"))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    return _ok(
        {
            "success": True,
            "count": len(rows),
            "needs_review": [{"goods_name": r.goods_name, "unit_price": float(r.unit_price) if r.unit_price is not None else None, "source_contract_no": r.source_contract_no, "source_page": r.source_page} for r in rows[:50]],
        }
    )


# ── server ──

server = Server("contract-price-analysis")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "price_analysis_summary": _handle_summary,
        "query_goods_price": _handle_query_goods,
        "list_price_outliers": _handle_outliers,
        "list_needs_review_items": _handle_needs_review,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments)
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
