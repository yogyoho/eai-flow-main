# EAI-CUSTOM: forked from app.extensions.contract_price.routers (geo-sample-bank Phase 1).
# 所有端点统一 require_permission("geo_samples:access")（最粗粒度，与 cpa 模式一致；
# 细粒度审核权限留待有真实角色需求再加）。
"""Geo sample bank management API — all functional areas.

Mounted into the Gateway under ``/api/extensions/geo-samples``. Endpoints:

  Functional area 1 (documents): GET /documents, GET /documents/{document_id},
                                 POST /documents/upload, POST /documents/suggest-id
  Functional area 2 (pipeline)  : POST /documents/{document_id}/parse,
                                 POST /documents/{document_id}/redact
  Functional area 3 (review)    : GET /documents/{document_id}/redactions,
                                 POST /documents/{document_id}/review
  Functional area 4 (pipeline)  : POST /pipeline/compile（模块级编译）
  Functional area 5 (tasks)     : GET /runs
"""

from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db

from . import crud, schemas, service, storage, title_parser

router = APIRouter(prefix="/api/extensions/geo-samples", tags=["Geo Sample Bank"])
_PERM = Depends(require_permission("geo_samples:access"))


# --- Functional area 1: documents -------------------------------------------


@router.get("/documents")
async def list_documents(stage: str | None = None, mineral: str | None = None, status: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_documents(db, stage=stage, mineral=mineral, status=status, skip=skip, limit=limit)
    return {"items": [schemas.DocumentOut.model_validate(r).model_dump() for r in rows], "skip": skip, "limit": limit}


@router.get("/documents/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    return schemas.DocumentOut.model_validate(doc).model_dump()


@router.post("/documents/upload")
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    report_id: str = Form(...),
    stage: str = Form("exploration"),
    mineral: str = Form("copper"),
    year: int | None = Form(None),
    region: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    _: object = _PERM,
):
    name = file.filename or ""
    if not name.lower().endswith((".docx", ".pdf")):
        raise HTTPException(400, "仅支持 .docx/.pdf")
    try:
        meta = schemas.UploadMeta(report_id=report_id, stage=stage, mineral=mineral, year=year, region=region)
    except ValidationError as exc:
        raise HTTPException(400, f"样例元数据非法：{exc.errors()[0].get('msg', 'validation error')}") from exc
    if meta.stage not in schemas.ALLOWED_STAGES or meta.mineral not in schemas.ALLOWED_MINERALS:
        raise HTTPException(400, "stage/mineral 取值非法")
    if await crud.get_document_by_report_id(db, meta.report_id):
        raise HTTPException(409, f"report_id {meta.report_id} 已存在")
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    digest = hashlib.sha256(data).hexdigest()
    dup = await crud.find_duplicate_document(db, digest, exclude_uri=None)
    if dup is not None:
        raise HTTPException(409, "相同内容的样例已存在（file_hash 命中）")
    file_type = "docx" if name.lower().endswith(".docx") else "pdf"
    # storage.put_raw 是阻塞 MinIO 调用——必须 asyncio.to_thread（blocking-IO 门，同 service.py 约定）。
    raw_uri = await asyncio.to_thread(storage.put_raw, meta.report_id, name, data)
    # 已知 Phase 1 窗口：put_raw 成功而 create_document 失败会留下孤儿 raw 对象（无 DB 行）；接受。
    doc = schemas.DocumentOut.model_validate(
        await crud.create_document(db, report_id=meta.report_id, file_name=name, file_hash=digest, file_type=file_type, stage=meta.stage, mineral=meta.mineral, year=meta.year, region=meta.region, raw_uri=raw_uri)
    )
    run = await crud.create_run(db, doc.id, "parse")
    background.add_task(service.run_parse, db, doc.id, run.id)
    return {"document": doc.model_dump(), "run_id": run.id}


async def suggest_id_impl(db: AsyncSession, title: str) -> dict:
    """题名 → 结构化 report_id 建议（batch-cli T2）。解析成功（mineral+stage 齐备）→
    gsb-{stage}-{mineral} 组内顺延；解析失败 → gsb-auto 组顺延（confidence 沿用 parse_title）。

    返回纯 dict（题名解析字段 + report_id）；实现函数与端点分离便于直测。
    """
    parsed = title_parser.parse_title(title)
    if parsed["mineral"] and parsed["stage"]:
        stage_code = {"survey": "pu", "detail": "xc", "exploration": "kc"}[parsed["stage"]]
        mineral_code = {"copper": "cu", "coal": "co", "gold": "au", "iron": "fe", "lead_zinc": "pbzn", "other": "ot"}[parsed["mineral"]]
        report_id = await crud.next_report_id(db, f"gsb-{stage_code}-{mineral_code}")
    else:
        report_id = await crud.next_report_id(db, "gsb-auto")
    return {**parsed, "report_id": report_id}


@router.post("/documents/suggest-id")
async def suggest_id(title: str = Query(...), db: AsyncSession = Depends(get_db), _: object = _PERM):
    return await suggest_id_impl(db, title)


# --- Functional area 2: parse / redact pipeline ------------------------------


@router.post("/documents/{document_id}/parse")
async def parse_document(document_id: str, background: BackgroundTasks, db: AsyncSession = Depends(get_db), _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    if await crud.has_running_run(db, document_id, "redact"):
        raise HTTPException(409, "脱敏任务在跑——稍后再解析")
    if doc.status not in ("uploaded", "failed", "parsed"):
        raise HTTPException(409, f"当前状态 {doc.status} 不允许重新解析（reviewed 章稿已定稿）")
    await crud.sweep_stale_runs(db)
    if await crud.has_running_run(db, document_id, "parse"):
        raise HTTPException(409, "解析任务已在跑")
    run = await crud.create_run(db, document_id, "parse")
    background.add_task(service.run_parse, db, document_id, run.id)
    return {"run_id": run.id}


@router.post("/documents/{document_id}/redact")
async def redact_document(document_id: str, background: BackgroundTasks, db: AsyncSession = Depends(get_db), _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    if doc.status != "parsed":
        raise HTTPException(409, f"仅 parsed 状态可脱敏（当前 {doc.status}）")
    # 双重闸门：状态为 parsed 之外，还须无在跑的 parse——parse 进行中 work_uri 可能写入一半。
    await crud.sweep_stale_runs(db)
    if await crud.has_running_run(db, document_id, "parse"):
        raise HTTPException(409, "解析任务在跑，work_uri 可能写入中——稍后再脱敏")
    if await crud.has_running_run(db, document_id, "redact"):
        raise HTTPException(409, "脱敏任务已在跑")
    run = await crud.create_run(db, document_id, "redact")
    background.add_task(service.run_redact, db, document_id, run.id)
    return {"run_id": run.id}


# --- Functional area 3: review -----------------------------------------------


@router.get("/documents/{document_id}/redactions")
async def list_redactions(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_redactions(db, document_id)
    return {"items": [schemas.RedactionOut.model_validate(r).model_dump() for r in rows]}


@router.post("/documents/{document_id}/review")
async def review_document(document_id: str, body: schemas.ReviewRequest, db: AsyncSession = Depends(get_db), _: object = _PERM):
    if await crud.get_document(db, document_id) is None:
        raise HTTPException(404, "样例不存在")
    try:
        await service.apply_review(db, document_id, body.decision, body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    doc = await crud.get_document(db, document_id)
    return schemas.DocumentOut.model_validate(doc).model_dump()


# --- Functional area 4: module-level compile ---------------------------------


@router.post("/pipeline/compile")
async def compile_pipeline(background: BackgroundTasks, stage: str | None = None, mineral: str | None = None, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """模块级编译：reviewed 全量（可选 stage/mineral 过滤）→ 子进程 bank_compile → RAGFlow 分发。

    互斥：任意 running 的 compile run 存在 → 409（先 sweep 超龄自愈，防网关重启残留行永久锁死）；
    无 reviewed 样例 → 400。run 行 document_id=None（模块级，无单体文档）。
    """
    await crud.sweep_stale_runs(db)
    if await crud.has_running_compile_run(db):
        raise HTTPException(409, "编译任务已在跑")
    if not await crud.list_reviewed(db, stage, mineral):
        raise HTTPException(400, "无 reviewed 状态的样例可编译")
    run = await crud.create_run(db, None, "compile")
    background.add_task(service.run_compile, db, run.id, stage, mineral)
    return {"run_id": run.id}


# --- Functional area 5: tasks -------------------------------------------------


@router.get("/runs")
async def list_runs(db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_recent_runs(db, limit=50)
    return {"items": [schemas.RunOut.model_validate(r).model_dump() for r in rows]}
