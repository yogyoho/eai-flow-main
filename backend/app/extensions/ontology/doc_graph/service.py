"""doc_graph 审核共享服务层——REST 与 MCP 共用的消解 SQL 逻辑.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-semantic-map-v2-design.md §4。
从 mcp.py 抽取(实现去重); SQL 语义与既终态逐字一致(CAST(:etype AS text) asyncpg 修复等)。
异常约定: KeyError("candidate"/"merge") = 资源不存在(REST→404, MCP→结构化消息);
IntegrityError(自合并 CHECK) = 409(MCP→_err 结构化)。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.ontology.connectors import _ext_url


async def list_pending_review(etype: str | None = None, limit: int = 50) -> dict[str, Any]:
    """status=pending_review 实体列表（置信度升序）。"""
    lim = max(1, min(int(limit), 200))
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT id, domain, etype, canonical_name, confidence FROM dg_entities WHERE status = 'pending_review' AND (CAST(:etype AS text) IS NULL OR etype = CAST(:etype AS text)) ORDER BY confidence ASC LIMIT :lim"),
                {"etype": etype, "lim": lim},
            )
            rows = [dict(r) for r in res.mappings().all()]
    finally:
        await engine.dispose()
    return {"entities": rows, "count": len(rows)}


async def merge_entities(candidate_id: str, canonical_id: str, method: str = "manual", confidence: float = 1.0) -> dict[str, Any]:
    """candidate 置 merged + dg_merges 留痕。返回 {"merge_id": ...}。

    candidate 不存在 → KeyError; 自合并等约束冲突 → IntegrityError 上抛。
    """
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            upd = await conn.execute(
                text("UPDATE dg_entities SET status = 'merged', updated_at = NOW() WHERE id = CAST(:cid AS uuid)"),
                {"cid": candidate_id},
            )
            if upd.rowcount == 0:
                raise KeyError(f"candidate {candidate_id} 不存在")
            row = (
                await conn.execute(
                    text("INSERT INTO dg_merges (candidate_id, canonical_id, method, confidence) VALUES (CAST(:cid AS uuid), CAST(:kid AS uuid), :method, :conf) RETURNING id"),
                    {"cid": candidate_id, "kid": canonical_id, "method": method, "conf": confidence},
                )
            ).first()
    finally:
        await engine.dispose()
    return {"merge_id": str(row.id)}


async def unmerge(merge_id: str) -> dict[str, Any]:
    """删留痕 + candidate 还原 active。返回 {"restored_candidate_id": ...}。

    merge 不存在 → KeyError。
    """
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text("DELETE FROM dg_merges WHERE id = CAST(:mid AS uuid) RETURNING candidate_id"),
                    {"mid": merge_id},
                )
            ).first()
            if row is None:
                raise KeyError(f"merge {merge_id} 不存在")
            await conn.execute(
                text("UPDATE dg_entities SET status = 'active', updated_at = NOW() WHERE id = :cid"),
                {"cid": row.candidate_id},
            )
    finally:
        await engine.dispose()
    return {"restored_candidate_id": str(row.candidate_id)}
