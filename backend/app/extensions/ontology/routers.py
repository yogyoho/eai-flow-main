"""Ontology 语义层 REST 路由 — 6 核心端点（pytest HTTP 集成测试载体）.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §8
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T6（D16）

EAI-CUSTOM(2026-08-15): 只读语义地图/管理查询，admin-gated(system:access)。
search/traverse/reload 包装随 1b（D16 砍面后的剩余项）。
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.extensions.auth.middleware import require_permission
from app.extensions.ontology.connectors import OntologyConnectors
from app.extensions.ontology.engine import Engine, OntologyError
from app.extensions.ontology.registry import get_registry, get_registry_store
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/ontology", tags=["ontology"])

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine(get_registry, OntologyConnectors())
    return _engine


def _http_error(e: Exception) -> HTTPException:
    status = 404 if type(e).__name__ in ("UnknownObjectError", "UnknownLinkError") else 400
    return HTTPException(status_code=status, detail=f"{type(e).__name__}: {e}")


@router.get("/registry")
async def get_registry_meta(_: CurrentUser = Depends(require_permission("system:access"))):
    """注册表元信息 + 各 access 可用性（断连显式 available:false）。"""
    store = get_registry_store()
    reg = store.get()
    seen: set[tuple[str, str | None, str | None]] = set()
    accesses = []
    for o in reg.object_types.values():
        key = (o.access.path, o.access.source_id, o.access.table or o.access.table_name)
        if key not in seen:
            seen.add(key)
            accesses.append(o.access)
    con = OntologyConnectors()
    return {
        "registry_version": reg.registry_version,
        "fingerprint": store._agg(reg)[:8],
        "schema_version": reg.manifest.schema_version,
        "object_type_count": len(reg.object_types),
        "link_type_count": len(reg.link_types),
        "availability": await con.availability(accesses),
    }


@router.get("/object-types")
async def list_object_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = get_registry()
    return {
        "object_types": [{"name": o.api_name, "display_name": o.display_name, "description": o.description, "pk": o.pk.api_name, "properties": [p.api_name for p in o.visible_properties()]} for o in reg.object_types.values()],
        "link_types": [{"name": lt.api_name, "source": lt.source, "target": lt.target, "enabled": lt.enabled, **({"note": lt.note} if not lt.enabled and lt.note else {})} for lt in reg.link_types.values()],
    }


@router.get("/objects/{object_type}")
async def list_objects(
    object_type: str,
    filters: str | None = Query(None, description='JSON 数组, 如 [{"column":"unit_price","op":"gte","value":100}]'),
    q: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    order: str | None = None,
    desc: bool = False,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    parsed: list[dict[str, Any]] | None = None
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"filters 不是合法 JSON: {e}") from e
    try:
        return await _get_engine().list_objects(object_type, filters=parsed, q=q, limit=limit, cursor=cursor, order=order, desc=desc)
    except OntologyError as e:
        raise _http_error(e) from e


@router.get("/objects/{object_type}/{pk}")
async def get_object(object_type: str, pk: str, _: CurrentUser = Depends(require_permission("system:access"))):
    try:
        obj = await _get_engine().get_object(object_type, pk)
    except OntologyError as e:
        raise _http_error(e) from e
    if obj is None:
        raise HTTPException(status_code=404, detail=f"未找到 {object_type}#{pk}")
    return obj


@router.get("/objects/{object_type}/{pk}/links/{link_type}")
async def get_links(
    object_type: str,
    pk: str,
    link_type: str,
    limit: int = 100,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        return await _get_engine().get_links(object_type, pk, link_type, limit=limit)
    except OntologyError as e:
        raise _http_error(e) from e


@router.post("/aggregate")
async def aggregate(
    body: dict[str, Any],
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        return await _get_engine().aggregate(body["object_type"], body["group_by"], metric=body.get("metric", "count"), metric_column=body.get("metric_column"), filters=body.get("filters"), limit=body.get("limit", 100))
    except OntologyError as e:
        raise _http_error(e) from e
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"缺少必填字段: {e}") from e
