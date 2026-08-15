# EAI-CUSTOM: forked from contract_price/mcp.py。
# 与 contract_price 的差异:5 工具(增 compare_part_price_by_customer 跨客户比价 +
# customer_parts_contracts 客户明细);字段 part_name(非 goods_name);客户维度分组。
"""Spare-parts price analysis MCP server — read-only price query tools for the agent。

把已处理的 ``csp_`` 数据(由 OCR 管线 / 管理模块填充)暴露为 MCP 工具,使对话 agent 能
直接经函数调用回答备件价格问题——无需 bash / sandbox。

只读:仅 SELECT。价格统计只用 ``validation_status IN (ok, corrected)`` 的项(needs_review
排除,与聚类统计同规则)。管线触发不在此暴露(属管理模块,需人工核验 + 管理员控制,见
SKILL.md)。客户维度(D3):compare_part_price_by_customer 是 ④ 特色——同备件跨客户比价。

DB:csp_ 表在扩展库;经 ``CSP_QUERY_DB_URL`` 解析(stdio env 白名单,bug-1162)。
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
    if os.environ.get("CSP_QUERY_DB_URL"):
        return os.environ["CSP_QUERY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine。"""
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
    """Mean/median/min/max/count over a list of (already-filtered) prices。"""
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


async def _resolve_customer_id(session, customer_name: str):
    """脏客户名 → customer_id(命中 canonical 或 alias);返回 (id, canonical_name, pending?)。

    ponytail: 全量扫 csp_customers 内存匹配——客户数 N 极小。与 normalizer.resolve_customer
    同策略,但只读(不新建 pending;查询时未命中返回 None,调用方提示"未认领")。
    """
    from sqlalchemy import select

    from app.extensions.spare_parts.models import CspCustomer

    name = customer_name.strip()
    rows = (await session.execute(select(CspCustomer))).scalars().all()
    for c in rows:
        if c.canonical_name == name:
            return c.id, c.canonical_name, (c.status == "pending")
        if name in (c.aliases or []):
            return c.id, c.canonical_name, (c.status == "pending")
    return None, None, False


# ── tools ──

TOOLS = [
    Tool(
        name="spare_part_summary",
        description=("备件价格分析数据总览:返回已入库的合同数、备件分项数、聚类组数、客户数、待核验数、含税单价全量区间与均值。用于回答'一共有多少备件/合同/客户/价格总体情况'类问题。只读,不触发任何流水线。"),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="query_part_price",
        description=(
            "按备件名称【模糊】查询含税单价统计:返回匹配的备件、每种的均价/中位数/价格区间(仅基于已校验数据)、校验状态分布、异常高价、来源合同号、样本明细。用于回答'X备件单价是多少/均价/区间'。只读;若该备件多为待核验,会标注'仅供参考'。"
        ),
        inputSchema={
            "type": "object",
            "properties": {"part_name": {"type": "string", "description": "备件名称关键字,如 闸阀、液压支架、DN100 无缝钢管"}},
            "required": ["part_name"],
        },
    ),
    Tool(
        name="compare_part_price_by_customer",
        description=(
            "【④ 特色】按备件名称【模糊】查询,并按**客户/采购方**分组对比同一备件的价格:"
            "返回各客户的均价/中位/区间 + 相对整体均值的偏离标记(高于/低于/持平)。"
            "用于回答'同一备件各客户报价对比/谁买贵了/客户间价差'。只读。"
            "偏离阈值:客户均价 > 整体中位 ×1.3 = 高于均值;< ×0.77 = 低于均值。"
        ),
        inputSchema={
            "type": "object",
            "properties": {"part_name": {"type": "string", "description": "备件名称关键字"}},
            "required": ["part_name"],
        },
    ),
    Tool(
        name="list_part_price_outliers",
        description="列出所有被标记为异常高价的备件分项(聚类层离群检测),含单价、客户、来源合同。只读。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="customer_parts_contracts",
        description=(
            "查询某**客户/采购方**的备件采购明细:返回该客户的备件(按名分组 + 均价)和来源合同清单。用于回答'X客户买了哪些备件/采购均价/合同有哪些'。只读。客户名经别名表归一;若该客户未认领(pending),会标注'客户名尚未归一,可能含重复/别名'。"
        ),
        inputSchema={
            "type": "object",
            "properties": {"customer_name": {"type": "string", "description": "客户/采购方名称(支持别名匹配)"}},
            "required": ["customer_name"],
        },
    ),
]


# ── handlers ──


