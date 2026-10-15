"""Translation task API (EAI-CUSTOM) — /api/extensions/translation.

S1 骨架（eng-review T2/T5 的 API 面）：任务列表/详情/状态流转。
MCP 工具（translate_document/translation_status）与 worker 在 T4/T5 接入，
复用同一 state 机校验（validate_transition）。
"""

import hashlib
import logging
import os
import tempfile
import uuid
from pathlib import Path
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.admin import is_superadmin
from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.models import Document, KnowledgeBase
from app.extensions.translation.models import (
    STATES,
    TERMINAL_STATES,
    TltFolder,
    TranslationTask,
    validate_transition,
)
from app.extensions.translation.ragflow_bridge import _doc_exists, ensure_dataset, index_original, reindex_deliverable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/translation", tags=["Translation"])


class TransitionRequest(BaseModel):
    target: str
    note: str | None = None


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


async def _get_task_scoped(
    task_id: UUID, current_user, is_admin: bool, db: AsyncSession
) -> TranslationTask:
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
    is_admin = await is_superadmin(db, current_user.id)
    conds = []
    if state is not None:
        conds.append(TranslationTask.state == state)
    else:
        conds.append(TranslationTask.state.notin_(["archived", "cancelled", "superseded"]))
    if kb_id is not None:
        conds.append(TranslationTask.kb_id == kb_id)
    if folder_id == "root":
        conds.append(TranslationTask.folder_id.is_(None))
    elif folder_id:
        conds.append(TranslationTask.folder_id == UUID(folder_id))
    if q:
        conds.append(or_(TranslationTask.source_uri.ilike(f"%{q}%"), TranslationTask.doc_sha.ilike(f"{q}%")))

    base = (
        select(TranslationTask, KnowledgeBase.name)
        .join(KnowledgeBase, TranslationTask.kb_id == KnowledgeBase.id)
        .where(*conds)
    )
    if not is_admin:
        base = base.where(KnowledgeBase.owner_id == current_user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            base.order_by(TranslationTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [TaskOut.from_row(t, kb_name=name).model_dump(mode="json") for t, name in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
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
    task.state = req.target
    if req.target == "retrying":
        task.retry_count += 1
    if req.note:
        detail = dict(task.error_detail or {})
        detail.setdefault("notes", []).append({"from": prev_state, "target": req.target, "note": req.note})
        task.error_detail = detail
    await db.commit()
    # updated_at 由 onupdate=func.now() 服务端生成，flush 后属性已过期；
    # AsyncSession 下直接读会 MissingGreenlet（同 create_folder 的 refresh 手法）
    await db.refresh(task)
    logger.info("tlt task %s transitioned %s -> %s by %s", task.id, prev_state, req.target, current_user.id)
    return TaskOut.from_row(task).model_dump(mode="json")


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
    has_children = (
        await db.execute(select(func.count()).select_from(TltFolder).where(TltFolder.parent_id == folder_id))
    ).scalar()
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多 100 个文件；更大批量请走定时任务通道")
    # 多 RAG 知识库：显式 kb_id 优先；缺省时恰一库自动、0/多库报错引导
    enabled_kbs = (
        await db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.translation_enabled.is_(True))
            .order_by(KnowledgeBase.created_at.asc())
        )
    ).scalars().all()
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
                detail=f"文件内容与扩展名不符（{Path(name).suffix} 非有效文件头）：{name}。"
                "请确认导出/保存格式正确后重新上传。",
            )
        dest = upload_dir / name
        i = 1
        while dest.exists():
            dest = upload_dir / f"{Path(name).stem}-{i}{Path(name).suffix}"
            i += 1
        dest.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        # 幂等：同 KB 同 sha 已有非终态任务 → 跳过建行
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
            results.append({"task_id": str(dup.id), "file": name, "reused": True})
            continue
        task = TranslationTask(
            kb_id=kb.id,
            doc_sha=sha,
            source_uri=str(dest),
            source_lang="mixed",
            state="stored",
            folder_id=folder_id,
        )
        if dataset_ready:
            try:
                task.ragflow_source_doc_id = await index_original(task, dest, kb=kb, client=rf_client)
            except Exception:
                logger.warning("tlt upload: original index failed for %s (fail-open)", name, exc_info=True)
        db.add(task)
        await db.flush()
        results.append({"task_id": str(task.id), "file": name, "reused": False})
    await db.commit()
    return {"items": results, "kb_id": str(kb.id), "count": len(results)}


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    current_user=Depends(require_permission("translation:transition")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """库删除：状态 → archived（移出列表；交付物按 R3-3 归档不物理删，可救）。"""
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if task.state in TERMINAL_STATES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已在库外（已归档/取消/替代）")
    task.state = "archived"
    await db.commit()
    return {"ok": True, "state": "archived"}


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
    if not task.source_uri or task.source_uri.startswith(("s3://", "http")):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="远程存储原件下载待支持")
    if not Path(task.source_uri).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文件已不存在")
    if inline:
        # 内嵌预览（无 attachment 头，浏览器原生渲染 PDF）
        return FileResponse(task.source_uri)
    return FileResponse(task.source_uri, filename=Path(task.source_uri).name)


