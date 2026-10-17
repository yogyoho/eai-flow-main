"""Contract price analysis management API — all functional areas.

Mounted into the Gateway under ``/api/extensions/contract-price``. Endpoints:

  Functional area 1 (documents): GET/DELETE /documents
  Functional area 2 (clusters) : GET /clusters, GET /clusters/{id},
                                 POST /clusters/{id}/confirm, POST /clusters/merge,
                                 POST /items/{id}/move
  Functional area 3 (items)    : GET /items, PATCH /items/{id}
  Functional area 4 (tasks)    : GET /runs, GET /runs/{id}/excel
  Functional area 5 (config)   : GET/PUT /config
  Functional area 6 (dashboard): GET /dashboard
  Library (cpa v3)             : /library/folders*, /library/files* — 合同文件库 (EAI-CUSTOM)
  Terms (cpa v3)               : GET/POST /terms, PATCH/DELETE /terms/{id} — 货物分类术语 (EAI-CUSTOM)
  RAGFlow (EAI-CUSTOM)         : POST /ragflow/init, GET /ragflow/status,
                                 POST /library/files/{file_id}/ragflow-sync — 共享租户知识库
  Pipeline trigger             : POST /pipeline/run, GET /pipeline/runs/{id}/status
"""

import asyncio
import hashlib
import json
import logging
import os
import urllib.parse
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.contract_price import crud, evolution, ragflow_setup, service, storage  # EAI-CUSTOM: ragflow_setup
from app.extensions.contract_price.models import CpaDocument, CpaItem, CpaLibraryFolder
from app.extensions.contract_price.schemas import (
    BatchDeleteRequest,
    ClusterConfirm,
    ClusterDetail,
    ClusterMerge,
    ClusterOut,
    ClusterUpdate,
    ConfigOut,
    ConfigUpdate,
    DashboardOut,
    DocumentConfirm,
    DocumentOut,
    DocumentUpdate,
    ItemMove,
    ItemOut,
    ItemUpdate,
    LibraryAnalyzeOut,
    LibraryFileMove,
    LibraryFileOut,
    LibraryFolderIn,
    LibraryFolderOut,
    LibraryFolderUpdate,
    Page,
    PipelineRunRequest,
    PipelineRunResponse,
    RunOut,
    TermCreate,
    TermOut,
    TermUpdate,
)
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/contract-price", tags=["Contract Price Analysis"])


# --- 合同文件库 (EAI-CUSTOM cpa v3, spec 2026-10-14 §1.3) --------------------