async def _handle_summary(arguments: dict) -> list[TextContent]:
    from sqlalchemy import func, select

    from app.extensions.spare_parts.models import CspCluster, CspCustomer, CspDocument, CspItem

    async def _q(session):
        docs = await session.scalar(select(func.count()).select_from(CspDocument)) or 0
        items = await session.scalar(select(func.count()).select_from(CspItem)) or 0
        clusters = await session.scalar(select(func.count()).select_from(CspCluster)) or 0
        # ponytail: count distinct non-null customer_id directly — 不用 subquery,
        # 否则 func.count(distinct CspItem.customer_id) 的列引用会把 csp_items 拉进 FROM,
        # 再叠加 .select_from(subquery) 形成笛卡尔积(非空库会返回 count×rows,见 bug-1177)。
        customers = await session.scalar(select(func.count(func.distinct(CspItem.customer_id))).where(CspItem.customer_id.is_not(None))) or 0
        pending = await session.scalar(select(func.count()).select_from(select(CspCluster).where(CspCluster.status == "pending").subquery())) or 0
        pending_customers = await session.scalar(select(func.count()).select_from(select(CspCustomer).where(CspCustomer.status == "pending").subquery())) or 0
        nr = await session.scalar(select(func.count()).select_from(select(CspItem).where(CspItem.validation_status == "needs_review").subquery())) or 0
        lo = await session.scalar(select(func.min(CspItem.unit_price)))
        hi = await session.scalar(select(func.max(CspItem.unit_price)))
        avg = await session.scalar(select(func.avg(CspItem.unit_price)))
        return dict(
            docs=int(docs),
            items=int(items),
            clusters=int(clusters),
            customers=int(customers),
            pending_clusters=int(pending),
            pending_customers=int(pending_customers),
            needs_review=int(nr),
            price_min=float(lo) if lo is not None else None,
            price_max=float(hi) if hi is not None else None,
            price_avg=round(float(avg), 2) if avg is not None else None,
        )

    data = await _run_in_db(_q)
    return _ok({"success": True, **data})


