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
        return {"success": True, **await get_kernel().load_from_sql(domain=domain)}
    except Exception as e:  # noqa: BLE001 - DB 不可达等 → 503（数据面未就绪）
        raise HTTPException(status_code=503, detail=f"装载失败: {e}") from e


@router.post("/infer")
async def formal_infer(
    min_confidence: float = Query(0.7, ge=0.0, le=1.0),
    dry: bool = Query(False, description="F6 试算：不落盘，仅返回统计"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    stats = get_kernel().refresh(min_confidence=min_confidence, dry=dry)
    return {"success": True, "dry": dry, **asdict(stats)}


@router.post("/cq/run")
async def formal_cq_run(_: CurrentUser = Depends(require_permission("system:access"))):
    """CQ 验收自动化（F5）：cq.yaml 逐条 ASK 真跑（推理工作台验收问题面板数据源）。"""
    return {"success": True, "results": get_kernel().run_cqs()}


@router.get("/rules")
async def formal_rules(_: CurrentUser = Depends(require_permission("system:access"))):
    """规则清单+源码+启用状态（F1/F8）：YAML 规则 + 内置 sameAs + registry 属性链自动生成。"""
    return {"success": True, "rules": get_kernel().rule_sources()}


@router.get("/rules/{name}/derivations")
async def formal_rule_derivations(
    name: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """派生三元组下钻（F2）：graph:derived:<name> 内容分页（named graph 归属即触发轨迹）。"""
    try:
        return {
            "success": True,
            "rule": name,
            **get_kernel().rule_derivations(name, limit=limit, offset=offset),
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/rules/{name}/trace")
async def formal_rule_trace(
    name: str,
    s: str = Query(..., description="派生三元组主体 IRI"),
    p: str = Query(..., description="派生谓词 IRI"),
    o: str = Query(..., description="派生三元组客体 IRI"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """单三元组溯源（F3）：返回触发该派生结论的基础事实链。"""
    try:
        return {"success": True, **get_kernel().rule_trace(name, s, p, o)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"规则不存在: {e}") from e


@router.get("/rules/{name}/explain-miss")
async def formal_rule_explain_miss(
    name: str,
    s: str = Query(..., description="期望结论主体 IRI"),
    o: str = Query(..., description="期望结论客体 IRI"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """反事实解释（F4）：期望派生未出现时，逐段定位断言图断裂点。"""
    try:
        return {"success": True, **get_kernel().rule_explain_miss(name, s, o)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"规则不存在: {e}") from e


@router.post("/rules/{name}/enabled")
async def formal_rule_set_enabled(
    name: str,
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """规则启停（F8）：状态写 kernel 卷 overlay，启用即单规则重算、停用即撤派生图。"""
    enabled = bool(payload.get("enabled", True))
    try:
        return {"success": True, **get_kernel().set_rule_enabled(name, enabled)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"规则不存在: {e}") from e


@router.get("/infer-last")
async def formal_infer_last(_: CurrentUser = Depends(require_permission("system:access"))):
    """内核当前推理状态（初始化读路径）：实时数图 + 最近落盘元数据，不触发重算。"""
    return {"success": True, **get_kernel().infer_last()}


@router.get("/history")
async def formal_history(
    limit: int = Query(20, ge=1, le=100),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """推理历史（F9）：近 N 次落盘重算（倒序），前端做相邻 diff。"""
    return {"success": True, "history": get_kernel().infer_history(limit)}


@router.get("/entity-labels")
async def formal_entity_labels(
    ids: str = Query(..., description="逗号分隔实体 uuid（≤500）"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """uuid → canonical_name（F2 下钻可读性）：dg_entities 按主键批量（SQL 是名字真相源——
    kernel 图不存 canonical_name，全量装载路径不写名字三元组）。"""
    import uuid as uuid_mod

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import DatabaseConfig

    uuid_list = [u.strip() for u in ids.split(",") if u.strip()][:500]
    if not uuid_list:
        return {"success": True, "labels": {}}
    try:
        params = [uuid_mod.UUID(u) for u in uuid_list]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"uuid 不合法: {e}") from e
    engine = create_async_engine(DatabaseConfig.from_env().url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT id::text AS id, canonical_name FROM dg_entities WHERE id = ANY(:ids)"),
                    {"ids": params},
                )
            ).mappings().all()
    finally:
        await engine.dispose()
    return {"success": True, "labels": {r["id"]: r["canonical_name"] for r in rows if r["canonical_name"]}}


@router.get("/orphans")
async def formal_orphans(_: CurrentUser = Depends(require_permission("system:access"))):
    """内核孤儿实体清单（治理）：asserted 实体 IRI 中 dg_entities 无对应行者。"""
    return {"success": True, **await get_kernel().orphans()}


@router.post("/orphans/purge")
async def formal_orphans_purge(
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """精确清除指定实体的 asserted 三元组（治理确认后执行；派生图建议随后全量重算）。"""
    iris = [str(i) for i in payload.get("iris", [])]
    return {"success": True, **get_kernel().purge_orphans(iris)}


@router.get("/orphan-mentions")
async def formal_orphan_mentions(_: CurrentUser = Depends(require_permission("system:access"))):
    """零边 mention 清单（无效证据治理）：证据未指向实体/关系任一。"""
    return {"success": True, **get_kernel().orphan_mentions()}


@router.post("/orphan-mentions/purge")
async def formal_orphan_mentions_purge(_: CurrentUser = Depends(require_permission("system:access"))):
    """精确清除全部零边 mention 节点（无效证据治理确认后执行）。"""
    return {"success": True, **get_kernel().purge_orphan_mentions()}


@router.get("/validate-last")
async def formal_validate_last(_: CurrentUser = Depends(require_permission("system:access"))):
    """最近一次校验完整结果（初始化读路径）：不触发 pyshacl，原样还原校验中心面板。"""
    return {"success": True, "last": get_kernel().validate_last()}


@router.get("/validate-history")
async def formal_validate_history(
    limit: int = Query(20, ge=1, le=100),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """校验历史：近 N 次 SHACL 运行（倒序，每次 GET /validate 自动记录）。"""
    return {"success": True, "history": get_kernel().validate_history(limit)}


@router.post("/load-ontology")
async def formal_load_ontology(
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """四类目标抽取结果 → kernel 断言图（抽取导入页数据源）。"""
    try:
        return {"success": True, **get_kernel().load_ontology(payload)}
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"payload 缺字段: {e}") from e


@router.get("/validate")
async def formal_validate(_: CurrentUser = Depends(require_permission("system:access"))):
    return {"success": True, **get_kernel().validate()}


@router.get("/export")
async def formal_export(
    format: str = Query("turtle", pattern="^(turtle|json-ld|trig)$"),
    graphs: str = Query("all", pattern="^(all|all\\+derived|schema|asserted|entailment|derived)$"),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    out = get_kernel().export(fmt=format, graphs=graphs)
    if format == "json-ld":
        # rdflib json-ld 顶层是节点数组——包一层交给 FastAPI 序列化
        return {"success": True, "format": format, "graphs": graphs, "document": out}
    from fastapi import Response

    media = "application/trig" if format == "trig" else "text/turtle; charset=utf-8"
    return Response(content=out, media_type=media)


# ---- 快照（D8）：TriG 全图落盘 / 清单 / 内容下载 / 恢复（自动回滚点）/ 删除 ----

_SNAP_NAME = "snapshot-[A-Za-z0-9._\\-]+\\.trig"


@router.post("/snapshots")
async def formal_snapshot_create(_: CurrentUser = Depends(require_permission("system:access"))):
    """生成 TriG 全图快照（含派生）落盘内核卷 snapshots/。"""
    return {"success": True, **get_kernel().create_snapshot()}


@router.get("/snapshots")
async def formal_snapshot_list(_: CurrentUser = Depends(require_permission("system:access"))):
    return {"success": True, "snapshots": get_kernel().list_snapshots()}


@router.get("/snapshots/{file}")
async def formal_snapshot_download(
    file: str,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    import re as _re

    from fastapi import Response

    if not _re.fullmatch(_SNAP_NAME, file):
        raise HTTPException(status_code=422, detail="快照文件名不合法")
    try:
        content = get_kernel().snapshot_content(file)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="快照不存在") from e
    return Response(content=content, media_type="application/trig")


@router.post("/snapshots/restore")
async def formal_snapshot_restore(
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """恢复快照：清空全部 named graph 后原样回灌；恢复前自动生成 pre-restore 回滚点。"""
    file = str(payload.get("file", ""))
    try:
        return {"success": True, **get_kernel().restore_snapshot(file)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail="快照不存在") from e


@router.delete("/snapshots/{file}")
async def formal_snapshot_delete(
    file: str,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    import re as _re

    if not _re.fullmatch(_SNAP_NAME, file):
        raise HTTPException(status_code=422, detail="快照文件名不合法")
    try:
        return {"success": True, **get_kernel().delete_snapshot(file)}
    except KeyError as e:
        raise HTTPException(status_code=404, detail="快照不存在") from e