@router.get("/library/folders")
async def list_library_folders(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    return {"items": await crud.list_library_folders(db)}


@router.post("/library/folders", response_model=LibraryFolderOut)
async def create_library_folder(
    body: LibraryFolderIn,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="文件夹名不能为空")
    try:
        return await crud.create_library_folder(db, body.name.strip(), body.parent_id)
    except ValueError as exc:
        # 父文件夹不存在 / 同级同名——都是客户端可修正的冲突
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/library/folders/{folder_id}", response_model=LibraryFolderOut)
async def update_library_folder(
    folder_id: UUID,
    body: LibraryFolderUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    fields = body.model_dump(exclude_unset=True)  # 显式 "parent_id": null（移回根）必须保留，exclude_none 会静默丢弃
    if "name" in fields and not (fields["name"] or "").strip():
        raise HTTPException(status_code=422, detail="文件夹名不能为空")
    try:
        row = await crud.update_library_folder(db, folder_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return row


@router.delete("/library/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_folder_endpoint(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    if not await crud.delete_library_folder(db, folder_id):
        raise HTTPException(status_code=409, detail="文件夹非空（含子文件夹或文件），请先移走内容")


@router.get("/library/files")
async def list_library_files_endpoint(
    folder_id: str | None = Query(None, description="空/root=根;否则文件夹 UUID"),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    # EAI-CUSTOM (bug-3306): 返回 {"items":[...]}——与 /library/folders 端点形状一致。
    # 曾返回裸数组而前端按 {items} 解析 → LibraryView 全列表静默空 + 统计行 TypeError。
    try:
        fid = None if folder_id in (None, "", "root") else UUID(folder_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="folder_id 需为 UUID")
    return {"items": await crud.list_library_files(db, fid)}


@router.post("/library/files/upload")
async def upload_library_files(
    folder_id: str = Form(""),
    paths: str = Form("[]"),  # 与 files 等长的相对路径 JSON 数组（webkitdirectory 用；""=不建子树）
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """多文件上传（含 webkitdirectory）。同文件夹同内容 → reused 复用不重复入库。
    paths 提供相对路径段（如 "设备采购/附表"）时自动逐级建子文件夹（幂等）。"""
    try:
        fid: UUID | None = UUID(folder_id) if folder_id and folder_id != "root" else None
    except ValueError:
        raise HTTPException(status_code=422, detail="folder_id 需为 UUID")
    if fid is not None and await db.get(CpaLibraryFolder, fid) is None:
        raise HTTPException(status_code=404, detail="目标文件夹不存在")
    try:
        rel_paths = json.loads(paths)
        if not isinstance(rel_paths, list) or len(rel_paths) != len(files):
            rel_paths = [""] * len(files)
    except (TypeError, ValueError):  # TypeError: 直调（测试）时 paths 是 FastAPI Form 默认对象而非 str
        rel_paths = [""] * len(files)
    out: list[dict] = []
    for f, rel in zip(files, rel_paths):
        name = f.filename or ""
        if not name.lower().endswith((".pdf", ".docx")):
            out.append({"file_name": name, "reused": False, "error": "仅接受 .pdf / .docx"})
            continue
        data = await f.read()
        if not data:
            out.append({"file_name": name, "reused": False, "error": "空文件"})
            continue
        # 相对路径 → 目标文件夹（逐级幂等建目录；根目录传 "" 时目标仍为 fid）。
        # 先校验段合法性（质量审查 Task 5）: 空段/./.. /超长 → per-item error;>32 段拒绝。
        target = fid
        segments = [seg.strip() for seg in str(rel or "").replace("\\", "/").split("/")[:-1]]
        bad = next((seg for seg in segments if not seg or seg in (".", "..") or len(seg) > 255), None)
        if bad is not None:
            out.append({"file_name": name, "reused": False, "error": f"路径段非法: {bad}"})
            continue
        if len(segments) > 32:
            out.append({"file_name": name, "reused": False, "error": "子目录层级过深（>32 段）"})
            continue
        if segments:
            target = await crud.ensure_folder_path(db, fid, segments)
        digest = hashlib.sha256(data).hexdigest()
        dup = await crud.find_library_duplicate(db, target, digest)
        if dup is not None:
            out.append({"file_name": name, "file_id": dup.id, "reused": True})
            continue
        ext = os.path.splitext(name)[1].lstrip(".").lower() or "pdf"
        key = storage.library_key(str(target) if target else "root", digest, name)
        await asyncio.to_thread(storage.upload_bytes, key, data, f.content_type or "application/octet-stream")
        row = await crud.create_library_file(
            db,
            folder_id=target,
            file_name=name,
            storage_key=key,
            file_hash=digest,
            file_size=len(data),
            file_type=ext,
        )
        out.append({"file_name": name, "file_id": row.id, "reused": False})
    return {"items": out}


@router.get("/library/files/{file_id}/content")
async def library_file_content(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """PDF inline 内嵌预览;docx 附件下载（浏览器不渲染 docx）。"""
    lf = await crud.get_library_file(db, file_id)
    if lf is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        data = await asyncio.to_thread(storage.get_object, lf.storage_key)
    except Exception:
        raise HTTPException(status_code=404, detail="文件对象不存在")
    is_pdf = (lf.file_type or "").lower() == "pdf"
    media = "application/pdf" if is_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    quoted = urllib.parse.quote(lf.file_name or "file")
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": (f"{'inline' if is_pdf else 'attachment'}; filename=\"library.{lf.file_type or 'bin'}\"; filename*=UTF-8''{quoted}")},
    )


@router.get("/library/files/{file_id}/items")
async def library_file_items(
    file_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """该文件（按 file_hash 匹配）解析出的分项清单——只读查阅。"""
    lf = await crud.get_library_file(db, file_id)
    if lf is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    doc = await crud.find_parsed_document_by_hash(db, lf.file_hash)
    if doc is None:
        raise HTTPException(status_code=404, detail="该文件尚未解析（先「加入解析」）")
    items, total = await crud.list_items(db, skip=skip, limit=limit, document_id=doc.id)
    return {
        "document": {"id": doc.id, "file_name": doc.file_name, "parse_status": doc.parse_status},
        "items": [ItemOut.model_validate(i).model_dump() for i in items],
        "total": total,
    }


@router.post("/library/files/{file_id}/analyze", response_model=LibraryAnalyzeOut)
async def analyze_library_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """显式加入解析，语义对齐 documents/upload：
    ① 同内容已解析 → already（直接看清单）;failed/needs_review 不短路、重新排队重试;
    ② 同名不同内容已存在 → 409 防统计污染;
    ③ MinIO 服务端拷 library/... → 扫描区根 + 建 pending 行，下一轮解析自动拾取。"""
    lf = await crud.get_library_file(db, file_id)
    if lf is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    doc = await crud.find_parsed_document_by_hash(db, lf.file_hash)
    if doc is not None:
        if doc.parse_status in ("pending", "parsing"):
            # 同内容已有任务在队列/解析中——不重复拷贝入队，也不误报"已解析过"
            return LibraryAnalyzeOut(
                status="already",
                document_id=doc.id,
                message=f"该内容已有解析任务进行中（{doc.file_name}），请稍候刷新",
            )
        if doc.parse_status == "parsed":
            return LibraryAnalyzeOut(
                status="already",
                document_id=doc.id,
                message=f"该内容已解析过（{doc.file_name}），可直接查看清单",
            )
        # failed / needs_review → 不被 "already" 短路，落到下面重新排队
        # （create_pending_document 按 storage_uri upsert 复用同名行——正是重试语义）
    conflict = await crud.find_document_by_storage_key(db, lf.file_name)
    if conflict is not None and conflict.file_hash != lf.file_hash:
        raise HTTPException(
            status_code=409,
            detail=f"扫描区已存在同名但内容不同的合同「{conflict.file_name}」，请先在合同解析页处理或重命名后重试",
        )
    await asyncio.to_thread(storage.copy_object, lf.storage_key, lf.file_name)
    await crud.create_pending_document(
        db,
        storage_uri=f"s3://{storage.BUCKET}/{lf.file_name}",
        file_name=lf.file_name,
        file_hash=lf.file_hash,
        file_type=lf.file_type or "pdf",
        size=lf.file_size,
    )
    return LibraryAnalyzeOut(status="queued", message="已加入解析队列，下一轮解析自动拾取")


@router.patch("/library/files/{file_id}", response_model=LibraryFileOut)
async def move_library_file_endpoint(
    file_id: UUID,
    body: LibraryFileMove,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    try:
        row = await crud.move_library_file(db, file_id, body.folder_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    # parse_status 占位 "unparsed"——move 后前端整体 refetch，真实值由列表接口给出
    return LibraryFileOut(
        id=row.id,
        folder_id=row.folder_id,
        file_name=row.file_name,
        file_size=row.file_size,
        file_type=row.file_type,
        uploaded_at=row.uploaded_at,
        parse_status="unparsed",
        document_id=None,
    )


@router.delete("/library/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_file_endpoint(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    key = await crud.delete_library_file(db, file_id)
    if key is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    await asyncio.to_thread(storage.delete_object, key)  # best-effort，静默容忍缺失


# --- 货物分类术语 (EAI-CUSTOM cpa v3, spec 2026-10-14 §2.4) ------------------


@router.get("/terms")
async def list_terms_endpoint(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """术语列表 + 已关联分项计数（canonical∪别名 归一化求和;空库为 0）。"""
    terms = await crud.list_terms(db)
    counts = await crud.term_item_count_map(db)
    items = []
    for t in terms:
        names = [t.canonical, *(t.aliases or [])]
        items.append(
            TermOut(
                id=t.id, canonical=t.canonical, aliases=t.aliases or [],
                enabled=t.enabled, source=t.source,
                alias_count=len(t.aliases or []),
                item_count=sum(counts.get(crud.normalize_term(n), 0) for n in names),
            ).model_dump()
        )
    return {"items": items}


@router.post("/terms", response_model=TermOut)
async def create_term_endpoint(
    body: TermCreate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    canonical = (body.canonical or "").strip()
    if not canonical:
        raise HTTPException(status_code=422, detail="规范名不能为空")
    aliases = [a.strip() for a in (body.aliases or []) if a.strip()]
    # 归一化去重（保序;alias_count 不虚高）
    seen: set = set()
    deduped: list = []
    for a in aliases:
        k = crud.normalize_term(a)
        if k and k not in seen:
            seen.add(k)
            deduped.append(a)
    aliases = deduped
    # 请求内自撞: 规范名 ∈ 自身归一化别名集 → 422（先自撞,再对其它术语 409）
    if crud.normalize_term(canonical) in seen:
        raise HTTPException(status_code=422, detail="规范名与自身别名冲突")
    # 归一化撞车防护: 与既有术语 canonical/别名冲突 → 409（同 M1 同级同名语义）
    # 评审注: list_terms 并发合并竞态下可能返回重复 canonical 行——任一行撞即 409,
    # 语义不变;去重属显示层职责,此处不处理。
    for t in await crud.list_terms(db):
        existing_names = {crud.normalize_term(n) for n in [t.canonical, *(t.aliases or [])]}
        if crud.normalize_term(canonical) in existing_names or (
            existing_names & {crud.normalize_term(a) for a in aliases}
        ):
            raise HTTPException(status_code=409, detail=f"与既有术语「{t.canonical}」名称冲突")
    row = await crud.create_term(db, canonical, aliases)
    return TermOut(
        id=row.id, canonical=row.canonical, aliases=row.aliases or [],
        enabled=row.enabled, source=row.source,
        alias_count=len(row.aliases or []), item_count=0,
    )


@router.patch("/terms/{term_id}", response_model=TermOut)
async def update_term_endpoint(
    term_id: UUID,
    body: TermUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    fields = body.model_dump(exclude_unset=True)
    if "canonical" in fields and not (fields["canonical"] or "").strip():
        raise HTTPException(status_code=422, detail="规范名不能为空")
    if "aliases" in fields:
        # 显式 null 按 [] 处理并清洗
        fields["aliases"] = [a.strip() for a in (fields["aliases"] or []) if a and a.strip()]
    row = await crud.get_term(db, term_id)
    if row is None:
        raise HTTPException(status_code=404, detail="术语不存在")
    # 生效值 = 显式传入 ∪ 既有行（exclude_unset;PATCH 语义下无部分覆盖漏洞）
    eff_canonical = (fields.get("canonical") or row.canonical).strip()
    eff_aliases = fields.get("aliases", row.aliases or [])
    # 自洽: 规范名 ∈ 自身归一化别名集 → 422（否则可绕过 POST 防护）
    if crud.normalize_term(eff_canonical) in {crud.normalize_term(a) for a in eff_aliases}:
        raise HTTPException(status_code=422, detail="规范名与自身别名冲突")
    # 归一化去重（保序;alias_count 不虚高）——显式传入时回写
    seen: set = set()
    deduped: list = []
    for a in eff_aliases:
        k = crud.normalize_term(a)
        if k and k not in seen:
            seen.add(k)
            deduped.append(a.strip())
    if "aliases" in fields:
        fields["aliases"] = deduped
    if "canonical" in fields:
        fields["canonical"] = eff_canonical
    # 对其它术语撞车（排除自身 id）→ 409,同 POST 文案;任一行撞即 409（并发合并竞态下
    # list_terms 可能返回重复 canonical 行,语义不变）
    for t in await crud.list_terms(db):
        if t.id == term_id:
            continue
        other_names = {crud.normalize_term(n) for n in [t.canonical, *(t.aliases or [])]}
        if crud.normalize_term(eff_canonical) in other_names or (
            other_names & {crud.normalize_term(a) for a in deduped}
        ):
            raise HTTPException(status_code=409, detail=f"与既有术语「{t.canonical}」名称冲突")
    row = await crud.update_term(db, term_id, fields)
    if row is None:  # get 与 update 之间的并发删除竞态兜底
        raise HTTPException(status_code=404, detail="术语不存在")
    return TermOut(
        id=row.id, canonical=row.canonical, aliases=row.aliases or [],
        enabled=row.enabled, source=row.source,
        alias_count=len(row.aliases or []), item_count=0,
    )


@router.delete("/terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_term_endpoint(
    term_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    if not await crud.delete_term(db, term_id):
        raise HTTPException(status_code=404, detail="术语不存在")


# --- RAGFlow 知识库集成 (EAI-CUSTOM: 合同价格分析 × RAGFlow, 共享租户服务身份) --


@router.post("/ragflow/init")
async def init_contract_ragflow(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """幂等初始化共享租户两个固定知识库并回读连通状态。

    服务身份失败/RAGFlow 不可达（RuntimeError、httpx）→ 503 + detail
    （设置页「重试连接」按钮语义, EAI-CUSTOM Task2 review M4）；其余意外异常仍 500。
    """
    try:
        client = await ragflow_setup.get_service_client(db)
        initialized = await ragflow_setup.ensure_initialized(client)
        connectivity = await ragflow_setup.collect_status(client)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "initialized": initialized, "connectivity": connectivity}


@router.get("/ragflow/status")
async def contract_ragflow_status(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """连通性探测 + 两个固定知识库状态；任何失败降级 available=False，不 500（前端状态面板直读）。"""
    try:
        client = await ragflow_setup.get_service_client(db)
        return await ragflow_setup.collect_status(client)
    except Exception as exc:  # noqa: BLE001 — SSO 未配置/网络不可达均为降级而非 500
        return {"available": False, "datasets": [], "error": str(exc)}


@router.post("/library/files/{file_id}/ragflow-sync")
async def ragflow_sync_library_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    """库文件 → 共享租户「合同知识库」（上传+解析）。同名文档已存在 → already_exists 不重复上传。"""
    lf = await crud.get_library_file(db, file_id)
    if lf is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        data = await asyncio.to_thread(storage.get_object, lf.storage_key)
    except Exception:
        raise HTTPException(status_code=404, detail="文件对象不存在")
    try:
        client = await ragflow_setup.get_service_client(db)
        return await ragflow_setup.sync_file(client, filename=lf.file_name or "file", content=data)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"RAGFlow 同步失败: {exc}") from exc


# --- Functional area 1: documents ------------------------------------------


@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(
    keyword: str | None = None,
    parse_status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_documents(db, keyword, parse_status, skip, limit)
    return Page[DocumentOut](items=items, total=total, skip=skip, limit=limit)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    doc = await db.get(CpaDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    # also remove the MinIO object so storage doesn't leak (scan would otherwise
    # re-ingest it every run). Previews are small PNGs, left to orphan.
    key = doc.storage_uri.split("/", 3)[-1] if doc.storage_uri.count("/") >= 3 else doc.file_name
    storage.delete_object(key)
    await crud.delete_document(db, doc_id)


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def update_document(
    doc_id: UUID,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Manual补 fallback: fill project name/location (and doc metadata) the
    front-page OCR regex couldn't anchor. Used by the ContractsView editor."""
    # EAI-CUSTOM (自进化 D-1, 补遗 2026-09-22): 人工修正即捕获——pre-image diff
    # 进 agent_learnings(evolution.capture_field_correction), 供锚词规则晋升评审。
    _DOC_FIELDS = ("project_name", "project_location", "project_no", "contract_no", "supplier", "sign_date")
    pre_doc = await db.get(CpaDocument, doc_id)
    pre = {f: getattr(pre_doc, f, None) for f in _DOC_FIELDS} if pre_doc is not None else {}
    doc = await crud.update_document(db, doc_id, body.model_dump(exclude_unset=True))
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    for field in _DOC_FIELDS:
        old, new = pre.get(field), getattr(doc, field)
        if old != new:
            await evolution.capture_field_correction(
                db,
                user_id=str(current_user.id),
                scope="doc",
                field=field,
                old_value=old,
                new_value=new,
                doc_hash=doc.file_hash,
            )
    return doc


@router.get("/documents/{doc_id}/file")
async def download_document_file(
    doc_id: UUID,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Stream the ORIGINAL uploaded contract file from MinIO (合同原文留档/查看/下载).

    Read-only archive access — the pipeline never mutates the uploaded object;
    orientation-corrected page previews stay on /preview/{page}.
    `?inline=1` serves Content-Disposition inline so the browser PDF viewer can
    embed the full document (preview PNGs only cover extracted-table pages).
    """
    doc = await db.get(CpaDocument, doc_id)
    if doc is None or not doc.storage_uri:
        raise HTTPException(status_code=404, detail="original file not available")
    prefix = f"s3://{storage.BUCKET}/"
    key = doc.storage_uri[len(prefix):] if doc.storage_uri.startswith(prefix) else doc.storage_uri
    try:
        data = await asyncio.to_thread(storage.get_object, key)
    except Exception:
        raise HTTPException(status_code=404, detail="original file not found")
    media = (
        "application/pdf"
        if (doc.file_type or "").lower() == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    quoted = urllib.parse.quote(doc.file_name or "contract")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=media,
        headers={
            # ASCII fallback + RFC 5987 for CJK filenames (合同文件名普遍为中文)
            "Content-Disposition": f"{disposition}; filename=\"contract.{doc.file_type or 'bin'}\"; filename*=UTF-8''{quoted}"
        },
    )


@router.post("/documents/{doc_id}/confirm", response_model=DocumentOut)
async def confirm_document(
    doc_id: UUID,
    body: DocumentConfirm,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Confirm-gate: mark a parsed document confirmed/skipped so the cluster
    phase will include it."""
    doc = await crud.confirm_document(db, doc_id, body.confirm_status)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.post("/documents/confirm-all")
async def confirm_all_documents(
    body: DocumentConfirm,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Batch confirm-gate: set every pending parsed document to the given status."""
    count = await crud.confirm_all_documents(db, body.confirm_status)
    return {"updated": count, "confirm_status": body.confirm_status}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Upload a contract to the independent cpa-contracts MinIO bucket.

    The pipeline picks it up on the next run (scan detects new files by SHA-256).
    Dedup by CONTENT: re-uploading the same file under the SAME name overwrites
    in place (and re-parses on content change); uploading the SAME content under
    a DIFFERENT filename is rejected (409) so one contract can't pollute stats by
    being counted twice.
    """
    name = (file.filename or "").lower()
    if not name.endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="only .pdf / .docx accepted")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    key = file.filename or "contract.pdf"
    digest = hashlib.sha256(data).hexdigest()
    dup = await crud.find_duplicate_document(db, digest, exclude_uri=f"s3://{storage.BUCKET}/{key}")
    if dup is not None:
        raise HTTPException(
            status_code=409,
            detail=(f"该合同内容已存在(文件名: {dup.file_name}),已拒绝重复上传。如需重跑,请在合同文档页对该合同点「重新解析」。"),
        )
    uri = storage.upload_bytes(key, data)
    # Create a 'pending' doc row immediately so the list shows it (解析中)
    # before the parse run finishes. _persist_parse upserts on storage_uri.
    file_type = os.path.splitext(key)[1].lstrip(".").lower() or "pdf"
    await crud.create_pending_document(db, storage_uri=uri, file_name=key, file_hash=digest, file_type=file_type, size=len(data))
    return {"storage_uri": uri, "file_name": key, "size": len(data)}


@router.get("/documents/{doc_id}/preview/{page}")
async def get_preview(
    doc_id: UUID,
    page: int,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Stream a page's OCR preview PNG from MinIO (for the traceback overlay)."""
    doc = await db.get(CpaDocument, doc_id)
    if doc is None or not doc.preview_prefix:
        raise HTTPException(status_code=404, detail="preview not available")
    try:
        png = storage.get_preview(doc.preview_prefix, page)
    except Exception:
        raise HTTPException(status_code=404, detail="preview page not found")
    return Response(content=png, media_type="image/png")


@router.post("/documents/{doc_id}/reparse", response_model=PipelineRunResponse)
async def reparse_document(
    doc_id: UUID,
    background: BackgroundTasks,
    re_ocr: bool = False,
    ocr_provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Re-parse a single document by force (bypass SHA-256 cache), preserving doc_id.

    Resolves the doc's MinIO key from storage_uri (s3://bucket/<key>) and kicks
    off a parse run scoped to that one object. The pipeline upserts by
    storage_uri, so the existing cpa_documents row is updated in place and its
    items are replaced (doc_id unchanged).

    re_ocr=true 强制重 OCR;默认读 OCR 缓存仅重跑分类+提取(秒级)。
    ocr_provider (cpa v3 M3 spec §3.4): 单文档引擎覆盖——本次解析临时使用指定
    服务(None = 取模块配置);缓存按 provider 分键,互不污染。
    """
    await crud.cleanup_stale_runs(db)
    if await crud.has_running_run(db, "parse"):
        raise HTTPException(status_code=409, detail="a parse run is already in progress")
    doc = await db.get(CpaDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    # storage_uri looks like "s3://cpa-contracts/<key>"
    key = doc.storage_uri.split("/", 3)[-1] if doc.storage_uri.count("/") >= 3 else doc.file_name
    # 立即置「解析中」(被重解析的文档当前可能是 parsed/needs_review,故强制覆写);
    # force_key 子进程会重跑并覆写终态。
    await crud.set_document_parse_status(db, doc_id, "parsing")
    run = await crud.create_run(
        db,
        trigger_type="manual",
        status="running",
        scope={"mode": "table", "phase": "parse", "started_by": current_user.username, "reparse": key, "re_ocr": re_ocr, "ocr_provider": ocr_provider},
    )
    background.add_task(service.run_pipeline_subprocess, db, run.id, "table", "manual", "parse", key, re_ocr, ocr_provider)
    return PipelineRunResponse(run_id=run.id, status="running", message=f"reparse started: {key}")


# --- Functional area 2: clusters -------------------------------------------


@router.get("/clusters", response_model=Page[ClusterOut])
async def list_clusters(
    cluster_status: str | None = None,
    category: str | None = None,
    keyword: str | None = Query(None, max_length=100),  # EAI-CUSTOM: 代表名/类目模糊搜(手动合并辅助)
    skip: int = Query(0, ge=0),
    # EAI-CUSTOM: 上限200→1000, 总览货物下拉需拉全量(分组数>200后下拉只显示前几十个)
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_clusters(db, cluster_status, category, keyword, skip, limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/clusters/{cluster_id}", response_model=ClusterDetail)
async def get_cluster(
    cluster_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    cluster = await crud.get_cluster_with_items(db, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    return cluster


@router.post("/clusters/{cluster_id}/confirm")
async def confirm_cluster(
    cluster_id: UUID,
    body: ClusterConfirm,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    try:
        cluster = await crud.confirm_cluster(db, cluster_id, body.confirmed_by or current_user.username, body.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    return {"status": cluster.status, "version": cluster.version}


@router.post("/clusters/{cluster_id}/reject")
async def reject_cluster(
    cluster_id: UUID,
    body: ClusterConfirm,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Reject a cluster (manual curation — drops it from confirmed stats)."""
    try:
        cluster = await crud.reject_cluster(db, cluster_id, body.expected_version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    return {"status": cluster.status, "version": cluster.version}


@router.patch("/clusters/{cluster_id}", response_model=ClusterOut)
async def update_cluster(
    cluster_id: UUID,
    body: ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Edit a cluster's display fields (category / representative_name)."""
    cluster = await crud.update_cluster(db, cluster_id, body.model_dump(exclude_unset=True))
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    return cluster


@router.post("/clusters/merge")
async def merge_clusters(
    body: ClusterMerge,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    try:
        new_cluster = await crud.merge_clusters(db, body.cluster_ids, body.representative_name, body.category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if new_cluster is None:
        raise HTTPException(status_code=404, detail="no clusters found to merge")
    return {"cluster_id": str(new_cluster.id), "item_count": new_cluster.item_count}


@router.post("/items/{item_id}/move")
async def move_item(
    item_id: UUID,
    body: ItemMove,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    item = await crud.move_item(db, item_id, body.target_cluster_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"item_id": str(item.id), "cluster_id": str(item.cluster_id)}


# --- Functional area 3: items ----------------------------------------------


@router.get("/items/contracts")
async def list_item_contracts(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Distinct source_contract_no with item counts (items-page filter options)."""
    return await crud.list_item_contracts(db)


@router.get("/items", response_model=Page[ItemOut])
async def list_items(
    goods_name: str | None = None,
    source_contract_no: str | None = None,
    cluster_id: UUID | None = None,
    run_id: UUID | None = None,
    only_outliers: bool = False,
    validation_status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_items(db, goods_name, source_contract_no, cluster_id, run_id, only_outliers, validation_status, skip, limit)
    return Page[ItemOut](items=items, total=total, skip=skip, limit=limit)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: UUID,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    # EAI-CUSTOM (自进化 D-3, 补遗 2026-09-22): 行级值修正(名称/规格/单价/参数)
    # 即捕获, 错误模式粗分类后进 agent_learnings——超出既有 L4 表头词收割的
    # 部分(错误模式本身)供列语义规则晋升评审。
    _ITEM_FIELDS = ("unit_price", "goods_name", "spec_model", "tech_params")
    pre_item = await db.get(CpaItem, item_id)
    pre = {f: getattr(pre_item, f, None) for f in _ITEM_FIELDS} if pre_item is not None else {}
    item = await crud.update_item(db, item_id, body.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    doc = await db.get(CpaDocument, item.document_id)
    for field in _ITEM_FIELDS:
        old, new = pre.get(field), getattr(item, field)
        if old != new:
            await evolution.capture_field_correction(
                db,
                user_id=str(current_user.id),
                scope="item",
                field=field,
                old_value=old,
                new_value=new,
                doc_hash=doc.file_hash if doc is not None else None,
                error_pattern=evolution.classify_error_pattern(
                    "" if old is None else str(old), "" if new is None else str(new)
                ),
            )
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    deleted = await crud.delete_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="item not found")


@router.post("/items/batch-delete")
async def batch_delete_items(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    count = await crud.delete_items_batch(db, body.item_ids)
    return {"deleted": count}


@router.post("/items/batch-validate")
async def batch_validate_items(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Batch set validation_status (ok) for selected items."""
    count = await crud.batch_validate_items(db, body.item_ids)
    return {"updated": count}


@router.delete("/items/by-run/{run_id}")
async def delete_items_by_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    count = await crud.delete_items_by_run(db, run_id)
    return {"deleted": count}


# --- Functional area 4: runs -----------------------------------------------


@router.get("/runs", response_model=Page[RunOut])
async def list_runs(
    run_status: str | None = None,
    has_items: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_runs(db, run_status, has_items, skip, limit)
    return Page[RunOut](items=items, total=total, skip=skip, limit=limit)


@router.get("/runs/{run_id}/excel")
async def download_run_excel(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    run = await crud.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not run.excel_path or not os.path.exists(run.excel_path):
        raise HTTPException(status_code=404, detail="excel file not available for this run")
    return FileResponse(run.excel_path, filename=os.path.basename(run.excel_path))


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    ok = await crud.delete_run(db, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="run not found")
    return {"deleted": True}


# --- Functional area 7: evolution（自进化候选 ⑥ 落地工作流, EAI-CUSTOM） ------


@router.get("/evolution/candidates")
async def evolution_candidates(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """pending 的字段修正候选（recurrence 降序）+ LLM 草案 + L4 建议锚词, 供配置页规则卡落地。"""
    return {
        "items": await evolution.list_candidates(
            db, user_id=str(current_user.id)
        )
    }


@router.post("/evolution/candidates/{learning_id}/adopt")
async def evolution_adopt(
    learning_id: str,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """人工已把该证据落成种子规则卡 → 标记 promoted_to_skill（晋升链路闭环）。"""
    ok = await evolution.set_candidate_status(db, learning_id, "promoted_to_skill")
    if not ok:
        raise HTTPException(status_code=404, detail="candidate not found")
    return {"status": "promoted_to_skill"}


@router.post("/evolution/candidates/{learning_id}/dismiss")
async def evolution_dismiss(
    learning_id: str,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """忽略该候选（误操作/不具代表性 → 永不重开, D12 dismissed 语义）。"""
    ok = await evolution.set_candidate_status(db, learning_id, "dismissed")
    if not ok:
        raise HTTPException(status_code=404, detail="candidate not found")
    return {"status": "dismissed"}


# --- Functional area 5: config ---------------------------------------------


@router.get("/config", response_model=ConfigOut)
async def get_config(_: CurrentUser = Depends(require_permission("system:access"))):  # EAI-CUSTOM: Add permission check
    # EAI-CUSTOM (review fix 2026-09-20): llm_key write-only——GET 只回掩码占位,
    # 明文真值不出 API(system:access 被基础 user 角色持有)。
    return crud.mask_llm_key(crud.load_config())


@router.put("/config", response_model=ConfigOut)
async def update_config(
    body: ConfigUpdate,
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    # EAI-CUSTOM (review fix 2026-09-20): GET 的掩码占位被原样 PUT 回传时视为
    # "llm_key 未修改",还原已存真值落盘,新 key 仍可直接写入。
    # EAI-CUSTOM (复验 fix 2026-09-20): 响应同样过掩码——否则持 system:access 的
    # 客户端 PUT 回掩码即可从响应体读回明文真值,write-only 语义被 PUT 打穿。
    return crud.mask_llm_key(crud.save_config(crud.resolve_llm_key_mask(body)))


# --- Functional area 6: dashboard ------------------------------------------


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    counts = await crud.dashboard_counts(db)
    recent, _ = await crud.list_runs(db, limit=5)
    return DashboardOut(
        **counts,
        price_range=await crud.price_range(db),
        charts=await crud.dashboard_charts(db),
        recent_runs=recent,
    )


@router.get("/contract-price-analysis")
async def contract_price_analysis(
    name: str | None = None,
    cluster_id: UUID | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Cross-contract goods price analysis: box plot stats, supplier comparison,
    trend by date, price histogram, and paginated detail table."""
    return await crud.goods_analysis(db, name=name, cluster_id=cluster_id, skip=skip, limit=limit)


# --- Pipeline trigger ------------------------------------------------------


@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def trigger_pipeline(
    body: PipelineRunRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Kick off a parse-phase run in the background; returns the run id immediately."""
    await crud.cleanup_stale_runs(db)  # self-heal orphaned 'running' runs
    if await crud.has_running_run(db, "parse"):
        raise HTTPException(status_code=409, detail="a parse run is already in progress")
    run = await crud.create_run(
        db,
        trigger_type=body.trigger,
        status="running",
        scope={"mode": body.mode, "phase": "parse", "started_by": current_user.username},
    )
    # 立即把全部「已上传」文档置为「解析中」,前端点下按钮即可见状态切换;
    # 子进程随后覆写为 parsed/failed/needs_review。
    await crud.mark_documents_parsing(db)
    background.add_task(service.run_pipeline_subprocess, db, run.id, body.mode, body.trigger, "parse")
    return PipelineRunResponse(run_id=run.id, status="running", message="parse started")


@router.post("/cluster/run", response_model=PipelineRunResponse)
async def trigger_cluster(
    body: PipelineRunRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """Phase 2: cluster all parsed documents' items in the background (no confirm gate)."""
    await crud.cleanup_stale_runs(db)  # self-heal orphaned 'running' runs
    if await crud.has_running_run(db, "cluster"):
        raise HTTPException(status_code=409, detail="a cluster run is already in progress")
    run = await crud.create_run(
        db,
        trigger_type=body.trigger,
        status="running",
        scope={"phase": "cluster", "started_by": current_user.username},
    )
    background.add_task(service.run_pipeline_subprocess, db, run.id, body.mode, body.trigger, "cluster")
    return PipelineRunResponse(run_id=run.id, status="running", message="cluster started")


@router.get("/pipeline/runs/{run_id}/status")
async def pipeline_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    run = await crud.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": str(run.id),
        "status": run.status,
        "docs_processed": run.docs_processed,
        "items_extracted": run.items_extracted,
        "clusters_formed": run.clusters_formed,
        "progress": run.progress,
        "error": run.error,
    }