@router.get("/tasks/{task_id}/deliverable")
async def download_deliverable(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
):
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not task.deliverable_uri:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚无交付物")
    if task.deliverable_uri.startswith(("s3://", "http")):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="远程存储交付物下载待支持")
    if not Path(task.deliverable_uri).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交付物文件已不存在")
    return FileResponse(task.deliverable_uri, filename=Path(task.deliverable_uri).name)


@router.get("/tasks/{task_id}/deliverable/preview")
async def preview_deliverable(
    task_id: UUID,
    current_user=Depends(require_permission("translation:read")),
    db: AsyncSession = Depends(get_db),
):
    is_admin = await is_superadmin(db, current_user.id)
    task = await _get_task_scoped(task_id, current_user, is_admin, db)
    if not task.deliverable_uri:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚无交付物")
    if task.deliverable_uri.startswith(("s3://", "http")):
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="远程存储预览待支持")
    p = Path(task.deliverable_uri)
    if not p.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交付物文件已不存在")
    return FileResponse(p, media_type="text/markdown; charset=utf-8")


# ── 术语库 CRUD（yaml 原子读写，参照 roles_custom overlay 模式）─────────


class GlossaryEntryOut(BaseModel):
    source: str
    action: str  # force | forbid | keep
    target: str | None = None


class GlossaryPutBody(BaseModel):
    entries: list[GlossaryEntryOut]


def _glossary_yaml_path() -> Path:
    env = os.environ.get("EAI_TRANSLATION_GLOSSARY")
    if env:
        return Path(env)
    return Path("config/translation_glossary.yaml")


def _read_glossary_entries(path: Path) -> list[GlossaryEntryOut]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for t in data.get("terms") or []:
        src = str(t.get("source", "")).strip()
        action = str(t.get("action", "force")).strip().lower()
        target = str(t.get("target", "")).strip() or None
        if src:
            out.append(GlossaryEntryOut(source=src, action=action, target=target))
    return out


def _write_glossary_yaml(path: Path, entries: list[GlossaryEntryOut]) -> None:
    lines = ["terms:"]
    for e in entries:
        lines.append(f"  - source: {e.source}")
        lines.append(f"    action: {e.action}")
        if e.target:
            lines.append(f"    target: {e.target}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".yaml", dir=str(path.parent), prefix=".glossary-")
    os.close(fd)
    try:
        Path(tmp).write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@router.get("/glossary")
async def get_glossary_entries(
    _current_user=Depends(require_permission("translation:read")),
) -> dict:
    path = _glossary_yaml_path()
    entries = _read_glossary_entries(path)
    return {"entries": [e.model_dump() for e in entries], "count": len(entries)}


@router.put("/glossary")
async def put_glossary_entries(
    body: GlossaryPutBody,
    _current_user=Depends(require_permission("translation:transition")),
) -> dict:
    _write_glossary_yaml(_glossary_yaml_path(), body.entries)
    entries = _read_glossary_entries(_glossary_yaml_path())
    return {"entries": [e.model_dump() for e in entries], "count": len(entries)}


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
        await db.execute(
            select(TranslationTask).where(
                TranslationTask.ragflow_source_doc_id.is_(None),
                TranslationTask.state.notin_(list(TERMINAL_STATES)),
            )
        )
    ).scalars().all()
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
    delivered = (
        await db.execute(
            select(TranslationTask).where(
                TranslationTask.state == "delivered", TranslationTask.ragflow_zh_doc_id.is_not(None)
            )
        )
    ).scalars().all()
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
