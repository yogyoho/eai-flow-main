"""doc_graph 写 MCP Server——4 工具，ontology 只读 server 的构建侧补充.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §3.1 补全。
- ingest_extraction: LLM 抽取 JSON → fail-closed 校验 → 入库（幂等）
- list_pending_review: 低置信待复核实体
- merge_entities / unmerge: 消解合并与撤销（dg_merges 留痕）
查询走只读 ontology server 的 graph_* 对象——本 server 只写。
"""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_TOOLS_SPEC = [
    (
        "ingest_extraction",
        "把抽取出的投标实体/关系/证据入库（幂等：同名实体归并）。payload 须严格符合投标域抽取 schema（extra 字段会被拒绝）。",
        {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": ["bid"]},
                "extracted_by": {"type": "string"},
                "thread_id": {"type": "string"},
                "entities": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                "relations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["domain", "entities"],
        },
    ),
    (
        "list_pending_review",
        "列出低置信度待复核实体（status=pending_review），可请用户确认后用 merge_entities 合并。",
        {"type": "object", "properties": {"etype": {"type": "string", "description": "实体类型: project/bidder/goods/qualification"}, "limit": {"type": "integer"}}, "required": []},
    ),
    (
        "merge_entities",
        "把候选实体合并进规范实体（candidate 置 merged + dg_merges 留痕，可撤销）。",
        {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "canonical_id": {"type": "string"},
                "method": {"type": "string", "description": "合并依据: similarity | manual"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["candidate_id", "canonical_id"],
        },
    ),
    (
        "unmerge",
        "撤销一次合并（删留痕行，candidate 置回 active）。",
        {"type": "object", "properties": {"merge_id": {"type": "string"}}, "required": ["merge_id"]},
    ),
]

TOOLS = [Tool(name=n, description=d, inputSchema=s) for n, d, s in _TOOLS_SPEC]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(e: Exception) -> list[TextContent]:
    return _ok({"success": False, "error": f"{type(e).__name__}: {e}"})


async def _ingest_extraction(a: dict) -> list[TextContent]:
    from pydantic import ValidationError

    from app.extensions.ontology.doc_graph.ingest import REVIEW_CONFIDENCE, ingest_extraction
    from app.extensions.ontology.doc_graph.schemas import BidExtraction

    try:
        payload = BidExtraction.model_validate(a)
    except ValidationError as e:
        return _ok({"success": False, "error": f"schema 校验失败(fail-closed): {e.error_count()} 处", "detail": str(e)[:2000]})
    counts = await ingest_extraction(payload)
    return _ok({"success": True, **counts, "hint": f"confidence<{REVIEW_CONFIDENCE} 的实体已置 pending_review, 用 list_pending_review 查看"})


async def _list_pending_review(a: dict) -> list[TextContent]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.connectors import _ext_url

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT id, domain, etype, canonical_name, confidence FROM dg_entities WHERE status = 'pending_review' AND (CAST(:etype AS text) IS NULL OR etype = CAST(:etype AS text)) ORDER BY confidence ASC LIMIT :lim"),
                {"etype": a.get("etype"), "lim": max(1, min(int(a.get("limit", 50)), 200))},
            )
            rows = [dict(r) for r in res.mappings().all()]
    finally:
        await engine.dispose()
    return _ok({"success": True, "count": len(rows), "entities": rows})


async def _merge_entities(a: dict) -> list[TextContent]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.connectors import _ext_url

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            res = await conn.execute(
                text("UPDATE dg_entities SET status = 'merged', updated_at = NOW() WHERE id = CAST(:cid AS uuid)"),
                {"cid": a["candidate_id"]},
            )
            if res.rowcount == 0:
                return _ok({"success": False, "message": f"candidate {a['candidate_id']} 不存在"})
            row = (
                await conn.execute(
                    text("INSERT INTO dg_merges (candidate_id, canonical_id, method, confidence) VALUES (CAST(:cid AS uuid), CAST(:kid AS uuid), :method, :conf) RETURNING id"),
                    {"cid": a["candidate_id"], "kid": a["canonical_id"], "method": a.get("method", "manual"), "conf": a.get("confidence", 1.0)},
                )
            ).first()
    finally:
        await engine.dispose()
    return _ok({"success": True, "merge_id": str(row.id)})


async def _unmerge(a: dict) -> list[TextContent]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.connectors import _ext_url

    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text("DELETE FROM dg_merges WHERE id = CAST(:mid AS uuid) RETURNING candidate_id"),
                    {"mid": a["merge_id"]},
                )
            ).first()
            if row is None:
                return _ok({"success": False, "message": f"merge {a['merge_id']} 不存在"})
            await conn.execute(
                text("UPDATE dg_entities SET status = 'active', updated_at = NOW() WHERE id = :cid"),
                {"cid": row.candidate_id},
            )
    finally:
        await engine.dispose()
    return _ok({"success": True, "restored_candidate_id": str(row.candidate_id)})


_HANDLERS = {
    "ingest_extraction": _ingest_extraction,
    "list_pending_review": _list_pending_review,
    "merge_entities": _merge_entities,
    "unmerge": _unmerge,
}

server = Server("doc-graph")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments or {})
    except Exception as e:  # 结构化错误返回 agent, 不崩 server
        return _err(e)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
