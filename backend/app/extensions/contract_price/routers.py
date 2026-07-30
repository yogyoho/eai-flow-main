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
  Pipeline trigger             : POST /pipeline/run, GET /pipeline/runs/{id}/status
"""

import hashlib
import logging
import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.contract_price import crud, service, storage
from app.extensions.contract_price.models import CpaDocument
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
    Page,
    PipelineRunRequest,
    PipelineRunResponse,
    RunOut,
)
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/contract-price", tags=["Contract Price Analysis"])


# --- Functional area 1: documents ------------------------------------------


@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(
    keyword: str | None = None,
    parse_status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_documents(db, keyword, parse_status, skip, limit)
    return Page[DocumentOut](items=items, total=total, skip=skip, limit=limit)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    """Manual补 fallback: fill project name/location (and doc metadata) the
    front-page OCR regex couldn't anchor. Used by the ContractsView editor."""
    doc = await crud.update_document(db, doc_id, body.model_dump(exclude_unset=True))
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.post("/documents/{doc_id}/confirm", response_model=DocumentOut)
async def confirm_document(
    doc_id: UUID,
    body: DocumentConfirm,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    """Batch confirm-gate: set every pending parsed document to the given status."""
    count = await crud.confirm_all_documents(db, body.confirm_status)
    return {"updated": count, "confirm_status": body.confirm_status}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
            detail=(
                f"该合同内容已存在(文件名: {dup.file_name}),已拒绝重复上传。"
                "如需重跑,请在合同文档页对该合同点「重新解析」。"
            ),
        )
    uri = storage.upload_bytes(key, data)
    # Create a 'pending' doc row immediately so the list shows it (解析中)
    # before the parse run finishes. _persist_parse upserts on storage_uri.
    file_type = os.path.splitext(key)[1].lstrip(".").lower() or "pdf"
    await crud.create_pending_document(
        db, storage_uri=uri, file_name=key, file_hash=digest, file_type=file_type, size=len(data)
    )
    return {"storage_uri": uri, "file_name": key, "size": len(data)}


@router.get("/documents/{doc_id}/preview/{page}")
async def get_preview(
    doc_id: UUID,
    page: int,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    """Re-parse a single document by force (bypass SHA-256 cache), preserving doc_id.

    Resolves the doc's MinIO key from storage_uri (s3://bucket/<key>) and kicks
    off a parse run scoped to that one object. The pipeline upserts by
    storage_uri, so the existing cpa_documents row is updated in place and its
    items are replaced (doc_id unchanged).
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
        scope={"mode": "table", "phase": "parse", "started_by": current_user.username, "reparse": key},
    )
    background.add_task(
        service.run_pipeline_subprocess, db, run.id, "table", "manual", "parse", key
    )
    return PipelineRunResponse(run_id=run.id, status="running", message=f"reparse started: {key}")


# --- Functional area 2: clusters -------------------------------------------


@router.get("/clusters", response_model=Page[ClusterOut])
async def list_clusters(
    cluster_status: str | None = None,
    category: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_clusters(db, cluster_status, category, skip, limit)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/clusters/{cluster_id}", response_model=ClusterDetail)
async def get_cluster(
    cluster_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    current_user: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    try:
        cluster = await crud.confirm_cluster(
            db, cluster_id, body.confirmed_by or current_user.username, body.expected_version
        )
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    try:
        new_cluster = await crud.merge_clusters(
            db, body.cluster_ids, body.representative_name, body.category
        )
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    item = await crud.move_item(db, item_id, body.target_cluster_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"item_id": str(item.id), "cluster_id": str(item.cluster_id)}


# --- Functional area 3: items ----------------------------------------------


@router.get("/items/contracts")
async def list_item_contracts(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_items(
        db, goods_name, source_contract_no, cluster_id, run_id, only_outliers, validation_status, skip, limit
    )
    return Page[ItemOut](items=items, total=total, skip=skip, limit=limit)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: UUID,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    item = await crud.update_item(db, item_id, body.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    deleted = await crud.delete_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="item not found")


@router.post("/items/batch-delete")
async def batch_delete_items(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    count = await crud.delete_items_batch(db, body.item_ids)
    return {"deleted": count}


@router.post("/items/batch-validate")
async def batch_validate_items(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    """Batch set validation_status (ok) for selected items."""
    count = await crud.batch_validate_items(db, body.item_ids)
    return {"updated": count}


@router.delete("/items/by-run/{run_id}")
async def delete_items_by_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    count = await crud.delete_items_by_run(db, run_id)
    return {"deleted": count}


# --- Functional area 4: runs -----------------------------------------------


@router.get("/runs", response_model=Page[RunOut])
async def list_runs(
    run_status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
):
    items, total = await crud.list_runs(db, run_status, skip, limit)
    return Page[RunOut](items=items, total=total, skip=skip, limit=limit)


@router.get("/runs/{run_id}/excel")
async def download_run_excel(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    ok = await crud.delete_run(db, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="run not found")
    return {"deleted": True}


# --- Functional area 5: config ---------------------------------------------


@router.get("/config", response_model=ConfigOut)
async def get_config(_: CurrentUser = Depends(require_permission("cpa:read"))):  # EAI-CUSTOM: Add permission check
    return crud.load_config()


@router.put("/config", response_model=ConfigOut)
async def update_config(
    body: ConfigUpdate,
    _: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
):
    return crud.save_config(body)


# --- Functional area 6: dashboard ------------------------------------------


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
    current_user: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    background.add_task(
        service.run_pipeline_subprocess, db, run.id, body.mode, body.trigger, "parse"
    )
    return PipelineRunResponse(
        run_id=run.id, status="running", message="parse started"
    )


@router.post("/cluster/run", response_model=PipelineRunResponse)
async def trigger_cluster(
    body: PipelineRunRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("cpa:import")),  # EAI-CUSTOM: Add permission check
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
    background.add_task(
        service.run_pipeline_subprocess, db, run.id, body.mode, body.trigger, "cluster"
    )
    return PipelineRunResponse(
        run_id=run.id, status="running", message="cluster started"
    )


@router.get("/pipeline/runs/{run_id}/status")
async def pipeline_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("cpa:read")),  # EAI-CUSTOM: Add permission check
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
