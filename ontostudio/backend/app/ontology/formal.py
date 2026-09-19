"""形式化内核 REST 服务面（kernel P5）——/formal/* 四端点.

- POST /load     SQL 测试数据 → 断言图（装载器，兼任主系统桥接器）
- POST /infer    schema 重编 → owlrl 闭包 → CONSTRUCT 派生（返回各层计数）
- GET  /validate SHACL 报告 + 国标五项符合性（校验中心页数据源）
- GET  /export   图真源 → Turtle/JSON-LD（快照/互操作页数据源）

鉴权与其余 ontology 路由一致（system:access）。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, require_permission
from app.ontology.kernel.service import get_kernel

router = APIRouter(prefix="/api/extensions/ontology/formal", tags=["ontology-formal"])


@router.post("/load")
async def formal_load(
    domain: str | None = Query(None, description="缺省域（行自带 domain 时按行解析）"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        return {"success": True, **get_kernel().load_from_sql(domain=domain)}
    except Exception as e:  # noqa: BLE001 - DB 不可达等 → 503（数据面未就绪）
        raise HTTPException(status_code=503, detail=f"装载失败: {e}") from e


@router.post("/infer")
async def formal_infer(
    min_confidence: float = Query(0.7, ge=0.0, le=1.0),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    stats = get_kernel().refresh(min_confidence=min_confidence)
    return {"success": True, **asdict(stats)}


@router.get("/validate")
async def formal_validate(_: CurrentUser = Depends(require_permission("system:access"))):
    return {"success": True, **get_kernel().validate()}


@router.get("/export")
async def formal_export(
    format: str = Query("turtle", pattern="^(turtle|json-ld)$"),
    graphs: str = Query("all", pattern="^(all|schema|asserted|entailment)$"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    out = get_kernel().export(fmt=format, graphs=graphs)
    if format == "json-ld":
        # rdflib json-ld 顶层是节点数组——包一层交给 FastAPI 序列化
        return {"success": True, "format": format, "graphs": graphs, "document": out}
    from fastapi import Response

    return Response(content=out, media_type="text/turtle; charset=utf-8")
