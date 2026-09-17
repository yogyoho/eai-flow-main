"""doc_graph 实体消解 REST 路由——pending / suggestions / merge / unmerge（写侧审核门）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-semantic-map-v2-design.md §4。
实体消解 REST——doc_graph 写侧审核, admin-gated(system:access)。SQL/连接一律在 service.py（本文件零 SQL）,
风格照 ontology/routers.py。
异常映射契约: ResourceNotFound→404（detail 取 e.args[0]——KeyError 的 str() 带 repr 引号, 不可用）;
MergeConflict / IntegrityError→409; 其余 OntologyError/ValueError→400; 其余原样上抛（500）。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

# EAI-CUSTOM(2026-09-17 迁出独立): 原 gateway 依赖 app.extensions.auth.middleware /
# app.extensions.schemas → 本地 app.auth（S1 Task 2 已实装 HS256 JWT 验签, v1 superadmin-only）。
from app.auth import CurrentUser, require_permission
from app.doc_graph import service
from app.doc_graph.service import MergeConflict, ResourceNotFound
from app.ontology.engine import OntologyError

router = APIRouter(prefix="/api/extensions/doc-graph", tags=["doc-graph"])


class MergeBody(BaseModel):
    """POST /resolution/merge 请求体（边界对齐表约束: confidence→Numeric(4,3), method→String(30) 枚举; 越界 pydantic 422 而非 500）。"""

    candidate_id: str
    canonical_id: str
    method: Literal["similarity", "manual"] = "manual"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class UnmergeBody(BaseModel):
    """POST /resolution/unmerge 请求体。"""

    merge_id: str


def _uuid_or_404(value: str, label: str) -> str:
    """malformed uuid → 404（无法标识任何资源; 否则 asyncpg CAST(:x AS uuid) DataError 变 500）。

    返回 canonical 形式（str(uuid.UUID)）——uuid.UUID 也接受 {…}/urn:uuid: 等拼写, Postgres CAST 会拒。
    """
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(status_code=404, detail=f"{label} 不存在") from e


def _resolution_http_error(e: Exception) -> HTTPException:
    """service 异常 → REST 状态码映射（三态契约, 见模块 docstring）。"""
    if isinstance(e, ResourceNotFound):
        return HTTPException(status_code=404, detail=e.args[0])
    if isinstance(e, MergeConflict):
        return HTTPException(status_code=409, detail=e.args[0])
    if isinstance(e, IntegrityError):
        return HTTPException(status_code=409, detail="自合并或约束冲突")
    return HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}")


@router.get("/resolution/pending")
async def resolution_pending(
    etype: str | None = None,
    limit: int = 50,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """status=pending_review 实体列表（置信度升序; limit 钳制在 service）。"""
    return await service.list_pending_review(etype, limit)


@router.get("/resolution/suggestions")
async def resolution_suggestions(
    entity_id: str = Query(...),
    top: int = 5,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """同 etype 相近实体合并建议（≥0.92 降序 Top-N; self 圈除由 service SQL 承担）。"""
    eid = _uuid_or_404(entity_id, f"entity {entity_id}")
    try:
        return await service.resolution_suggestions(eid, top)
    except (ResourceNotFound, MergeConflict, IntegrityError, OntologyError, ValueError) as e:
        raise _resolution_http_error(e) from e


@router.post("/resolution/merge")
async def resolution_merge(
    body: MergeBody,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """candidate 并入 canonical（candidate 置 merged + dg_merges 留痕, 可 unmerge 撤销）。"""
    cid = _uuid_or_404(body.candidate_id, f"candidate {body.candidate_id}")
    kid = _uuid_or_404(body.canonical_id, f"canonical {body.canonical_id}")
    try:
        res = await service.merge_entities(cid, kid, method=body.method, confidence=body.confidence)
    except (ResourceNotFound, MergeConflict, IntegrityError, OntologyError, ValueError) as e:
        raise _resolution_http_error(e) from e
    return {**res, "candidate_id": cid, "canonical_id": kid}


@router.post("/resolution/unmerge")
async def resolution_unmerge(
    body: UnmergeBody,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """撤销一次合并（删留痕行, candidate 置回 active）。"""
    mid = _uuid_or_404(body.merge_id, f"merge {body.merge_id}")
    try:
        res: dict[str, Any] = await service.unmerge(mid)
    except (ResourceNotFound, MergeConflict, IntegrityError, OntologyError, ValueError) as e:
        raise _resolution_http_error(e) from e
    return res