async def _handle_query_part(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.spare_parts.models import CspItem

    name = arguments["part_name"]

    async def _q(session):
        rows = (await session.execute(select(CspItem).where(CspItem.part_name.ilike(f"%{name}%")).order_by(CspItem.created_at))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    if not rows:
        return _ok({"success": True, "matched": 0, "message": f"未找到名称含「{name}」的备件。请先在备件价格分析管理页面分析相关合同。"})

    by_name: dict[str, list] = {}
    for it in rows:
        by_name.setdefault(it.part_name, []).append(it)

    groups = []
    for gname, items in by_name.items():
        priced = [float(i.unit_price) for i in items if i.unit_price is not None and i.validation_status in ("ok", "corrected")]
        nr = sum(1 for i in items if i.validation_status == "needs_review")
        ok = sum(1 for i in items if i.validation_status == "ok")
        corr = sum(1 for i in items if i.validation_status == "corrected")
        outliers = [{"unit_price": float(i.unit_price), "customer": i.customer_name, "contract": i.source_contract_no} for i in items if i.is_outlier and i.unit_price is not None]
        contracts = sorted({(i.source_contract_no or "(未关联)") for i in items})
        customers = sorted({(i.customer_name or "(未关联)") for i in items})
        samples = [
            {
                "unit_price": float(i.unit_price) if i.unit_price is not None else None,
                "price_untaxed": float(i.price_untaxed) if i.price_untaxed is not None else None,
                "quantity": float(i.quantity) if i.quantity is not None else None,
                "unit": i.unit,
                "customer": i.customer_name,
                "validation_status": i.validation_status,
            }
            for i in items[:5]
        ]
        groups.append(
            {
                "part_name": gname,
                "item_count": len(items),
                "price_stats": _stats(priced),
                "validation": {"ok": ok, "needs_review": nr, "corrected": corr},
                "outliers": outliers,
                "source_contracts": contracts,
                "customers": customers,
                "samples": samples,
                "confidence_note": "价格待人工溯源核验,仅供参考" if nr >= ok + corr else None,
            }
        )

    return _ok({"success": True, "keyword": name, "matched_items": len(rows), "matched_names": len(by_name), "groups": groups})


async def _handle_compare_by_customer(arguments: dict) -> list[TextContent]:
    """④ 特色:同备件跨客户比价。按 customer_id 分组,各客户独立统计 + 偏离整体中位标记。"""
    from sqlalchemy import select

    from app.extensions.spare_parts.models import CspItem

    name = arguments["part_name"]

    async def _q(session):
        rows = (await session.execute(select(CspItem).where(CspItem.part_name.ilike(f"%{name}%")).order_by(CspItem.created_at))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    if not rows:
        return _ok({"success": True, "matched": 0, "message": f"未找到名称含「{name}」的备件,无法做跨客户比价。"})

    # 整体基线:所有匹配项里 ok/corrected 的价格中位
    all_priced = [float(i.unit_price) for i in rows if i.unit_price is not None and i.validation_status in ("ok", "corrected")]
    baseline = _stats(all_priced)
    overall_median = baseline.get("median")

    # 按 customer 分组
    by_cust: dict[tuple, list] = {}
    for it in rows:
        key = (str(it.customer_id) if it.customer_id else None, it.customer_name or "(未关联客户)")
        by_cust.setdefault(key, []).append(it)

    cust_groups = []
    for (cust_id, cust_name), items in by_cust.items():
        priced = [float(i.unit_price) for i in items if i.unit_price is not None and i.validation_status in ("ok", "corrected")]
        st = _stats(priced)
        deviation = None
        if overall_median and st.get("mean") is not None and overall_median > 0:
            ratio = st["mean"] / overall_median
            if ratio >= 1.3:
                deviation = "高于均值"
            elif ratio <= 0.77:
                deviation = "低于均值"
            else:
                deviation = "持平"
        cust_groups.append(
            {
                "customer_id": cust_id,
                "customer_name": cust_name,
                "item_count": len(items),
                "priced_count": st.get("count", 0),
                "price_stats": st,
                "deviation_vs_overall": deviation,
                "contracts": sorted({(i.source_contract_no or "(未关联)") for i in items}),
            }
        )
    # 按均价降序(贵→便宜),None 最后
    cust_groups.sort(key=lambda g: (g["price_stats"].get("mean") is None, -(g["price_stats"].get("mean") or 0)))

    return _ok(
        {
            "success": True,
            "keyword": name,
            "matched_items": len(rows),
            "overall_stats": baseline,
            "customer_count": len(by_cust),
            "by_customer": cust_groups,
            "note": "偏离阈值:客户均价 ≥ 整体中位×1.3=高于均值;≤ ×0.77=低于均值;否则持平。",
        }
    )


async def _handle_outliers(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.spare_parts.models import CspItem

    async def _q(session):
        rows = (await session.execute(select(CspItem).where(CspItem.is_outlier.is_(True)).order_by(CspItem.unit_price.desc()))).scalars().all()
        return rows

    rows = await _run_in_db(_q)
    return _ok(
        {
            "success": True,
            "count": len(rows),
            "outliers": [{"part_name": r.part_name, "unit_price": float(r.unit_price) if r.unit_price is not None else None, "customer": r.customer_name, "source_contract_no": r.source_contract_no} for r in rows[:50]],
        }
    )


async def _handle_customer_parts(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.spare_parts.models import CspItem

    cust_name = arguments["customer_name"]

    async def _q(session):
        cust_id, canonical, pending = await _resolve_customer_id(session, cust_name)
        if cust_id is None:
            return None, None, False, []
        rows = (await session.execute(select(CspItem).where(CspItem.customer_id == cust_id).order_by(CspItem.created_at))).scalars().all()
        return cust_id, canonical, pending, rows

    cust_id, canonical, pending, rows = await _run_in_db(_q)
    if cust_id is None:
        return _ok({"success": True, "matched": 0, "message": f"未找到客户「{cust_name}」。该客户可能尚未在系统中认领归一,请先在管理页面上传其合同并认领。"})

    by_part: dict[str, list] = {}
    for it in rows:
        by_part.setdefault(it.part_name, []).append(it)
    parts = []
    for pname, items in by_part.items():
        priced = [float(i.unit_price) for i in items if i.unit_price is not None and i.validation_status in ("ok", "corrected")]
        parts.append(
            {
                "part_name": pname,
                "item_count": len(items),
                "price_stats": _stats(priced),
                "contracts": sorted({(i.source_contract_no or "(未关联)") for i in items}),
            }
        )
    parts.sort(key=lambda g: -(g["price_stats"].get("mean") or 0))
    contracts = sorted({(i.source_contract_no or "(未关联)") for i in rows})

    return _ok(
        {
            "success": True,
            "customer_id": str(cust_id),
            "customer_name": canonical,
            "pending": pending,
            "matched_items": len(rows),
            "part_count": len(by_part),
            "parts": parts,
            "contracts": contracts,
            "confidence_note": "客户名尚未认领归一,数据可能含重复/别名" if pending else None,
        }
    )


# ── server ──

server = Server("spare-parts-analysis")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "spare_part_summary": _handle_summary,
        "query_part_price": _handle_query_part,
        "compare_part_price_by_customer": _handle_compare_by_customer,
        "list_part_price_outliers": _handle_outliers,
        "customer_parts_contracts": _handle_customer_parts,
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
