"""Translation task API (EAI-CUSTOM) — /api/extensions/translation.

S1 骨架（eng-review T2/T5 的 API 面）：任务列表/详情/状态流转。
MCP 工具（translate_document/translation_status）与 worker 在 T4/T5 接入，
复用同一 state 机校验（validate_transition）。
"""

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.extensions.auth.admin import is_superadmin
from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.storage import get_storage_provider
from app.extensions.models import Document, KnowledgeBase
from app.extensions.translation import checks
from app.extensions.translation.glossary import (
    ACTIONS,
    LANGS,
    GlossaryEntry,
    clean_domains,
    file_version,
    load_glossary,
    read_entries,
    resolve_glossary_path,
    write_entries,
)
from app.extensions.translation.glossary_import import MAX_IMPORT_BYTES
from app.extensions.translation.glossary_import import merge as merge_glossary_import
from app.extensions.translation.glossary_import import parse_file as parse_glossary_file
from app.extensions.translation.langdetect import detect_language
from app.extensions.translation.models import (
    STATES,
    TERMINAL_STATES,
    TltBackfillJob,
    TltFolder,
    TranslationTask,
    validate_transition,
)
from app.extensions.translation.parsers import OcrRequired, blocks_text, classify_tag, parse_document
from app.extensions.translation.ragflow_bridge import _doc_exists, build_markdown, ensure_dataset, index_original, index_translation, reindex_deliverable
from app.extensions.translation.settings import (
    SETTINGS_KEY,
    read_translation_settings,
    resolve_effective_model_name,
    write_translation_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/translation", tags=["Translation"])


class TransitionRequest(BaseModel):
    target: str
    note: str | None = None


class BatchTranslateRequest(BaseModel):
    task_ids: list[UUID]


class TaskFolderPatch(BaseModel):
    folder_id: UUID | None = None


class BackfillJobCreate(BaseModel):
    task_ids: list[UUID] | None = None
    kb_id: UUID | None = None
    folder_id: str | None = None  # "root" 或 UUID
    states: list[str] | None = None  # 默认 stored/failed
    chunk_size: int = 100


class DraftUpdateBody(BaseModel):
    blocks: list[dict]  # [{id, text}]


def _draft_gate_failures(task: TranslationTask, blocks: list[dict]) -> dict[str, list[str]]:
    """MTPE 草稿的硬轴复检：数值/术语（结构由块类型复制保证）。"""
    source = task.draft_source_blocks or []
    if not source:
        return {}
    source_text = "\n".join(str(item.get("text", "")) for item in source)
    translated_text = "\n".join(str(item.get("text", "")) for item in blocks)
    failures: dict[str, list[str]] = {}
    numeric = checks.run_numeric_axis(source_text, translated_text, task.source_lang)
    if numeric:
        failures["numeric"] = numeric
    glossary = load_glossary()
    force_terms, dont_translate = glossary.for_language(task.source_lang)
    terminology = checks.terminology_violations(source_text, translated_text, force_terms, dont_translate)
    if terminology:
        failures["terminology"] = terminology
    return failures


class TaskOut(BaseModel):
    id: UUID
    kb_id: UUID
    document_id: UUID | None
    doc_sha: str
    source_lang: str
    content_tag: str | None
    state: str
    quality_tier: str
    progress: int
    retry_count: int
    task_version: int
    gate_failures: dict | None
    error_detail: dict | None
    superseded_by: UUID | None
    folder_id: UUID | None
    deliverable_uri: str | None
    ragflow_zh_doc_id: str | None
    ragflow_source_doc_id: str | None
    file_name: str
    size_bytes: int | None
    created_at: str | None
    updated_at: str | None
    source_uri: str | None
    kb_name: str | None
    uncertainty: list | None  # worker 写 list[{block,...}]，mcp.py 按 list 迭代（曾误标 dict → pydantic 500）

    @classmethod
    def from_row(cls, t: TranslationTask, kb_name: str | None = None) -> "TaskOut":
        size = None
        try:
            if t.source_uri and not t.source_uri.startswith(("s3://", "http")):
                size = os.path.getsize(t.source_uri)
        except OSError:
            size = None
        return cls(
            id=t.id,
            kb_id=t.kb_id,
            document_id=t.document_id,
            doc_sha=t.doc_sha,
            source_lang=t.source_lang,
            content_tag=t.content_tag,
            state=t.state,
            quality_tier=t.quality_tier,
            progress=t.progress,
            retry_count=t.retry_count,
            task_version=t.task_version,
            gate_failures=t.gate_failures,
            error_detail=t.error_detail,
            superseded_by=t.superseded_by,
            folder_id=t.folder_id,
            deliverable_uri=t.deliverable_uri,
            ragflow_zh_doc_id=t.ragflow_zh_doc_id,
            ragflow_source_doc_id=t.ragflow_source_doc_id,
            file_name=Path(t.source_uri or "").name or "(未命名)",
            size_bytes=size,
            created_at=t.created_at.isoformat() if t.created_at else None,
            updated_at=t.updated_at.isoformat() if t.updated_at else None,
            source_uri=t.source_uri,
            kb_name=kb_name,
            uncertainty=t.uncertainty,
        )


async def _get_task_scoped(task_id: UUID, current_user, is_admin: bool, db: AsyncSession) -> TranslationTask:
    """取任务并做 owner 过滤（R7/SC: 与 knowledge_scope 准入同源的 owner 原则）。"""
    task = await db.get(TranslationTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    kb = await db.get(KnowledgeBase, task.kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kb not found")
    if not is_admin and kb.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not task owner")
    return task


@router.get("/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    kb_id: UUID | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    state: str | None = Query(default=None),
    source_lang: str | None = Query(default=None),
    quality_tier: str | None = Query(default=None),
    q: str | None = Query(default=None),
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """分页任务列表（资产库/任务管理共用）。

    folder_id: "root"=根（未归夹）；UUID=指定文件夹；缺省=全部。
    默认排除已移出库的行（archived/cancelled/superseded——库删除语义=移出列表，R3-3）；
    state 显式指定时按指定态过滤（含终态，供历史查询）。
    """
    if state is not None and state not in STATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown state: {state}")
    if source_lang is not None and source_lang not in {"en", "fr", "zh", "mixed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown source_lang: {source_lang}")
    if quality_tier is not None and quality_tier not in {"draft", "reviewed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown quality_tier: {quality_tier}")
    is_admin = await is_superadmin(db, current_user.id)
    conds = []
    if state is not None:
        conds.append(TranslationTask.state == state)
    else:
        conds.append(TranslationTask.state.notin_(["archived", "cancelled", "superseded"]))
    if source_lang is not None:
        conds.append(TranslationTask.source_lang == source_lang)
    if quality_tier is not None:
        conds.append(TranslationTask.quality_tier == quality_tier)
    if kb_id is not None:
        conds.append(TranslationTask.kb_id == kb_id)
    if folder_id == "root":
        conds.append(TranslationTask.folder_id.is_(None))
    elif folder_id:
        conds.append(TranslationTask.folder_id == UUID(folder_id))
    if q:
        conds.append(or_(TranslationTask.source_uri.ilike(f"%{q}%"), TranslationTask.doc_sha.ilike(f"{q}%")))

    base = select(TranslationTask, KnowledgeBase.name).join(KnowledgeBase, TranslationTask.kb_id == KnowledgeBase.id).where(*conds)
    if not is_admin:
        base = base.where(KnowledgeBase.owner_id == current_user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = (await db.execute(base.order_by(TranslationTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "items": [TaskOut.from_row(t, kb_name=name).model_dump(mode="json") for t, name in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/task-stats")
async def task_stats(
    kb_id: UUID | None = Query(default=None),
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """任务页头部指标条：按状态聚合（同 owner/data-scope 口径）。"""
    is_admin = await is_superadmin(db, current_user.id)
    conds = [TranslationTask.state.notin_(["archived", "cancelled", "superseded"])]
    if kb_id is not None:
        conds.append(TranslationTask.kb_id == kb_id)
    stmt = select(TranslationTask.state, func.count()).join(KnowledgeBase, TranslationTask.kb_id == KnowledgeBase.id).where(*conds)
    if not is_admin:
        stmt = stmt.where(KnowledgeBase.owner_id == current_user.id)
    rows = (await db.execute(stmt.group_by(TranslationTask.state))).all()
    by_state = {state: int(count) for state, count in rows}
    return {
        "total": sum(by_state.values()),
        "by_state": by_state,
        "delivered": by_state.get("delivered", 0),
        "running": by_state.get("running", 0),
        "pending": by_state.get("pending", 0),
        "exceeded": by_state.get("exceeded", 0),
        "skipped": by_state.get("skipped", 0),
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    return TaskOut.from_row(task).model_dump(mode="json")


@router.get("/tasks/{task_id}/draft")
async def get_task_draft(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """复核页对照数据：源文块 + 译文草稿（按 id 对齐）+ 机检/不确定段。"""
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    return {
        "state": task.state,
        "source": task.draft_source_blocks or [],
        "translated": task.draft_blocks or [],
        "gate_failures": task.gate_failures,
        "uncertainty": task.uncertainty or [],
        "edited_at": task.draft_edited_at.isoformat() if task.draft_edited_at else None,
        "edited_by": str(task.draft_edited_by) if task.draft_edited_by else None,
    }


@router.put("/tasks/{task_id}/draft")
async def update_task_draft(
    task_id: UUID,
    body: DraftUpdateBody,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MTPE：人工编辑 exceeded 草稿；首次编辑保留机器原件作为 TM 种子。"""
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if task.state != "exceeded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有待复核任务可编辑草稿")
    original = [dict(item) for item in (task.draft_blocks or [])]
    if not original:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="没有可编辑的草稿")
    by_id = {str(item.get("id", "")): item for item in original}
    for patch in body.blocks:
        block_id = str(patch.get("id", ""))
        if block_id not in by_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"未知译文块：{block_id}")
        text = str(patch.get("text", ""))
        if not text.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="译文块不能为空")
        by_id[block_id]["text"] = text
    if task.draft_blocks_original is None:
        task.draft_blocks_original = [dict(item) for item in (task.draft_blocks or [])]
    task.draft_blocks = original
    task.draft_edited_at = datetime.now(UTC).replace(tzinfo=None)
    task.draft_edited_by = current_user.id
    failures = _draft_gate_failures(task, original)
    task.gate_failures = failures or None
    await db.commit()
    await db.refresh(task)
    logger.info("tlt task %s draft edited by %s (failures=%s)", task.id, current_user.id, list(failures))
    return {
        "translated": task.draft_blocks,
        "gate_failures": failures,
        "edited_at": task.draft_edited_at.isoformat() if task.draft_edited_at else None,
    }


@router.post("/tasks/{task_id}/transition")
async def transition_task(
    task_id: UUID,
    req: TransitionRequest,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """人工流转（复核裁决 review_approved/rejected、failed 重跑、取消）。

    机检驱动流转由 worker（T4）走同一 validate_transition，不经此端点。
    """
    if req.target in TERMINAL_STATES and req.target == "delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="delivered 由 worker 在交付物落桶后驱动，不经人工端点",
        )
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not validate_transition(task.state, req.target):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"illegal transition: {task.state} -> {req.target}",
        )
    prev_state = task.state
    note_detail = None
    if req.note:
        note_detail = dict(task.error_detail or {})
        note_detail.setdefault("notes", []).append({"from": prev_state, "target": req.target, "note": req.note})

    # P0-1: 复核通过 = 用 exceeded 时保存的逐块草稿完成中文份索引与交付。
    if prev_state == "exceeded" and req.target == "indexed":
        blocks = task.draft_blocks
        if not blocks:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="缺少待交付草稿，请重跑翻译后再复核",
            )
        # P2 MTPE: reviewed 档交付前硬轴复检（数值/术语）；draft 档保留人工接受语义。
        if task.quality_tier == "reviewed":
            failures = _draft_gate_failures(task, blocks)
            if failures:
                task.gate_failures = failures
                await db.commit()
                summary = "；".join(f"{axis} {len(items)} 项" for axis, items in failures.items())
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"机检未通过：{summary}；请修正草稿后重试",
                )
        # 先落 indexed，作为并发复核的互斥闸；索引失败回退 exceeded 供重试。
        task.state = "indexed"
        if note_detail is not None:
            task.error_detail = note_detail
        await db.commit()
        try:
            await index_translation(task, blocks, [])
        except Exception as exc:
            logger.exception("tlt review approval index failed for %s", task_id)
            await db.refresh(task)
            task.state = "exceeded"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交付物索引失败，请重试：{exc}",
            ) from exc
        await db.refresh(task)
        task.state = "delivered"
        await db.commit()
        await db.refresh(task)
        logger.info("tlt task %s review approved -> delivered by %s", task.id, current_user.id)
        return TaskOut.from_row(task).model_dump(mode="json")

    task.state = req.target
    if req.target == "retrying":
        task.retry_count += 1
    if note_detail is not None:
        task.error_detail = note_detail
    await db.commit()
    # updated_at 由 onupdate=func.now() 服务端生成，flush 后属性已过期；
    # AsyncSession 下直接读会 MissingGreenlet（同 create_folder 的 refresh 手法）
    await db.refresh(task)
    logger.info("tlt task %s transitioned %s -> %s by %s", task.id, prev_state, req.target, current_user.id)
    return TaskOut.from_row(task).model_dump(mode="json")


@router.post("/tasks/batch-translate")
async def batch_translate_tasks(
    body: BatchTranslateRequest,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """批量入队：stored / failed → pending（单次 ≤500，自动去重）。"""
    if not body.task_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未选择任务")
    if len(body.task_ids) > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多 500 个任务")
    is_admin = await is_superadmin(db, current_user.id)
    rows = (await db.execute(select(TranslationTask).where(TranslationTask.id.in_(body.task_ids)))).scalars().all()
    by_id = {task.id: task for task in rows}
    queued: list[str] = []
    skipped: list[dict] = []
    seen: set[UUID] = set()
    for task_id in body.task_ids:
        if task_id in seen:
            continue
        seen.add(task_id)
        task = by_id.get(task_id)
        if task is None:
            skipped.append({"task_id": str(task_id), "reason": "not_found"})
            continue
        kb = await db.get(KnowledgeBase, task.kb_id)
        if kb is None or (not is_admin and kb.owner_id != current_user.id):
            skipped.append({"task_id": str(task_id), "reason": "forbidden"})
            continue
        if task.state not in {"stored", "failed"}:
            skipped.append({"task_id": str(task_id), "reason": f"state:{task.state}"})
            continue
        task.state = "pending"
        queued.append(str(task.id))
    await db.commit()
    logger.info("tlt batch translate: queued=%d skipped=%d by %s", len(queued), len(skipped), current_user.id)
    return {"queued": len(queued), "task_ids": queued, "skipped": skipped}


@router.post("/backfill-jobs", status_code=status.HTTP_201_CREATED)
async def create_backfill_job(
    body: BackfillJobCreate,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """超大回填：把选择/过滤出的任务分批交给后台 tick 入队（每批 chunk_size）。"""
    if body.chunk_size < 10 or body.chunk_size > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chunk_size 需在 10-500 之间")
    states = set(body.states or ["stored", "failed"]) & {"stored", "failed"}
    if not states:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="states 仅支持 stored / failed")
    is_admin = await is_superadmin(db, current_user.id)
    selected: list[str] = []
    if body.task_ids:
        ids = list(dict.fromkeys(body.task_ids))
        if len(ids) > 20000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次回填最多 20000 个任务")
        rows = (await db.execute(select(TranslationTask).where(TranslationTask.id.in_(ids)))).scalars().all()
        by_id = {task.id: task for task in rows}
        allowed_kbs: dict[UUID, bool] = {}
        for task_id in ids:
            task = by_id.get(task_id)
            if task is None or task.state not in states:
                continue
            allowed = allowed_kbs.get(task.kb_id)
            if allowed is None:
                kb = await db.get(KnowledgeBase, task.kb_id)
                allowed = bool(kb and (is_admin or kb.owner_id == current_user.id))
                allowed_kbs[task.kb_id] = allowed
            if allowed:
                selected.append(str(task.id))
    else:
        conds = [TranslationTask.state.in_(states)]
        if body.kb_id is not None:
            conds.append(TranslationTask.kb_id == body.kb_id)
        if body.folder_id:
            if body.folder_id == "root":
                conds.append(TranslationTask.folder_id.is_(None))
            else:
                try:
                    conds.append(TranslationTask.folder_id == UUID(body.folder_id))
                except ValueError:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="folder_id 非法")
        stmt = select(TranslationTask.id).join(KnowledgeBase, TranslationTask.kb_id == KnowledgeBase.id).where(*conds)
        if not is_admin:
            stmt = stmt.where(KnowledgeBase.owner_id == current_user.id)
        stmt = stmt.order_by(TranslationTask.created_at).limit(20000)
        selected = [str(item) for item in (await db.execute(stmt)).scalars().all()]
    if not selected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有符合条件的任务")
    job = TltBackfillJob(
        kb_id=body.kb_id,
        owner_id=current_user.id,
        task_ids=selected,
        chunk_size=body.chunk_size,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info("tlt backfill job %s created: %d tasks, chunk=%d", job.id, len(selected), job.chunk_size)
    return {"id": str(job.id), "total": len(selected), "chunk_size": job.chunk_size, "state": job.state}


@router.get("/backfill-jobs")
async def list_backfill_jobs(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    is_admin = await is_superadmin(db, current_user.id)
    stmt = select(TltBackfillJob).order_by(TltBackfillJob.created_at.desc()).limit(limit)
    if not is_admin:
        stmt = stmt.where(TltBackfillJob.owner_id == current_user.id)
    jobs = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(job.id),
                "state": job.state,
                "total": len(job.task_ids or []),
                "cursor": job.cursor,
                "chunk_size": job.chunk_size,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in jobs
        ]
    }


@router.delete("/backfill-jobs/{job_id}")
async def cancel_backfill_job(
    job_id: UUID,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await db.get(TltBackfillJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回填任务不存在")
    if job.owner_id != current_user.id and not await is_superadmin(db, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权取消该回填任务")
    if job.state == "active":
        job.state = "cancelled"
        await db.commit()
    return {"ok": True, "state": job.state}


# ── 资产库：文件夹 CRUD（虚拟分类树，物理文件不动）─────────────────────
class FolderCreate(BaseModel):
    name: str
    parent_id: UUID | None = None


class FolderPatch(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None


async def _folder_dup_check(db: AsyncSession, name: str, parent_id: UUID | None, exclude: UUID | None = None) -> None:
    stmt = select(TltFolder).where(TltFolder.name == name, TltFolder.parent_id == parent_id)
    if exclude is not None:
        stmt = stmt.where(TltFolder.id != exclude)
    if (await db.execute(stmt)).scalar() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同级已存在同名文件夹")


@router.get("/folders")
async def list_folders(
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.execute(select(TltFolder).order_by(TltFolder.name.asc()))).scalars()
    items = [{"id": str(f.id), "parent_id": str(f.parent_id) if f.parent_id else None, "name": f.name} for f in rows]
    return {"items": items, "total": len(items)}


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    req: FolderCreate,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹名不能为空")
    if req.parent_id is not None and await db.get(TltFolder, req.parent_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父文件夹不存在")
    await _folder_dup_check(db, name, req.parent_id)
    folder = TltFolder(name=name, parent_id=req.parent_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return {"id": str(folder.id), "parent_id": str(folder.parent_id) if folder.parent_id else None, "name": folder.name}


@router.patch("/folders/{folder_id}")
async def patch_folder(
    folder_id: UUID,
    req: FolderPatch,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    folder = await db.get(TltFolder, folder_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    if req.parent_id is not None and req.parent_id != folder.parent_id:
        # 移动：新父不能是自己或自己的后代（沿祖先链上溯检查）
        node = req.parent_id
        while node is not None:
            if node == folder.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移动到自身或其子文件夹内")
            parent = await db.get(TltFolder, node)
            node = parent.parent_id if parent else None
        if await db.get(TltFolder, req.parent_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标父文件夹不存在")
        folder.parent_id = req.parent_id
    if req.name is not None:
        name = req.name.strip()
        if name:
            folder.name = name
    await _folder_dup_check(db, folder.name, folder.parent_id, exclude=folder.id)
    await db.commit()
    return {"id": str(folder.id), "parent_id": str(folder.parent_id) if folder.parent_id else None, "name": folder.name}


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: UUID,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    folder = await db.get(TltFolder, folder_id)
    if folder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在")
    has_children = (await db.execute(select(func.count()).select_from(TltFolder).where(TltFolder.parent_id == folder_id))).scalar()
    if (has_children or 0) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件夹非空（含子文件夹）")
    has_tasks = (
        await db.execute(
            select(func.count())
            .select_from(TranslationTask)
            .where(
                TranslationTask.folder_id == folder_id,
                TranslationTask.state.notin_(["archived", "cancelled", "superseded"]),
            )
        )
    ).scalar()
    if (has_tasks or 0) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件夹内仍有文件，请先移出")
    # 已归档/终态任务脱离文件夹（FK 约束；归档资产视为「未归夹」历史件）
    from sqlalchemy import update as _update

    await db.execute(_update(TranslationTask).where(TranslationTask.folder_id == folder_id).values(folder_id=None))
    await db.delete(folder)
    await db.commit()
    return {"ok": True}


# ── 资产库：上传（多文件 → 存原件 → stored 任务）──────────────────────


def _same_source_name(uploaded_name: str, source_uri: str | None) -> bool:
    """判断旧任务是否同一逻辑文件（上传端同名冲突会追加 ``-N`` 后缀）。"""
    base = Path(source_uri or "").name
    if not base or not uploaded_name:
        return False
    if base == uploaded_name:
        return True
    target = Path(uploaded_name)
    stem, suffix = target.stem, target.suffix
    prefix = f"{stem}-"
    if not base.startswith(prefix):
        return False
    if suffix and not base.endswith(suffix):
        return False
    middle = base[len(prefix) : len(base) - len(suffix)] if suffix else base[len(prefix) :]
    return middle.isdigit()


@router.post("/upload")
async def upload_assets(
    files: list[UploadFile] = File(...),
    folder_id: UUID | None = Form(None),
    kb_id: UUID | None = Form(None),
    current_user=Depends(require_permission("kb:upload")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """资产库上传：存原件 + 建 stored 任务（不入队；用户在库内点「翻译」→ pending）。

    多 RAG 知识库：显式 kb_id 优先；缺省时恰一库自动、0/多库报错引导。
    单次 ≤100 个；更大批量走 scheduled_tasks 批量通道。
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未选择文件")
    if len(files) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多 100 个文件；更大批量请分批上传后使用批量翻译")
    # 多 RAG 知识库：显式 kb_id 优先；缺省时恰一库自动、0/多库报错引导
    enabled_kbs = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.translation_enabled.is_(True)).order_by(KnowledgeBase.created_at.asc()))).scalars().all()
    if kb_id is not None:
        kb = await db.get(KnowledgeBase, kb_id)
        if kb is None or not kb.translation_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标知识库不存在或未加入翻译体系")
    elif len(enabled_kbs) == 1:
        kb = enabled_kbs[0]
    elif len(enabled_kbs) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无翻译知识库：请先在设置页「RAG知识库配置」创建或添加")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="存在多个翻译知识库：请选择目标知识库后重试")
    is_admin = await is_superadmin(db, current_user.id)
    if kb.owner_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无资产知识库上传权限")
    if folder_id is not None and await db.get(TltFolder, folder_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标文件夹不存在")

    # B1: dataset 就绪探活 + 悬空自愈；RAGFlow 不可用不阻断上传（D2 失败开放）
    rf_client = RAGFlowClient()
    dataset_ready = True
    try:
        await ensure_dataset(kb, client=rf_client)
        await db.commit()  # ensure_dataset 可能自愈回写 kb.ragflow_dataset_id
    except Exception:
        dataset_ready = False
        logger.warning("tlt upload: ragflow unavailable, originals not indexed this batch", exc_info=True)

    from app.extensions.config import get_extensions_config

    upload_dir = Path(get_extensions_config().storage.base_path) / "translation" / uuid.uuid4().hex[:8]
    upload_dir.mkdir(parents=True, exist_ok=True)

    results = []
    # 魔数校验（EAI-CUSTOM）：拒绝改名/导出坏的伪文件（如 is_pdf=False 的假 PDF，
    # 上传侧早失败优于 babeldoc/worker 阶段诡异报错）。txt/md 纯文本跳过。
    _MAGIC = {
        ".pdf": b"%PDF-",
        ".docx": b"PK\x03\x04",
        ".doc": b"\xd0\xcf\x11\xe0",
        ".xlsx": b"PK\x03\x04",
        ".xlsm": b"PK\x03\x04",
        ".pptx": b"PK\x03\x04",
        ".ppt": b"\xd0\xcf\x11\xe0",
    }
    for f in files:
        content = await f.read()
        name = Path(f.filename or "file").name or "file"
        expect_magic = _MAGIC.get(Path(name).suffix.lower())
        if expect_magic and not content.startswith(expect_magic):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件内容与扩展名不符（{Path(name).suffix} 非有效文件头）：{name}。请确认导出/保存格式正确后重新上传。",
            )
        sha = hashlib.sha256(content).hexdigest()
        # 幂等：同 KB 同 sha 已有非终态任务 → 跳过建行（并跳过落盘，避免孤儿文件）
        dup = (
            await db.execute(
                select(TranslationTask)
                .where(
                    TranslationTask.kb_id == kb.id,
                    TranslationTask.doc_sha == sha,
                    TranslationTask.state.notin_(["archived", "cancelled", "superseded"]),
                )
                .limit(1)
            )
        ).scalar()
        if dup is not None:
            results.append(
                {
                    "task_id": str(dup.id),
                    "file": name,
                    "reused": True,
                    "existing_file": Path(dup.source_uri).name if dup.source_uri else None,
                    "existing_folder_id": str(dup.folder_id) if dup.folder_id else None,
                }
            )
            continue
        dest = upload_dir / name
        i = 1
        while dest.exists():
            dest = upload_dir / f"{Path(name).stem}-{i}{Path(name).suffix}"
            i += 1
        dest.write_bytes(content)
        # P0-3: 入库即判定语言/内容 tag（扫描件 deferred 到 worker OCR 后回写）。
        source_lang, content_tag = "mixed", None
        try:
            blocks = await asyncio.to_thread(parse_document, str(dest))
            source_lang = detect_language(blocks_text(blocks)) or "mixed"
            content_tag = classify_tag(blocks)
        except OcrRequired:
            pass
        except Exception:
            logger.warning("tlt upload: detect lang/tag failed for %s (defer to worker)", name, exc_info=True)
        # 终态历史版本仍占用 (kb, sha, version) 唯一键：同内容归档后重传需递增版本，
        # 否则 INSERT 会撞 uq_tlt_task_kb_sha_version → 500。
        max_version = (
            await db.execute(
                select(func.max(TranslationTask.task_version)).where(
                    TranslationTask.kb_id == kb.id,
                    TranslationTask.doc_sha == sha,
                )
            )
        ).scalar()
        task = TranslationTask(
            kb_id=kb.id,
            doc_sha=sha,
            source_uri=str(dest),
            source_lang=source_lang,
            content_tag=content_tag,
            state="skipped" if source_lang == "zh" else "stored",
            folder_id=folder_id,
            task_version=(max_version or 0) + 1,
        )
        if dataset_ready:
            try:
                task.ragflow_source_doc_id = await index_original(task, dest, kb=kb, client=rf_client)
            except Exception:
                logger.warning("tlt upload: original index failed for %s (fail-open)", name, exc_info=True)
        db.add(task)
        await db.flush()
        # P1-4 重传即替换：同 KB 同逻辑文件名、不同 sha 的旧任务 → superseded，
        # 旧 RAGFlow 原文/中文份下线（交付物文件保留为归档，不物理删）。
        superseded: list[TranslationTask] = []
        old_rows = (
            (
                await db.execute(
                    select(TranslationTask).where(
                        TranslationTask.kb_id == kb.id,
                        TranslationTask.id != task.id,
                        TranslationTask.doc_sha != sha,
                        TranslationTask.state.notin_(["archived", "cancelled", "superseded"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        for old in old_rows:
            if not _same_source_name(name, old.source_uri):
                continue
            old.state = "superseded"
            old.superseded_by = task.id
            superseded.append(old)
        if superseded and dataset_ready and kb.ragflow_dataset_id:
            for old in superseded:
                for doc_id in {old.ragflow_source_doc_id, old.ragflow_zh_doc_id}:
                    if not doc_id:
                        continue
                    try:
                        await rf_client.delete_document(kb.ragflow_dataset_id, doc_id)
                    except Exception:
                        logger.warning("tlt supersede: delete RAGFlow doc %s failed (stale chunks may remain)", doc_id, exc_info=True)
        results.append({"task_id": str(task.id), "file": name, "reused": False, "superseded": [str(t.id) for t in superseded]})
    await db.commit()
    return {"items": results, "kb_id": str(kb.id), "count": len(results)}


@router.patch("/tasks/{task_id}/folder")
async def patch_task_folder(
    task_id: UUID,
    body: TaskFolderPatch,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """资产库拖拽移动：只改 folder_id 指针，物理文件不动。"""
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if body.folder_id is not None and await db.get(TltFolder, body.folder_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标文件夹不存在")
    task.folder_id = body.folder_id
    await db.commit()
    await db.refresh(task)
    return TaskOut.from_row(task).model_dump(mode="json")


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除文档：状态 → archived，并下线该任务在 RAGFlow 的原文/中文份；交付物留档。"""
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if task.state in {"archived", "cancelled", "superseded"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已在库外（已归档/取消/替代）")
    kb = await db.get(KnowledgeBase, task.kb_id)
    dataset_id = kb.ragflow_dataset_id if kb else None
    task.state = "archived"
    await db.commit()
    # P1-5 / R3-3: 中文份与原文 chunk 同步下线；交付物文件保留（归档不物理删）。
    deleted: list[str] = []
    if dataset_id:
        client = RAGFlowClient()
        for doc_id in {task.ragflow_source_doc_id, task.ragflow_zh_doc_id}:
            if not doc_id:
                continue
            try:
                await client.delete_document(dataset_id, doc_id)
                deleted.append(doc_id)
            except Exception:
                logger.warning("tlt delete: offline RAGFlow doc %s failed (task %s)", doc_id, task.id, exc_info=True)
    return {"ok": True, "state": "archived", "deleted_docs": deleted}


# ── 资产库：原件/交付物 下载与预览 ─────────────────────────────────────


@router.get("/tasks/{task_id}/source")
async def download_source(
    task_id: UUID,
    inline: bool = Query(default=False),
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
):
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not task.source_uri:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文件已不存在")
    path, temp = await _resolve_download_path(task.source_uri, "源文件已不存在")
    background = BackgroundTask(path.unlink) if temp else None
    if inline:
        # 内嵌预览（无 attachment 头，浏览器原生渲染 PDF）
        return FileResponse(path, background=background)
    return FileResponse(path, filename=Path(task.source_uri).name, background=background)


def _draft_markdown(task: TranslationTask) -> str | None:
    """exceeded 任务的逐块草稿 → Markdown（复核页“下载当前译本”用）。"""
    if not task.draft_blocks:
        return None
    return build_markdown(task, task.draft_blocks)


async def _resolve_download_path(uri: str, missing: str) -> tuple[Path, bool]:
    """本地路径直返；s3:// 落到临时文件（is_temp=True，由调用方后台清理）。"""
    if uri.startswith("s3://"):
        return await get_storage_provider().download_to_temp(uri), True
    if uri.startswith("http"):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="远程 URL 下载待支持")
    path = Path(uri)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing)
    return path, False


@router.get("/tasks/{task_id}/deliverable")
async def download_deliverable(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
):
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not task.deliverable_uri:
        markdown = _draft_markdown(task)
        if markdown is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚无交付物")
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="tlt-{task.id}.zh.md"'},
        )
    path, temp = await _resolve_download_path(task.deliverable_uri, "交付物文件已不存在")
    background = BackgroundTask(path.unlink) if temp else None
    return FileResponse(path, filename=Path(task.deliverable_uri).name, background=background)


@router.get("/tasks/{task_id}/deliverable/preview")
async def preview_deliverable(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
):
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not task.deliverable_uri:
        markdown = _draft_markdown(task)
        if markdown is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚无交付物")
        return Response(content=markdown, media_type="text/markdown; charset=utf-8")
    path, temp = await _resolve_download_path(task.deliverable_uri, "交付物文件已不存在")
    background = BackgroundTask(path.unlink) if temp else None
    return FileResponse(path, media_type="text/markdown; charset=utf-8", background=background)


# ── 术语库（语言维度 + Excel 导入；yaml 原子读写）─────────────────────


class GlossaryEntryOut(BaseModel):
    source: str
    lang: str = "any"  # en | fr | any
    action: str  # force | forbid | keep
    target: str | None = None
    domains: list[str] = []
    notes: str | None = None


class GlossaryPutBody(BaseModel):
    entries: list[GlossaryEntryOut]
    base_version: str | None = None


def _glossary_path() -> Path:
    return resolve_glossary_path()


def _entry_out(entry: GlossaryEntry) -> GlossaryEntryOut:
    return GlossaryEntryOut(
        source=entry.source,
        lang=entry.lang,
        action=entry.action,
        target=entry.target,
        domains=entry.domains,
        notes=entry.notes,
    )


def _validate_entries(entries: list[GlossaryEntryOut]) -> list[GlossaryEntry]:
    """PUT 全表校验：动作/语言白名单、force 必须给目标、(source, lang) 唯一。"""
    seen: dict[tuple[str, str], int] = {}
    validated: list[GlossaryEntry] = []
    for idx, item in enumerate(entries, start=1):
        source = item.source.strip()
        lang = (item.lang or "any").strip().lower()
        action = (item.action or "").strip().lower()
        target = (item.target or "").strip() or None
        domains = clean_domains(item.domains)
        notes = (item.notes or "").strip() or None

        if not source:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"第 {idx} 条：源词为空")
        if lang not in LANGS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"第 {idx} 条：语言必须为 en / fr / any")
        if action not in ACTIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"第 {idx} 条：动作必须为 force / forbid / keep")
        if action == "force" and not target:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"第 {idx} 条：指定译法缺少目标译法")
        if action != "force":
            target = None

        key = (source.casefold(), lang)
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"第 {idx} 条与第 {seen[key]} 条重复（同一源词与语言只允许一条）",
            )
        seen[key] = idx
        validated.append(GlossaryEntry(source=source, action=action, target=target, lang=lang, domains=domains, notes=notes))
    return validated


@router.get("/glossary")
async def get_glossary_entries(
    _current_user=Depends(require_permission("translation:read")),
) -> dict:
    path = _glossary_path()
    entries = read_entries(path)
    return {
        "entries": [_entry_out(e).model_dump() for e in entries],
        "count": len(entries),
        "version": file_version(path),
    }


@router.put("/glossary")
async def put_glossary_entries(
    body: GlossaryPutBody,
    _current_user=Depends(require_permission("translation:transition")),
) -> dict:
    path = _glossary_path()
    current_version = file_version(path)
    if body.base_version is not None and body.base_version != current_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="术语库已被他人修改，请刷新后重试",
        )
    entries = _validate_entries(body.entries)
    write_entries(path, entries)
    return {
        "entries": [_entry_out(e).model_dump() for e in read_entries(path)],
        "count": len(entries),
        "version": file_version(path),
    }


@router.post("/glossary/import")
async def import_glossary(
    file: UploadFile = File(...),
    _current_user=Depends(require_permission("translation:transition")),
) -> dict:
    """解析 Excel/CSV 并返回预览 + 合并结果；确认仍走 PUT（复用版本校验）。"""
    if (file.size or 0) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件超过 2 MB 上限")
    data = await file.read()
    try:
        parsed = parse_glossary_file(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    path = _glossary_path()
    result = merge_glossary_import(read_entries(path), parsed)
    return {
        "version": file_version(path),
        "rows": [
            {
                "row": row.row,
                "source": row.source,
                "lang": row.lang,
                "action": row.action,
                "target": row.target,
                "domains": row.domains,
                "notes": row.notes,
                "status": row.status,
                "errors": row.errors,
            }
            for row in result.rows
        ],
        "summary": result.summary,
        "merged_entries": [
            {
                "source": e.source,
                "lang": e.lang,
                "action": e.action,
                "target": e.target,
                "domains": e.domains,
                "notes": e.notes,
            }
            for e in result.merged
        ],
    }


# ── RAG 知识库配置（多库）：建/列/改/启停 ─────────────────────────────


async def _require_superadmin(db: AsyncSession, current_user) -> None:
    if not await is_superadmin(db, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可管理检索知识库")


class RagKbCreate(BaseModel):
    name: str
    description: str | None = None
    language: str | None = None  # Chinese | English（create 不收，create 后 update 落地）
    permission: str | None = None  # me | team
    embedding_model: str | None = None
    chunk_method: str | None = None
    parser_config: dict | None = None
    pagerank: int | None = None


class RagKbUpdate(BaseModel):
    description: str | None = None
    language: str | None = None
    permission: str | None = None
    embedding_model: str | None = None
    chunk_method: str | None = None
    parser_config: dict | None = None
    pagerank: int | None = None


class RagKbEnabled(BaseModel):
    enabled: bool


class TranslationModelUpdate(BaseModel):
    translation_model: str | None = None


# ── 翻译模型选择（EAI-CUSTOM，与对话模型独立；worker 每次任务读取）────────


@router.get("/models")
async def list_translation_models(
    current_user=Depends(require_permission("translation:read")),
) -> dict:
    """可选模型 + 当前 UI 设置 + 实际生效模型（设置 > 环境变量 > config 首项）。"""
    from deerflow.config import get_app_config

    models = get_app_config().models
    names = [m.name for m in models]
    data = await asyncio.to_thread(read_translation_settings)
    raw = data.get(SETTINGS_KEY)
    setting = raw if isinstance(raw, str) and raw in names else None
    return {
        "items": [{"name": m.name, "display_name": getattr(m, "display_name", None) or m.name} for m in models],
        "setting": setting,
        "effective": resolve_effective_model_name(setting, names),
    }


@router.put("/models")
async def set_translation_model(
    body: TranslationModelUpdate,
    current_user=Depends(require_permission("translation:transition")),
) -> dict:
    """保存翻译模型；null = 跟随环境变量/config 首项。"""
    from deerflow.config import get_app_config

    names = [m.name for m in get_app_config().models]
    name = body.translation_model.strip() if isinstance(body.translation_model, str) else None
    name = name or None
    if name is not None and name not in names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模型不存在或未在 config.yaml models 中声明")
    data = await asyncio.to_thread(read_translation_settings)
    if name is None:
        data.pop(SETTINGS_KEY, None)
    else:
        data[SETTINGS_KEY] = name
    await asyncio.to_thread(write_translation_settings, data)
    return {"setting": name, "effective": resolve_effective_model_name(name, names)}


@router.get("/rag-kbs/embedding-models")
async def list_embedding_models(
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_superadmin(db, current_user)
    models = await RAGFlowClient().list_available_embedding_models()
    return {"items": models}


@router.get("/rag-kbs")
async def list_rag_kbs(
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """翻译体系内 KB 清单：PG 摘要 + RAGFlow 配置回读 + 文档/待处理聚合。"""
    await _require_superadmin(db, current_user)
    rows = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.translation_enabled.is_(True)).order_by(KnowledgeBase.created_at.asc()))).scalars().all()
    client = RAGFlowClient()
    items = []
    for kb in rows:
        item = {
            "id": str(kb.id),
            "name": kb.name,
            "description": kb.description,
            "language": kb.language,
            "chunk_method": kb.chunk_method,
            "embedding_model": kb.embedding_model,
            "permission": None,
            "parser_config": None,
            "pagerank": None,
            "ragflow_linked": bool(kb.ragflow_dataset_id),
            "ragflow_dataset_id": kb.ragflow_dataset_id,
        }
        if kb.ragflow_dataset_id:
            try:
                ds = (await client.get_dataset(kb.ragflow_dataset_id)).get("data") or {}
                item.update(
                    {
                        "language": ds.get("language") or kb.language,
                        "chunk_method": ds.get("chunk_method") or ds.get("parser_id") or kb.chunk_method,
                        "embedding_model": ds.get("embedding_model") or kb.embedding_model,
                        "permission": ds.get("permission"),
                        "parser_config": ds.get("parser_config"),
                        "pagerank": ds.get("pagerank"),
                    }
                )
            except Exception:
                logger.warning("rag-kb detail fetch failed for kb %s", kb.id, exc_info=True)
        item["doc_count"] = (await db.execute(select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id))).scalar() or 0
        item["pending_count"] = (
            await db.execute(
                select(func.count())
                .select_from(TranslationTask)
                .where(
                    TranslationTask.kb_id == kb.id,
                    TranslationTask.state.notin_(list(TERMINAL_STATES)),
                )
            )
        ).scalar() or 0
        items.append(item)
    return {"items": items, "total": len(items)}


@router.post("/rag-kbs", status_code=status.HTTP_201_CREATED)
async def create_rag_kb(
    body: RagKbCreate,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """建库全参数：RAGFlow create（permission/chunk_method/parser_config）→ update 补 language/pagerank → PG 行 translation_enabled=true。"""
    await _require_superadmin(db, current_user)
    client = RAGFlowClient()
    embed = body.embedding_model
    if not embed:
        available = await client.list_available_embedding_models()
        if not available:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="RAGFlow 无可用 embedding 模型")
        embed = available[0]
    rf = await client.create_dataset(
        name=body.name,
        description=body.description or "",
        embedding_model=embed,
        chunk_method=body.chunk_method,
        parser_config=body.parser_config,
        permission=body.permission,
    )
    dataset_id = (rf.get("data") or {}).get("id")
    if not dataset_id:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"RAGFlow create_dataset 未返回 id: {str(rf)[:200]}")
    follow_up = {}
    if body.language:
        follow_up["language"] = body.language
    if body.pagerank is not None:
        follow_up["pagerank"] = body.pagerank
    if follow_up:
        try:
            await client.update_dataset(dataset_id, **follow_up)
        except Exception:
            logger.warning("rag-kb %s: create 后 update 补参失败（language/pagerank）", dataset_id, exc_info=True)
    kb = KnowledgeBase(
        name=body.name,
        description=body.description,
        owner_id=current_user.id,
        kb_type="ragflow",
        embedding_model=embed,
        chunk_method=body.chunk_method,
        language=body.language or "Chinese",
        ragflow_dataset_id=dataset_id,
        translation_enabled=True,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return {"id": str(kb.id), "ragflow_dataset_id": dataset_id}


@router.put("/rag-kbs/{kb_id}")
async def update_rag_kb(
    kb_id: UUID,
    body: RagKbUpdate,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """改配置（编辑对话框保存通道）：update_dataset 全字段 + PG chunk_method 摘要同步。"""
    await _require_superadmin(db, current_user)
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or not kb.translation_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在或未加入翻译体系")
    if not kb.ragflow_dataset_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该库未关联 RAGFlow，无可编辑配置")
    kwargs = {
        k: v
        for k, v in {
            "description": body.description,
            "chunk_method": body.chunk_method,
            "parser_config": body.parser_config,
            "permission": body.permission,
            "language": body.language,
            "pagerank": body.pagerank,
        }.items()
        if v is not None
    }
    await RAGFlowClient().update_dataset(kb.ragflow_dataset_id, **kwargs)
    if body.chunk_method:
        kb.chunk_method = body.chunk_method
        db.add(kb)
        await db.commit()
    return {"ok": True}


@router.put("/rag-kbs/{kb_id}/enabled")
async def set_rag_kb_enabled(
    kb_id: UUID,
    body: RagKbEnabled,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """加/移出翻译体系（多库无互斥）。"""
    await _require_superadmin(db, current_user)
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    kb.translation_enabled = body.enabled
    await db.commit()
    return {"ok": True, "enabled": kb.translation_enabled}


@router.post("/backfill-sources")
async def backfill_sources(
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """B2 一次性回填（superadmin）：原文 doc_id 缺失的任务补录原文；delivered 译本悬空的补回新 dataset。手动触发，无调度。"""
    await _require_superadmin(db, current_user)
    client = RAGFlowClient()
    results = []
    tasks = (
        (
            await db.execute(
                select(TranslationTask).where(
                    TranslationTask.ragflow_source_doc_id.is_(None),
                    TranslationTask.state.notin_(list(TERMINAL_STATES)),
                )
            )
        )
        .scalars()
        .all()
    )
    for t in tasks:
        if not t.source_uri or t.source_uri.startswith(("s3://", "http")) or not Path(t.source_uri).exists():
            results.append({"task_id": str(t.id), "action": "error", "detail": "source file missing"})
            continue
        kb = await db.get(KnowledgeBase, t.kb_id)
        if kb is None:
            results.append({"task_id": str(t.id), "action": "error", "detail": "kb vanished"})
            continue
        try:
            doc_id = await index_original(t, Path(t.source_uri), kb=kb, client=client)
            t.ragflow_source_doc_id = doc_id
            results.append({"task_id": str(t.id), "action": "source_indexed" if doc_id else "source_skipped"})
        except Exception as exc:
            results.append({"task_id": str(t.id), "action": "error", "detail": str(exc)[:200]})
    delivered = (await db.execute(select(TranslationTask).where(TranslationTask.state == "delivered", TranslationTask.ragflow_zh_doc_id.is_not(None)))).scalars().all()
    for t in delivered:
        kb = await db.get(KnowledgeBase, t.kb_id)
        if kb is None or not kb.ragflow_dataset_id:
            continue
        try:
            if await _doc_exists(client, kb.ragflow_dataset_id, t.ragflow_zh_doc_id):
                continue
            new_id = await reindex_deliverable(t, kb=kb, client=client)
            if new_id:
                t.ragflow_zh_doc_id = new_id
                results.append({"task_id": str(t.id), "action": "zh_reindexed"})
        except Exception as exc:
            results.append({"task_id": str(t.id), "action": "error", "detail": str(exc)[:200]})
    await db.commit()
    return {"results": results, "total": len(results)}
