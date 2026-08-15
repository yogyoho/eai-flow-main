"""Ontology REST surface — thin passthrough of the engine for the semantic-map frontend.

Mounted at /api/extensions/ontology. Admin-gated (require_permission system:access),
same as contract_price/spare_parts (mother spec §10 R3 decision).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.extensions.auth.middleware import require_permission
from app.extensions.ontology.engine.query import QueryEngine
from app.extensions.ontology.registry import RegistryCache
from app.extensions.ontology.schemas import (
    AggregateRow,
    LinkTypeOut,
    ObjectListOut,
    ObjectTypeOut,
    PropertyOut,
    RegistryOut,
)
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/ontology", tags=["Ontology Semantic Layer"])

_cache = RegistryCache()
_engine: QueryEngine | None = None


def _get_engine() -> QueryEngine:
    global _engine
    if _engine is None:
        from app.extensions.ontology.connectors import data_source as ds
        from app.extensions.ontology.connectors import postgres_ext as pg

        _engine = QueryEngine(_cache.get(), pg_connector=pg, ds_connector=ds)
    return _engine


def _to_link_out(link) -> LinkTypeOut:
    return LinkTypeOut(
        **link.model_dump(exclude={"join", "direction"}),
        join_type=link.join.type,
        join_expression=link.join.expression,
    )


@router.get("/registry", response_model=RegistryOut)
async def get_registry(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return RegistryOut(
        schema_version=reg.schema_version,
        registry_version=reg.registry_version,
        hot_reload=reg.hot_reload,
        files=[f.model_dump() for f in reg.files],
        object_types=[_to_type_out(o) for o in reg.object_types if o.enabled],
        link_types=[_to_link_out(link) for link in reg.link_types if link.enabled],
    )


@router.post("/registry/reload")
async def reload_registry(_: CurrentUser = Depends(require_permission("system:access"))):
    _cache.invalidate()  # force re-load on next get()
    reg = _cache.get()
    return {"registry_version": reg.registry_version, "reloaded": True}


@router.get("/object-types", response_model=list[ObjectTypeOut])
async def list_object_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return [_to_type_out(o) for o in reg.object_types if o.enabled]


@router.get("/object-types/{api_name}", response_model=ObjectTypeOut)
async def get_object_type(api_name: str, _: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    obj = reg.object_by_name(api_name)
    if obj is None:
        raise HTTPException(404, "object type not found")
    return _to_type_out(obj)


@router.get("/link-types", response_model=list[LinkTypeOut])
async def list_link_types(_: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    return [_to_link_out(link) for link in reg.link_types if link.enabled]


@router.get("/objects/{object_type}", response_model=ObjectListOut)
async def list_objects(object_type: str, filter: str | None = None, order_by: str | None = None, limit: int = 50, cursor: str | None = None, _: CurrentUser = Depends(require_permission("system:access"))):
    filters = json.loads(filter) if filter else None
    return await _get_engine().list(object_type, filters, order_by, limit, cursor)


@router.get("/objects/{object_type}/{primary_key}")
async def get_object(object_type: str, primary_key: str, _: CurrentUser = Depends(require_permission("system:access"))):
    obj = await _get_engine().get(object_type, primary_key)
    if obj is None:
        raise HTTPException(404, "object not found")
    return {"success": True, "object": obj}


@router.get("/objects/{object_type}/{primary_key}/links/{link_type}", response_model=ObjectListOut)
async def get_links(object_type: str, primary_key: str, link_type: str, limit: int = 50, cursor: str | None = None, _: CurrentUser = Depends(require_permission("system:access"))):
    return await _get_engine().get_links(object_type, primary_key, link_type, limit, cursor)


@router.post("/objects/traverse")
async def traverse(body: dict[str, Any], _: CurrentUser = Depends(require_permission("system:access"))):
    try:
        return await _get_engine().traverse_path(body["object_type"], body["primary_key"], body["path"], body.get("limit", 50))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/search")
async def search(term: str, object_type: str | None = None, limit: int = 20, _: CurrentUser = Depends(require_permission("system:access"))):
    reg = _cache.get()
    if object_type:
        return await _get_engine().search(object_type, term, limit)
    # 全局:跨所有 searchable 类型聚合
    out = []
    for o in reg.object_types:
        if not o.enabled:
            continue
        try:
            r = await _get_engine().search(o.api_name, term, limit)
            out.extend({"object_type": o.api_name, **item} for item in r.get("objects", []))
        except Exception:  # noqa: BLE001 — one type failing shouldn't kill global search
            continue
    return {"objects": out, "hasMore": False}


@router.post("/aggregate", response_model=list[AggregateRow])
async def aggregate(body: dict[str, Any], _: CurrentUser = Depends(require_permission("system:access"))):
    try:
        rows = await _get_engine().aggregate(body["object_type"], body.get("group_by"), body.get("metric"), body.get("filter"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return [AggregateRow(**r) for r in rows]


def _to_type_out(o) -> ObjectTypeOut:
    return ObjectTypeOut(
        api_name=o.api_name,
        display_name=o.display_name,
        description=o.description,
        domain=o.domain,
        icon=o.icon,
        access={"path": o.access.path, "table": o.access.table or o.access.table_name},
        pk=o.pk.api_name,
        properties=[PropertyOut(**p.model_dump(exclude={"name"})) for p in o.properties if not p.hidden],
    )
