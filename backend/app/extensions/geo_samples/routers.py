# EAI-CUSTOM: forked from app.extensions.contract_price.routers (geo-sample-bank Phase 1).
# 所有端点统一 require_permission("geo_samples:access")（最粗粒度，与 cpa 模式一致；
# 细粒度审核权限留待有真实角色需求再加）。
"""Geo sample bank management API — all functional areas.

Mounted into the Gateway under ``/api/extensions/geo-samples``. Endpoints:

  Functional area 1 (documents): GET /documents, GET /documents/{document_id},
                                 POST /documents/upload, POST /documents/suggest-id,
                                 DELETE /documents/{document_id}
  Functional area 2 (pipeline)  : POST /documents/{document_id}/parse,
                                 POST /documents/{document_id}/redact,
                                 POST /documents/parse-batch（defer 行受控启动）
  Functional area 3 (review)    : GET /documents/{document_id}/redactions,
                                 POST /documents/{document_id}/review
  Functional area 4 (pipeline)  : POST /pipeline/compile（模块级编译）
  Functional area 5 (tasks)     : GET /runs
  Functional area 6 (ore_pack)  : POST /ore-packs/extract, GET /ore-packs/drafts,
                                 POST /ore-packs/drafts/{id}/approve,
                                 POST /ore-packs/drafts/{id}/reject
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db

from . import crud, ore_pack_extract, ore_pack_schema, schemas, service, storage, title_parser

router = APIRouter(prefix="/api/extensions/geo-samples", tags=["Geo Sample Bank"])
_PERM = Depends(require_permission("geo_samples:access"))


# --- Functional area 1: documents -------------------------------------------


@router.get("/documents")
async def list_documents(stage: str | None = None, mineral: str | None = None, status: str | None = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_documents(db, stage=stage, mineral=mineral, status=status, skip=skip, limit=limit)
    # total 与 items 同三过滤（分页总数；batch-cli T4）——前端「下一页」可改用本值，
    # 但现以 docs.length < pageSize 判尾页（翻页与筛选期间 total 可能瞬时滞后）。
    total = await crud.count_documents(db, stage=stage, mineral=mineral, status=status)
    return {"items": [schemas.DocumentOut.model_validate(r).model_dump() for r in rows], "skip": skip, "limit": limit, "total": total}


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
    # 批量导入闸门（batch-cli P4 T1）：true → 仅落行（status=uploaded），不 create_run、
    # 不起后台 parse——1000 份扫描件逐份即时入队（单份 OCR 最长 1800s）会击穿网关；
    # defer 行由 parse-batch 端点（Task 3）受控启动。响应省略 run_id 键（非 null）。
    defer_parse: bool = Form(False),
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
    run = None
    if not defer_parse:
        run = await crud.create_run(db, doc.id, "parse")
        background.add_task(service.run_parse, db, doc.id, run.id)
    resp = {"document": doc.model_dump()}
    if run is not None:
        resp["run_id"] = run.id
    return resp


async def suggest_id_impl(db: AsyncSession, title: str) -> dict:
    """题名 → 结构化 report_id 建议（batch-cli T2）。解析成功（mineral+stage 齐备）→
    gsb-{stage}-{mineral} 组内顺延；解析失败 → gsb-auto 组顺延（confidence 沿用 parse_title）。

    返回纯 dict（题名解析字段 + report_id）；实现函数与端点分离便于直测。
    """
    parsed = title_parser.parse_title(title)
    # .get() 而非 [...]：未来词表漂移（title_parser 新增 slug 而此表未同步）时落 gsb-auto，不 500。
    stage_code = {"survey": "pu", "detail": "xc", "exploration": "kc"}.get(parsed["stage"])
    mineral_code = {"copper": "cu", "coal": "co", "gold": "au", "iron": "fe", "lead_zinc": "pbzn", "other": "ot"}.get(parsed["mineral"])
    if stage_code and mineral_code:
        report_id = await crud.next_report_id(db, f"gsb-{stage_code}-{mineral_code}")
    else:
        report_id = await crud.next_report_id(db, "gsb-auto")
    return {**parsed, "report_id": report_id}


@router.post("/documents/suggest-id")
async def suggest_id(title: str = Query(...), db: AsyncSession = Depends(get_db), _: object = _PERM):
    return await suggest_id_impl(db, title)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """删除样例（batch-cli T3, spec 2026-09-03）：MinIO 三前缀对象（raw/work/clean，逐一判 None）
    best-effort 删除（storage.delete_object_by_uri，阻塞调用走 to_thread）+ 行删除。

    审计语义：gsb_redactions / gsb_run_history 故意不建 FK——文档删除后流水保留
    （document_id 悬空），跑批审计链不随行消失。compiled 禁删：编译产物已并入技能
    references（回收机制未设计，spec §5.3）。
    """
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    # 网关重启遗留的超龄 running 行自愈（同 parse/redact/compile 端点惯例）——否则
    # 陈旧 running 行以误导文案 409 锁删除达 60 分钟。
    await crud.sweep_stale_runs(db)
    if doc.status == "compiled":
        raise HTTPException(409, "已编译样例不可删除（编译产物在技能 references 中）")
    if await crud.has_running_run(db, document_id, "parse") or await crud.has_running_run(db, document_id, "redact"):
        raise HTTPException(409, "parse/redact 任务在跑——稍后再删除")
    for uri in (doc.raw_uri, doc.work_uri, doc.clean_uri):
        if uri:
            await asyncio.to_thread(storage.delete_object_by_uri, uri)
    await crud.delete_document(db, document_id)
    return {"deleted": True, "report_id": doc.report_id}


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


async def parse_batch_impl(db: AsyncSession, limit: int, background: BackgroundTasks) -> dict:
    """list_uploaded → 逐行 create_run + 入队（实现函数与端点分离便于直测，同 suggest_id_impl 模式）。

    行级 running-parse 守卫：跳过而非 409（批处理语义）——上批调度仍在跑的行不建重复 run
    （防重叠批次浪费 OCR/重复 run 行）；陈旧行由端点先行的 sweep_stale_runs 自愈后才过本守卫。
    DB 层互斥（P5 ledger A）：行级守卫是 check-then-insert，两并发批次可同时过检——
    create_run 提交撞部分唯一索引 uq_gsb_run_running（migrate_db 建）时 IntegrityError →
    409「该样例解析已在调度」终止批次（真互斥冲突，非可跳过的陈旧行；会话先 rollback 复位）。
    scheduled/ids 只计实际调度的行，skipped_running 计跳过数。
    """
    ids: list[str] = []
    skipped = 0
    for doc in await crud.list_uploaded(db, limit=limit):
        if await crud.has_running_run(db, doc.id, "parse"):
            skipped += 1
            continue
        try:
            run = await crud.create_run(db, doc.id, "parse")
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "该样例解析已在调度") from exc
        background.add_task(service.run_parse, db, doc.id, run.id)
        ids.append(run.id)
    return {"scheduled": len(ids), "ids": ids, "skipped_running": skipped}


@router.post("/documents/parse-batch")
async def parse_batch(background: BackgroundTasks, limit: int = Query(5, ge=1, le=20), db: AsyncSession = Depends(get_db), _: object = _PERM):
    """批量触发 defer 行解析（batch-cli P4 T3，spec 2026-09-04）：把 defer_parse 上传（P4 T1）
    留下的 status=uploaded 行按 created_at asc 取前 N 行，逐行建 parse run + 后台 run_parse——
    等价于逐份调 POST /documents/{id}/parse，但一次请求成批。

    并发上限语义：limit 的 Query le=20 即天然并发闸（不另设信号量）——防 defer 批量导入后的
    OCR 风暴原样搬到触发阶段（单份 OCR 最长 1800s）；1000 行分 50 批手动/脚本触发。

    互斥取舍：对每行不做 409（单体 parse 端点的双向互斥在此弱化）——已有 running parse 的行
    静默跳过（批处理语义，响应 skipped_running 计数），防重叠批次浪费 OCR；行刚 defer 完必无
    在跑任务，网关重启遗留的陈旧 running 行由先行 sweep_stale_runs 自愈（模块惯例）后才过守卫。
    行级守卫过检后仍可能与他方批次在 check-then-insert 窗口内撞车——部分唯一索引
    uq_gsb_run_running（P5 ledger A，migrate_db 建）在 DB 层收口：IntegrityError → 409，双保险。
    零行 → {"scheduled": 0, "ids": [], "skipped_running": 0}，不视为错误。
    """
    await crud.sweep_stale_runs(db)
    return await parse_batch_impl(db, limit=limit, background=background)


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


async def _ensure_slices_kb_registered(db: AsyncSession, dataset_id: str | None) -> bool:
    """把切片库注册进 knowledge_bases 表（只读系统库；owner 固定 admin，同法规库
    LawService._ensure_kb_registered 模式——避免触发者账号软删留下孤儿 owner）。

    按展示名幂等：无行→插入（access_type=public，挂 dataset id）；已有行但缺
    ragflow_dataset_id→回填（历史手工建库场景）。admin 缺失→False（跳过注册，
    dataset 本身已建，不让注册失败拖垮初始化）。
    """
    from sqlalchemy import select as sa_select

    from app.extensions.models import KnowledgeBase, User

    owner_result = await db.execute(sa_select(User.id).where(User.email == "admin@eai-flow.com"))
    owner_id = owner_result.scalar_one_or_none()
    if owner_id is None:
        return False
    existing = await db.execute(sa_select(KnowledgeBase).where(KnowledgeBase.name == service.GEO_SLICES_KB_NAME))
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(
            KnowledgeBase(
                name=service.GEO_SLICES_KB_NAME,
                description="地质样例库编译切片：样例过审后由行级「编译」自动写入并分发 RAGFlow（只读，禁手动上传）",
                owner_id=owner_id,
                access_type="public",
                kb_type="ragflow",
                ragflow_dataset_id=dataset_id,
                chunk_method="naive",
                status="active",
            )
        )
        await db.commit()
        return True
    if dataset_id and not row.ragflow_dataset_id:
        row.ragflow_dataset_id = dataset_id
        await db.commit()
    return True


@router.post("/pipeline/init-ragflow")
async def init_ragflow_dataset(db: AsyncSession = Depends(get_db), _: object = _PERM):
    """初始化（幂等收敛）地质样例库 RAGFlow 切片数据集——部署后手动点一次即可让编译分发生效。

    按固定名 GSB_RAGFLOW_DATASET_NAME 查找：缺失 → 按种子（naive）创建；已存在 → aligned。
    同步把「固体矿产报告切片库」注册进 knowledge_bases 表（只读系统库，前端按名识别）。
    分发解析链（service.resolve_ragflow_dataset_id）= env 覆写 > 本同名库 > skipped，
    因此按钮建库后无需改 env 即生效；env 仍保留给离线部署做覆写口。
    """
    from app.extensions.config import get_extensions_config
    from app.extensions.knowledge import client as ragflow_client_mod

    cfg = get_extensions_config().ragflow
    if not cfg.api_key:
        raise HTTPException(503, "RAGFlow 服务未配置（缺 API Key）")
    client = ragflow_client_mod.RAGFlowClient(api_key=cfg.api_key, base_url=cfg.base_url)
    try:
        if not await client.is_available():
            raise HTTPException(503, "RAGFlow 服务不可用")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"RAGFlow 连接失败: {exc}") from exc

    existing = await client.get_dataset_by_name(service.GSB_RAGFLOW_DATASET_NAME)
    if existing:
        dataset_id = existing.get("id")
        status = "aligned"
    else:
        result = await client.create_dataset(
            name=service.GSB_RAGFLOW_DATASET_NAME,
            description="地质样例库编译切片（bank_compile 分发，EAI-CUSTOM）",
            chunk_method=service._GSB_DATASET_SEED["chunk_method"],
            parser_config=dict(service._GSB_DATASET_SEED["parser_config"]),
        )
        dataset_id = (result.get("data") or {}).get("id")
        status = "created"
    if not dataset_id:
        raise HTTPException(502, "RAGFlow 建库失败（响应缺 dataset id）")
    kb_registered = await _ensure_slices_kb_registered(db, dataset_id)
    return {"status": status, "dataset_id": dataset_id, "kb_registered": kb_registered}


@router.post("/pipeline/compile")
async def compile_pipeline(background: BackgroundTasks, stage: str | None = None, mineral: str | None = None, document_id: str | None = Query(None), db: AsyncSession = Depends(get_db), _: object = _PERM):
    """模块级编译：reviewed 全量（可选 stage/mineral 过滤）或单文档域（document_id）→
    子进程 bank_compile → RAGFlow 分发。

    document_id 给定时为逐行编译分发（前端操作列按钮）：该样例须 reviewed/compiled
    （重编译幂等）；互斥仍为模块级全局（同一时刻仅一个编译 run 写共享 references）。
    互斥：任意 running 的 compile run 存在 → 409（先 sweep 超龄自愈，防网关重启残留行
    永久锁死）；无 reviewed 样例 → 400。run 行 document_id=None（模块级，无单体文档）。
    """
    await crud.sweep_stale_runs(db)
    if await crud.has_running_compile_run(db):
        raise HTTPException(409, "编译任务已在跑")
    if document_id is not None:
        doc = await crud.get_document(db, document_id)
        if doc is None:
            raise HTTPException(404, "样例不存在")
        if doc.status not in ("reviewed", "compiled"):
            raise HTTPException(409, f"仅 reviewed/compiled 样例可编译（当前 {doc.status}）")
    elif not await crud.list_reviewed(db, stage, mineral):
        raise HTTPException(400, "无 reviewed 状态的样例可编译")
    run = await crud.create_run(db, None, "compile")
    background.add_task(service.run_compile, db, run.id, stage, mineral, document_id)
    return {"run_id": run.id}


# --- Functional area 5: tasks -------------------------------------------------


@router.get("/runs")
async def list_runs(db: AsyncSession = Depends(get_db), _: object = _PERM):
    rows = await crud.list_recent_runs(db, limit=50)
    return {"items": [schemas.RunOut.model_validate(r).model_dump() for r in rows]}


# --- Functional area 6: ore_pack incubation（P5 T5）---------------------------
# LLM 批量抽取草稿 → gsb_ore_pack_drafts → 人审（approve 落 repo ore_packs/<mineral>.json）。


@router.post("/ore-packs/extract")
async def extract_ore_pack(body: schemas.OrePackExtractRequest, background: BackgroundTasks, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """触发 {mineral} 矿种草稿抽取（后台）：切片载入（截断 8000 字符/片）→ LLM →
    validate_ore_pack → 草稿落 gsb_ore_pack_drafts（errors 非空仍落表，人审可见）。

    词表单源裁决：mineral ∉ 5 production slug → 400（other 不孵化）。切片路径须在仓库根内
    （LLM 输入信任边界）。响应 slices_hash 供前端与落表草稿对账。
    """
    if body.mineral not in ore_pack_schema.KNOWN_SLUGS:
        raise HTTPException(400, f"mineral 非法: {body.mineral}（须 ∈ {sorted(ore_pack_schema.KNOWN_SLUGS)}；other 不孵化）")
    try:
        texts = await asyncio.to_thread(ore_pack_extract.load_slices, body.slice_paths)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    background.add_task(ore_pack_extract.run_extract, db, body.mineral, texts)
    return {"queued": True, "mineral": body.mineral, "slices_hash": ore_pack_extract.slices_hash(texts)}


@router.get("/ore-packs/drafts")
async def ore_pack_drafts(mineral: str | None = None, review_status: str | None = None, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """草稿清单（created desc；draft_json/errors JSON 解码后返回，人审 tab 消费）。"""
    rows = await crud.list_drafts(db, mineral=mineral, review_status=review_status)
    return {"items": [crud.draft_payload(r) for r in rows]}


async def _get_draft_or_404(db: AsyncSession, draft_id: str):
    draft = await crud.get_draft(db, draft_id)
    if draft is None:
        raise HTTPException(404, "草稿不存在")
    if draft.review_status != "draft":
        raise HTTPException(409, f"草稿已审阅（{draft.review_status}）")
    return draft


@router.post("/ore-packs/drafts/{draft_id}/approve")
async def ore_pack_approve(draft_id: str, body: schemas.DraftReviewRequest | None = None, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """过审 → repo ore_packs/<mineral>.json 落盘（dev bind-mount 直写；离线 caveat 沿
    MANUAL-UPGRADE.md runbook）→ approved 落账。approve 前置 = errors==[]（落表时与
    落盘前双重 validate——schema 常量可能自抽取起收紧）。

    响应携带 standards_index 扩容义务清单（全部【待核实】节点）：过审 ≠ 义务完成，
    阈值仍须人工对照规范原文录入 standards_index（spec §9 Phase 4）。
    """
    draft = await _get_draft_or_404(db, draft_id)
    doc = json.loads(draft.draft_json) if draft.draft_json else None
    # 双闸：① errors 列（抽取时人审可见的判词，plan：approve 前置=errors 空）；
    # ② 当场重校验（schema 常量自抽取起收紧时拦下，防坏包落 repo）。
    recorded = json.loads(draft.errors) if draft.errors else []
    fresh = ore_pack_schema.validate_ore_pack(doc) if isinstance(doc, dict) else ["草稿无有效 JSON"]
    if recorded or fresh:
        raise HTTPException(409, f"草稿校验未过，禁止 approve：{'；'.join(recorded + fresh)}")
    written = await asyncio.to_thread(ore_pack_extract.write_ore_pack_file, draft.mineral, doc)
    row = await crud.review_draft(db, draft_id, "approved", body.note if body else None)
    return {**crud.draft_payload(row), "written": written, "standards_index_obligations": ore_pack_extract.pending_obligations(doc)}


@router.post("/ore-packs/drafts/{draft_id}/reject")
async def ore_pack_reject(draft_id: str, body: schemas.DraftReviewRequest | None = None, db: AsyncSession = Depends(get_db), _: object = _PERM):
    """驳回草稿（repo 零写入）——T6 DraftsView 的另一审阅分支。"""
    await _get_draft_or_404(db, draft_id)
    row = await crud.review_draft(db, draft_id, "rejected", body.note if body else None)
    return crud.draft_payload(row)
