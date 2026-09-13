"""doc_graph 审核共享服务层——REST 与 MCP 共用的消解 SQL 逻辑.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-semantic-map-v2-design.md §4。
从 mcp.py 抽取(实现去重); SQL 语义与既终态逐字一致(CAST(:etype AS text) asyncpg 修复等)。
异常约定: ResourceNotFound = 资源不存在(REST→404, MCP 的 except KeyError 照常捕获→结构化消息, MCP 零改动);
MergeConflict(candidate 已有未撤销留痕, 2026-09-13 v2 Task2) / IntegrityError(自合并 CHECK) = 409。
既定语义(v1 口径, 2026-09-13 评审加固): unmerge 还原固定 active(不记忆合并前 prior status);
status=merged 实体不参与 suggestions(候选圈定只取 active/pending_review)。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.ontology.connectors import _ext_url
from app.extensions.ontology.doc_graph.resolver import REVIEW_THRESHOLD, decide_merge


class ResourceNotFound(KeyError):
    """资源不存在（REST→404, MCP 结构化消息）。KeyError 子类保持 MCP 现有 except 兼容。"""


class MergeConflict(RuntimeError):
    """candidate 已有未撤销合并留痕（REST→409; MCP 走通用 _err 结构化, 零改动）。"""


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

    candidate 不存在 / canonical 不存在(先验, 候选不翻转) → ResourceNotFound;
    candidate 已有未撤销留痕 → MergeConflict(REST→409, 堵重复审计行);
    自合并 CHECK 等约束冲突 → IntegrityError 上抛。
    """
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            dup = (await conn.execute(text("SELECT id FROM dg_merges WHERE candidate_id = CAST(:cid AS uuid) LIMIT 1"), {"cid": candidate_id})).first()
            if dup is not None:
                raise MergeConflict(f"candidate {candidate_id} 已有合并留痕(merge {dup.id}), 须先 unmerge 再重并")
            canon = (await conn.execute(text("SELECT id FROM dg_entities WHERE id = CAST(:kid AS uuid)"), {"kid": canonical_id})).first()
            if canon is None:
                raise ResourceNotFound(f"canonical {canonical_id} 不存在")  # 先验: 否则 FK 违约束 → 误分类 409
            upd = await conn.execute(
                text("UPDATE dg_entities SET status = 'merged', updated_at = NOW() WHERE id = CAST(:cid AS uuid)"),
                {"cid": candidate_id},
            )
            if upd.rowcount == 0:
                raise ResourceNotFound(f"candidate {candidate_id} 不存在")
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

    merge 不存在 → ResourceNotFound。还原固定 active, 不记忆合并前 prior status（v1 口径）。
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
                raise ResourceNotFound(f"merge {merge_id} 不存在")
            await conn.execute(
                text("UPDATE dg_entities SET status = 'active', updated_at = NOW() WHERE id = :cid"),
                {"cid": row.candidate_id},
            )
    finally:
        await engine.dispose()
    return {"restored_candidate_id": str(row.candidate_id)}


def score_candidates(entity_norm_name: str, entity_etype: str, rows: list[dict[str, Any]], top: int = 5) -> list[dict[str, Any]]:
    """同 etype 实体按 norm_name 相似度打分（≥ REVIEW_THRESHOLD），降序截 top。

    返回 [{id, canonical_name, etype, norm_name, similarity, action}]（action 来自 decide_merge）。
    精确同名候选（auto_merge）照常返回——uq(domain,etype,norm_name) 下同 etype 精确同名只能是跨域孪生;
    self 圈除由调用方 SQL 的 id != 目标id 承担（本函数无 id 信息, 见 resolution_suggestions）。
    """
    scored = []
    for r in rows:
        if r.get("etype") != entity_etype:
            continue
        d = decide_merge(entity_norm_name, r.get("norm_name") or "")
        if d.similarity < REVIEW_THRESHOLD:
            continue
        scored.append({**r, "similarity": round(d.similarity, 4), "action": d.action})
    scored.sort(key=lambda s: s["similarity"], reverse=True)
    return scored[: max(1, top)]


async def resolution_suggestions(entity_id: str, top: int = 5) -> dict[str, Any]:
    """目标实体行 + 同 etype 相近实体合并建议（REST /resolution/suggestions 后端, 2026-09-13 v2 Task2）。

    目标不存在 → ResourceNotFound。候选圈定: 同 etype 且 status ∈ (active, pending_review)
    （merged 不参与, v1 口径）, id != 目标（self 圈除在本 SQL 完成, score_candidates 不重复处理）。
    """
    top = max(1, min(int(top), 20))
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            target = (
                (
                    await conn.execute(
                        text("SELECT id, domain, etype, canonical_name, norm_name, confidence FROM dg_entities WHERE id = CAST(:eid AS uuid) LIMIT 1"),
                        {"eid": entity_id},
                    )
                )
                .mappings()
                .first()
            )
            if target is None:
                raise ResourceNotFound(f"entity {entity_id} 不存在")
            rows = [
                dict(r)
                for r in (
                    await conn.execute(
                        text("SELECT id, etype, canonical_name, norm_name FROM dg_entities WHERE etype = :et AND status IN ('active', 'pending_review') AND id != CAST(:eid AS uuid)"),
                        {"et": target["etype"], "eid": entity_id},
                    )
                )
                .mappings()
                .all()
            ]
    finally:
        await engine.dispose()
    return {
        "entity": {"id": str(target["id"]), "canonical_name": target["canonical_name"], "etype": target["etype"]},
        "suggestions": score_candidates(target["norm_name"], target["etype"], rows, top=top),
    }
