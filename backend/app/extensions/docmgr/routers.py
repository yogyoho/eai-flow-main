"""AI Document routers for extensions module."""

import asyncio
import json
import logging
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.middleware import require_permission, with_data_scope
from app.extensions.database import get_db
from app.extensions.docmgr.folder_service import FolderService
from app.extensions.docmgr.service import AIDocumentService, _StaleWrite
from app.extensions.docmgr.share_schemas import ShareCreateRequest, ShareResponse
from app.extensions.docmgr.share_service import ShareService
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentListResponse,
    AIDocumentResponse,
    AIDocumentUpdate,
    CurrentUser,
    FolderDeleteConfirm,
    FolderListResponse,
    FolderResponse,
    FolderTreeResponse,
    FolderUpdate,
    MessageResponse,
    PersonalDocShareRequest,
    PersonalDocStarRequest,
    PersonalOutputsResponse,
    PersonalVersionCreateRequest,
    PersonalVersionDetailResponse,
    PersonalVersionListResponse,
    ProjectDocContentRequest,
    ProjectOutputsResponse,
    ProjectVersionDetailResponse,
    ProjectVersionListResponse,
)
from deerflow.config.paths import Paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["AI Documents"])

# EAI-CUSTOM: BlockNote uploadFile 图片上传——白名单/大小上限（SVG 因 artifacts 强制下载防 XSS 而排除）
_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_IMAGE_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


class ThreadImageResponse(BaseModel):
    url: str


class SyncThreadFilesRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=100)


class MoveRequest(BaseModel):
    folder: str | None = Field(None, max_length=255)
    to_documents: bool = False


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class BatchDeleteRequest(BaseModel):
    ids: list[UUID] = Field(..., min_length=1, max_length=50)


class CreateFolderRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: UUID | None = Field(None, description="Parent folder ID")
    project_id: UUID | None = Field(None, description="Project ID for root folder binding")


@router.get("/documents", response_model=AIDocumentListResponse)
async def list_documents(
    folder: str | None = Query(None, description="Filter by folder name"),
    folder_id: UUID | None = Query(None, description="Filter by folder ID (new)"),
    starred: bool | None = Query(None, description="Filter by starred status"),
    shared: bool | None = Query(None, description="Filter by shared status"),
    doc_type: str | None = Query(None, description="Filter by doc_type: document or file_ref"),
    project_scope: str | None = Query(None, description="Filter by project scope: personal or project"),
    project_id: UUID | None = Query(None, description="Filter by specific project ID"),
    q: str | None = Query(None, description="Search query for title"),
    skip: int = Query(0, ge=0),
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
    # EAI-CUSTOM (Task 13): scope from ABAC engine — for roles bound to
    # doc_owner + doc_project_member this reproduces the prior
    # (user_id == caller OR project_id IN member_projects) clause; superadmin
    # gets allow_all; future deny_data_scopes can narrow this further.
    scope: FilterRule = Depends(with_data_scope("docmgr")),
):
    """List all documents for the current user."""
    documents, total = await AIDocumentService.list_docs(
        db,
        user_id=current_user.id,
        folder=folder,
        folder_id=folder_id,
        starred=starred,
        shared=shared,
        doc_type=doc_type,
        project_scope=project_scope,
        project_id=project_id,
        q=q,
        skip=skip,
        limit=limit,
        scope=scope,
    )
    return AIDocumentListResponse(
        documents=[await AIDocumentService.to_response(doc) for doc in documents],
        total=total,
    )


@router.get("/documents/{doc_id}", response_model=AIDocumentResponse)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
    # EAI-CUSTOM (Task L2): by-id routes through the same scope engine as
    # list_docs so deny_data_scopes narrows by-id fetches too. For roles bound
    # to doc_owner + doc_project_member the compiled predicate is identical to
    # the prior hand-rolled (user_id == caller OR project_id IN member_projects)
    # clause; superadmin gets allow_all.
    scope: FilterRule = Depends(with_data_scope("docmgr")),
):
    """Get a specific document by ID."""
    document = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return await AIDocumentService.to_detail_response(document)


@router.post("/documents", response_model=AIDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: AIDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Create a new document."""
    document = await AIDocumentService.create(db, current_user.id, data)
    return await AIDocumentService.to_response(document)


@router.put("/documents/{doc_id}", response_model=AIDocumentResponse)
async def update_document(
    doc_id: UUID,
    data: AIDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Update a document."""
    document = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    document = await AIDocumentService.update(db, document, data)
    return await AIDocumentService.to_response(document)


@router.delete("/documents/{doc_id}", response_model=MessageResponse)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:delete")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Delete a document."""
    document = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await AIDocumentService.delete(db, document)
    return MessageResponse(message="Document deleted successfully")


@router.put("/documents/{doc_id}/move", response_model=AIDocumentResponse)
async def move_document(
    doc_id: UUID,
    request: MoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Move document to a folder or to My Documents."""
    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if request.to_documents:
        doc = await AIDocumentService.move_to_documents(db, doc)
    if request.folder:
        doc = await AIDocumentService.update(db, doc, AIDocumentUpdate(folder=request.folder))
    return await AIDocumentService.to_response(doc)


@router.put("/documents/{doc_id}/rename", response_model=AIDocumentResponse)
async def rename_document(
    doc_id: UUID,
    request: RenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Rename a document."""
    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = await AIDocumentService.rename(db, doc, request.title)
    return await AIDocumentService.to_response(doc)


@router.delete("/documents/batch", response_model=MessageResponse)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:delete")),  # EAI-CUSTOM: Add permission check
):
    """Batch delete documents."""
    count = await AIDocumentService.batch_delete(db, current_user.id, request.ids)
    return MessageResponse(message=f"Deleted {count} documents")


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Read file content for preview."""
    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.doc_type != "file_ref":
        return {"content": doc.content, "doc_type": doc.doc_type}
    content = await AIDocumentService.read_file_content(doc)
    return {"content": content, "doc_type": doc.doc_type, "file_mime": doc.file_mime, "file_size": doc.file_size}


@router.get("/documents/{doc_id}/export")
async def export_document(
    doc_id: UUID,
    format: str = Query("md", description="Export format: md or docx"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Export a document as Markdown (.md) or Word (.docx) file."""
    from urllib.parse import quote

    from fastapi.responses import Response

    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Resolve content: for file_ref docs, read from disk
    content = doc.content
    if doc.doc_type == "file_ref":
        content = await AIDocumentService.read_file_content(doc)
    if not content:
        content = ""

    # Sanitize title for filename — use URL encoding for CJK characters in Content-Disposition
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", doc.title or "document")
    ext = "docx" if format == "docx" else "md"
    encoded_filename = quote(f"{safe_title}.{ext}")

    if format == "docx":
        from io import BytesIO

        from app.extensions.output.generator import generate_docx_simple

        buf = BytesIO()
        generate_docx_simple(content, buf)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )

    # Default: markdown
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.get("/cover-presets")
async def list_cover_presets(current_user: CurrentUser = Depends(require_permission("doc:read"))):  # EAI-CUSTOM: Add permission check
    """List built-in cover page presets (id/label/fields; layout elements omitted)."""
    from app.extensions.output.cover_presets import public_cover_presets

    return {"items": public_cover_presets()}


@router.post("/import-layout")
async def import_layout_docmgr(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Thin pass-through to the shared output layout extractor.

    Fixes the ExportDocxDialog「导入排版」dead button — this route was specified
    in 2026-06-09-docmgr-word-export-layout-design.md but never implemented.
    """
    from app.extensions.output.layout_import import validate_docx_upload

    data = await file.read()
    try:
        return validate_docx_upload(file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExportRequest(BaseModel):
    format: str = "docx"
    layout_template: dict | None = None
    watermark: str | None = None
    with_toc: bool = False
    toc_depth: int = 3
    cover_preset_id: str | None = None
    cover_values: dict | None = None


@router.post("/documents/{doc_id}/export")
async def export_document_with_layout(
    doc_id: UUID,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
    scope: FilterRule = Depends(with_data_scope("docmgr")),  # EAI-CUSTOM (Task L2)
):
    """Export a document as Word (.docx) with layout template and watermark."""
    from urllib.parse import quote

    from fastapi.responses import Response

    doc = await AIDocumentService.get_by_id_scoped(db, doc_id, scope)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc.content
    if doc.doc_type == "file_ref":
        content = await AIDocumentService.read_file_content(doc)
    if not content:
        content = ""

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", doc.title or "document")
    ext = "docx" if request.format == "docx" else "md"
    encoded_filename = quote(f"{safe_title}.{ext}")

    if request.format == "md":
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )

    # DOCX with optional layout template and watermark
    from io import BytesIO

    from app.extensions.output.generator import generate_docx_simple

    buf = BytesIO()
    toc_settings = {"maxDepth": max(1, min(4, request.toc_depth))} if request.with_toc else None
    cover_preset = None
    if request.cover_preset_id:
        from app.extensions.output.cover_presets import get_cover_preset

        cover_preset = get_cover_preset(request.cover_preset_id)
        if cover_preset is None:
            raise HTTPException(status_code=400, detail=f"Unknown cover preset: {request.cover_preset_id}")
    generate_docx_simple(content, buf, template_data=request.layout_template, watermark=request.watermark, toc_settings=toc_settings, cover_preset=cover_preset, cover_values=request.cover_values)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


class ExportContentRequest(BaseModel):
    """Export raw markdown content (no AIDocument row) — used for personal/thread files."""

    content: str = ""
    format: str = "docx"
    layout_template: dict | None = None
    watermark: str | None = None
    filename: str | None = None
    with_toc: bool = False
    toc_depth: int = 3
    cover_preset_id: str | None = None
    cover_values: dict | None = None


@router.post("/export-content")
async def export_content(
    request: ExportContentRequest,
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Export raw markdown content as Word (.docx) with layout template + watermark.

    For personal/thread-synced files whose editor-side id is synthetic
    (``{thread_id}/{rel_path}``, not a UUID) and therefore cannot hit
    ``/documents/{doc_id}/export``.
    """
    from urllib.parse import quote

    from fastapi.responses import Response

    content = request.content or ""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", (request.filename or "document").split("/")[-1])
    ext = "docx" if request.format == "docx" else "md"
    encoded_filename = quote(f"{safe_name}.{ext}")

    if request.format == "md":
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )

    from io import BytesIO

    from app.extensions.output.generator import generate_docx_simple

    buf = BytesIO()
    toc_settings = {"maxDepth": max(1, min(4, request.toc_depth))} if request.with_toc else None
    cover_preset = None
    if request.cover_preset_id:
        from app.extensions.output.cover_presets import get_cover_preset

        cover_preset = get_cover_preset(request.cover_preset_id)
        if cover_preset is None:
            raise HTTPException(status_code=400, detail=f"Unknown cover preset: {request.cover_preset_id}")
    generate_docx_simple(content, buf, template_data=request.layout_template, watermark=request.watermark, toc_settings=toc_settings, cover_preset=cover_preset, cover_values=request.cover_values)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
    # EAI-CUSTOM (F3): 文件夹列表走 scope 引擎（deny 生效，超管 allow_all）
    scope: FilterRule = Depends(with_data_scope("docmgr")),
):
    """List all folders for the current user."""
    folders = await AIDocumentService.list_folders(db, current_user.id, project_scope=project_scope, scope=scope)
    return FolderListResponse(folders=folders)


@router.get("/folders/tree", response_model=FolderTreeResponse)
async def get_folder_tree(
    project_id: UUID | None = Query(None, description="Filter by project ID"),
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    doc_type: str | None = Query(None, description="Filter by doc_type, e.g. 'file_ref'"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """Get folder tree for the current user."""
    folders = await FolderService.get_folder_tree(
        db,
        current_user.id,
        project_id=project_id,
        project_scope=project_scope,
        doc_type=doc_type,
    )
    return FolderTreeResponse(folders=[await FolderService.to_response(f) for f in folders])


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: CreateFolderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Create a new folder or sub-folder."""
    try:
        folder = await FolderService.create_folder(
            db,
            current_user.id,
            data.name,
            parent_id=data.parent_id,
            project_id=data.project_id,
        )
        return await FolderService.to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    folder_id: UUID,
    data: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Rename a folder."""
    try:
        folder = await FolderService.rename_folder(db, folder_id, current_user.id, data.name)
        return await FolderService.to_response(folder)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/folders/{folder_id}/delete-info", response_model=FolderDeleteConfirm)
async def get_folder_delete_info(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """Get deletion preview for a folder."""
    try:
        info = await FolderService.get_delete_info(db, folder_id)
        return FolderDeleteConfirm(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/folders/{folder_id}", response_model=MessageResponse)
async def delete_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:delete")),  # EAI-CUSTOM: Add permission check
):
    """Delete a folder and all its contents."""
    try:
        await FolderService.delete_folder(db, folder_id, current_user.id)
        return MessageResponse(message="Folder deleted successfully")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── AI Operations ────────────────────────────────────────────────────────────


class AIEditRequest(BaseModel):
    """AI edit request schema (inline, mirrors source code)."""

    text: str = Field(..., min_length=1, description="The text to process")
    operation: str = Field(..., description="polish | expand | condense | brainstorm")
    model_name: str | None = Field(None, description="Optional model override")


class AIEditResponse(BaseModel):
    """AI edit response schema."""

    result: str


OPERATION_PROMPTS: dict[str, str] = {
    "polish": ("你是一位专业的文字编辑。请对以下文本进行润色，使其更加流畅、专业，保持原意不变。只输出润色后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"),
    "expand": ("你是一位专业的写作助手。请对以下文本进行扩写，增加更多细节、论据或说明，使内容更加丰富详实。只输出扩写后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"),
    "condense": ("你是一位专业的文字编辑。请对以下文本进行精简，去除冗余内容，保留核心信息，使表达更加简洁有力。只输出精简后的文本，不要添加任何解释或前缀。\n\n文本：\n{text}"),
    "chat": ("你是一位嵌入在文档编辑器中的AI写作助手。请根据用户的指令处理提供的文本，直接输出处理结果。不要添加任何解释或前缀。如果用户要求总结、翻译、改写、分析等，按指令输出。始终使用与用户输入相同的语言回复。\n\n{text}"),
}

# Timeout for AI edit operations (seconds)
AI_EDIT_TIMEOUT_SECONDS = 120


@router.post("/documents/ai-edit/stream")
async def ai_edit_text_stream(
    request: AIEditRequest,
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Stream AI operation result as SSE text/event-stream."""
    prompt_template = OPERATION_PROMPTS.get(request.operation)
    if not prompt_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation: {request.operation}. Must be one of: {list(OPERATION_PROMPTS.keys())}",
        )

    prompt = prompt_template.format(text=request.text)

    from deerflow.models import create_chat_model

    model = create_chat_model(name=request.model_name, thinking_enabled=False)

    async def generate():
        try:
            async with asyncio.timeout(AI_EDIT_TIMEOUT_SECONDS):
                async for chunk in model.astream(prompt):
                    # 不对每个 chunk strip：流式 token 边界常落在空格/换行处，
                    # strip 会吞掉它们导致英文单词粘连（如 "Total plant" → "Totalplant"）
                    text = _extract_ai_response_text(chunk.content)
                    if text:
                        yield f"data: {json.dumps({'token': text})}\n\n"
            yield "data: [DONE]\n\n"
        except TimeoutError:
            logger.warning("AI edit stream timed out: operation=%s", request.operation)
            yield f"data: {json.dumps({'error': 'AI processing timed out, please try a shorter text or select a faster model'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("AI edit stream failed: operation=%s", request.operation)
            yield f"data: {json.dumps({'error': 'AI processing failed, please try again'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _extract_ai_response_text(content: object) -> str:
    """Extract text from AI model response content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else ""
    if content is None:
        return ""
    return str(content)


@router.post("/documents/ai-edit", response_model=AIEditResponse)
async def ai_edit_text(
    request: AIEditRequest,
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Apply AI operation (polish/expand/condense/brainstorm) to a text snippet."""
    prompt_template = OPERATION_PROMPTS.get(request.operation)
    if not prompt_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation: {request.operation}. Must be one of: {list(OPERATION_PROMPTS.keys())}",
        )

    prompt = prompt_template.format(text=request.text)

    try:
        from deerflow.models import create_chat_model

        model = create_chat_model(name=request.model_name, thinking_enabled=False)
        model_name = request.model_name or "default"
        response = await asyncio.wait_for(
            model.ainvoke(prompt),
            timeout=AI_EDIT_TIMEOUT_SECONDS,
        )
        result = _extract_ai_response_text(response.content).strip()
        return AIEditResponse(result=result)
    except TimeoutError:
        logger.warning("AI edit timed out: operation=%s model=%s", request.operation, model_name)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI processing timed out, please try a shorter text or select a faster model",
        )
    except Exception as exc:
        logger.exception("AI edit failed: operation=%s model=%s err=%s", request.operation, model_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI processing failed, please try again",
        )


@router.post("/sync-thread-files")
async def sync_thread_files(
    request: SyncThreadFilesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Sync sandbox files from a thread into document space."""
    from deerflow.config.paths import Paths

    paths = Paths()
    thread_id = request.thread_id

    # Resolve the actual sandbox directory for the thread.
    # The thread may have been created by the Gateway auth (Gateway UUID) while
    # the current user is authenticated via extensions (different UUID).  Scan
    # for the thread under all user directories to bridge this gap.
    user_data_dir = _resolve_thread_sandbox_dir(paths, thread_id, str(current_user.id))

    result = await AIDocumentService.sync_thread_files(
        db=db,
        user_id=current_user.id,
        thread_id=thread_id,
        sandbox_dir=str(user_data_dir),
    )
    return result


# EAI-CUSTOM: 个人文档 BlockNote 编辑器图片上传（uploadFile 后端）。
# 图片落盘线程 user-data/outputs/images/，前端拿 artifacts 相对 URL 渲染。
# 跨桶扫描沿用 sync_thread_files 既有模式（spec §6 已知限制#2），存在性门用于收窄凭空造目录的种文件面。
@router.post("/threads/{thread_id}/images", response_model=ThreadImageResponse)
async def upload_thread_image(
    thread_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Upload an image into the thread's outputs/images/ dir; return an artifacts URL."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="线程不存在")
    ext = _IMAGE_MIME_EXT.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"不支持的图片类型: {file.content_type}")
    data = await file.read(_IMAGE_MAX_BYTES + 1)  # 有界读取：最多读上限+1字节，防任意大 body 全量进内存
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="图片超过 10MB 上限")

    def _resolve_existing_dir():
        d = _resolve_thread_sandbox_dir(Paths(), thread_id, str(current_user.id))
        if not d.exists():  # 仅允许写入已存在线程目录（收窄跨桶种文件面）
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="线程目录不存在")
        return d

    user_data_dir = await asyncio.to_thread(_resolve_existing_dir)
    name = uuid4().hex[:12] + ext
    target = user_data_dir / "outputs" / "images" / name

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    await asyncio.to_thread(_write)
    return ThreadImageResponse(url=f"/api/threads/{thread_id}/artifacts/mnt/user-data/outputs/images/{name}")


# EAI-CUSTOM: 无线程文档（docmgr 直接新建的 AIDocument，source_thread_id 为空）的图片存储。
# 用户级 docmgr-images 目录 + 本路由 GET 服务；无线程沙箱可挂靠，目录归 docmgr 自管，
# 首次上传创建（无需线程端点的存在性门）。name 由服务端生成，GET 只放行 12hex+白名单后缀。
def _user_images_dir(paths, user_id):
    return paths.base_dir / "users" / str(user_id) / "docmgr-images"


@router.post("/images", response_model=ThreadImageResponse)
async def upload_user_image(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Upload an image for a thread-less personal doc into the user's docmgr-images dir."""
    ext = _IMAGE_MIME_EXT.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"不支持的图片类型: {file.content_type}")
    data = await file.read(_IMAGE_MAX_BYTES + 1)
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="图片超过 10MB 上限")
    name = uuid4().hex[:12] + ext
    target = _user_images_dir(Paths(), current_user.id) / name

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    await asyncio.to_thread(_write)
    return ThreadImageResponse(url=f"/api/extensions/docmgr/images/{name}")


_IMAGE_EXT_MIME = {ext: mime for mime, ext in _IMAGE_MIME_EXT.items()}
_USER_IMAGE_NAME = re.compile(r"[0-9a-f]{12}\.(png|jpg|gif|webp|bmp)")


@router.get("/images/{name}")
async def get_user_image(
    name: str,
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """Serve a user-scoped docmgr image inline (server-generated names only)."""
    if not _USER_IMAGE_NAME.fullmatch(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="图片不存在")
    target = _user_images_dir(Paths(), current_user.id) / name

    def _stat() -> bool:
        return target.is_file()

    if not await asyncio.to_thread(_stat):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="图片不存在")
    return FileResponse(target, media_type=_IMAGE_EXT_MIME[target.suffix])


def _resolve_thread_sandbox_dir(paths, thread_id: str, fallback_user_id: str):
    """Find the sandbox user-data directory for *thread_id*.

    Tries the *fallback_user_id* path first.  If that directory is missing or
    contains no files, scans ``{base_dir}/users/`` for any user bucket
    containing this thread.  This bridges the Gateway-vs-extensions UUID split
    where a thread created through the Gateway uses the Gateway user_id for
    its filesystem layout, but the extensions docmgr sync authenticates with
    the extensions user_id.
    """
    primary = paths.sandbox_user_data_dir(thread_id=thread_id, user_id=fallback_user_id)
    if _has_files(primary):
        return primary

    users_dir = paths.base_dir / "users"
    if not users_dir.is_dir():
        return primary

    for user_path in users_dir.iterdir():
        candidate = user_path / "threads" / thread_id / "user-data"
        if _has_files(candidate):
            return candidate

    return primary


def _has_files(directory) -> bool:
    """Quick check whether *directory* contains at least one file (non-recursive)."""
    if not directory.is_dir():
        return False
    for sub in ("workspace", "outputs", "uploads"):
        d = directory / sub
        if d.is_dir():
            try:
                next(d.iterdir())
                return True
            except StopIteration:
                pass
    return False


# ─── Document Sharing ────────────────────────────────────────────────────────


@router.post("/documents/{doc_id}/share", response_model=ShareResponse)
async def share_document(
    doc_id: UUID,
    data: ShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Share a document."""
    try:
        return await ShareService.create_share(db, current_user.id, doc_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/documents/{doc_id}/shares", response_model=list[ShareResponse])
async def list_document_shares(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """List all shares for a document."""
    return await ShareService.list_shares(db, doc_id, current_user.id)


@router.delete("/shares/{share_id}", response_model=MessageResponse)
async def revoke_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:delete")),  # EAI-CUSTOM: Add permission check
):
    """Revoke a share."""
    revoked = await ShareService.revoke_share(db, share_id, current_user.id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Share not found")
    return MessageResponse(message="Share revoked successfully")


@router.get("/shared-with-me")
async def shared_with_me(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """List documents shared with the current user."""
    return await ShareService.list_shared_with_me(db, current_user.id)


@router.get("/shared/{token}")
async def access_shared_document(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """Access a shared document via link token."""
    result = await ShareService.get_shared_document(db, token)
    if not result:
        raise HTTPException(status_code=404, detail="Shared document not found or link invalid")
    return result


# ─── Personal Outputs (Direct Filesystem) ────────────────────────────────────


@router.get("/personal-outputs", response_model=PersonalOutputsResponse)
async def list_personal_outputs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """List personal thread outputs — paginated direct filesystem view of 我的文档."""
    return await AIDocumentService.list_personal_outputs(db, current_user.id, skip, limit)


@router.put("/personal-docs/{thread_id}/star")
async def toggle_personal_star(
    thread_id: str,
    data: PersonalDocStarRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Toggle star on a personal doc."""
    await AIDocumentService.upsert_personal_star(
        db,
        current_user.id,
        thread_id,
        data.rel_path,
        data.starred,
    )
    await db.commit()
    return {"ok": True}


@router.put("/personal-docs/{thread_id}/share")
async def toggle_personal_share(
    thread_id: str,
    data: PersonalDocShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Toggle share on a personal doc."""
    await AIDocumentService.upsert_personal_share(
        db,
        current_user.id,
        thread_id,
        data.rel_path,
        data.shared,
    )
    await db.commit()
    return {"ok": True}


@router.get("/personal-docs/starred")
async def list_starred_personal(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM: Add permission check
):
    """Return all starred personal doc (thread_id, rel_path) pairs."""
    items = await AIDocumentService.list_starred_personal(db, current_user.id)
    return {"items": items}


class PersonalDocContentRequest(BaseModel):
    rel_path: str = Field(..., min_length=1, max_length=500)
    content: str


@router.put("/personal-docs/{thread_id}/content")
async def save_personal_content(
    thread_id: str,
    data: PersonalDocContentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """写回线程 outputs/ 文件（编辑器保存）。"""
    try:
        await AIDocumentService.write_personal_output(
            db,
            current_user.id,
            thread_id,
            data.rel_path,
            data.content,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="outputs directory not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}


# ── EAI-CUSTOM (C10): 个人文档版本历史 ──────────────────────────────────────


@router.post("/personal-docs/{thread_id}/versions")
async def create_personal_version(
    thread_id: str,
    data: PersonalVersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),
):
    """Create a content snapshot for a personal doc (manual save or pre-AI-edit)."""
    vid = await AIDocumentService.create_personal_version(
        db,
        current_user.id,
        thread_id,
        data.rel_path,
        data.content,
        data.label,
    )
    await db.commit()
    return {"ok": True, "id": str(vid)}


@router.get("/personal-docs/{thread_id}/versions", response_model=PersonalVersionListResponse)
async def list_personal_versions(
    thread_id: str,
    rel_path: str = Query(..., min_length=1, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    """List version snapshots for a personal doc, newest first."""
    versions = await AIDocumentService.list_personal_versions(db, current_user.id, thread_id, rel_path)
    return {"versions": versions}


@router.get("/personal-docs/versions/{version_id}", response_model=PersonalVersionDetailResponse)
async def get_personal_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),
):
    """Fetch a single version's full content (preview)."""
    v = await AIDocumentService.get_personal_version(db, current_user.id, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    return v


@router.post("/personal-docs/versions/{version_id}/restore")
async def restore_personal_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),
):
    """Restore a version: write its content back to the outputs file."""
    result = await AIDocumentService.restore_personal_version(db, current_user.id, version_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    await db.commit()
    return {"ok": True, "content": result["content"], "thread_id": result["thread_id"], "rel_path": result["rel_path"]}


# ─── Project Outputs (Cross-User Shared Filesystem) ─────────────────────────
# EAI-CUSTOM: 文档空间「项目区」—— 直接扫各成员线程 outputs/ 目录聚合；
# 项目负责人(lisi)生成的文档自动对组员(zhangsan)可见，可编辑（跨用户写回 + mtime 乐观锁）。


async def _require_project_member(db: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    """跨用户写/版本端点鉴权：校验调用者是项目成员（fail-closed，查库失败即拒）。"""
    members = await AIDocumentService._project_members(db, project_id)
    if str(user_id) not in {str(getattr(m, "user_id", None)) for m in members}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a project member")


async def _require_project_member_thread(db: AsyncSession, project_id: UUID, user_id: UUID, thread_id: str) -> None:
    """带 thread_id 的文件/版本端点鉴权：调用者须为项目成员，且 thread_id 须属于本项目成员的线程。

    防跨项目越权：thread_id 全局唯一，但 service._locate_thread_outputs 会扫所有 user 桶定位，
    故必须在此显式校验 thread_id 是本项目某个成员的线程——否则项目 A 的成员可借任意 thread_id
    读写项目 B 或他人线程的 outputs（fail-closed，查库失败即拒）。EAI-CUSTOM。
    """
    members = await AIDocumentService._project_members(db, project_id)
    if str(user_id) not in {str(getattr(m, "user_id", None)) for m in members}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a project member")
    if thread_id not in {getattr(m, "thread_id", None) for m in members}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="thread does not belong to this project")


@router.get("/projects/{project_id}/outputs", response_model=ProjectOutputsResponse)
async def list_project_outputs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM
):
    """项目区文件系统视图 —— 聚合所有成员线程的 outputs/（服务层校验成员资格）。"""
    try:
        return await AIDocumentService.list_project_outputs(db, project_id, current_user.id)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a project member")


@router.get("/projects/{project_id}/outputs/content")
async def read_project_output(
    project_id: UUID,
    thread_id: str = Query(..., min_length=1, max_length=100),
    rel_path: str = Query(..., min_length=1, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM
):
    """读单个项目文件内容 + mtime（编辑器 seed；artifacts API owner-scoped 故走此端点）。"""
    await _require_project_member_thread(db, project_id, current_user.id, thread_id)
    try:
        return await AIDocumentService.read_project_output(db, project_id, thread_id, rel_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/projects/{project_id}/outputs")
async def save_project_output(
    project_id: UUID,
    data: ProjectDocContentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM
):
    """跨用户写回线程 outputs/ 文件（编辑器保存，带 mtime 乐观锁 + 自动版本快照）。"""
    await _require_project_member_thread(db, project_id, current_user.id, data.thread_id)
    try:
        new_mtime = await AIDocumentService.write_project_output(
            db,
            project_id,
            data.thread_id,
            data.rel_path,
            data.content,
            current_user.id,
            if_mtime=data.if_mtime,
        )
    except _StaleWrite:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="file modified by another editor")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="outputs directory not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return {"ok": True, "mtime": new_mtime}


# ── EAI-CUSTOM: 项目文档版本历史（list / get / restore；写盘自动快照）───────


@router.get("/projects/{project_id}/versions", response_model=ProjectVersionListResponse)
async def list_project_versions(
    project_id: UUID,
    thread_id: str = Query(..., min_length=1, max_length=100),
    rel_path: str = Query(..., min_length=1, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM
):
    """项目文档版本列表（最新优先）。"""
    await _require_project_member_thread(db, project_id, current_user.id, thread_id)
    versions = await AIDocumentService.list_project_versions(db, project_id, thread_id, rel_path)
    return {"versions": versions}


@router.get("/projects/{project_id}/versions/{version_id}", response_model=ProjectVersionDetailResponse)
async def get_project_version(
    project_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:read")),  # EAI-CUSTOM
):
    """取单条版本全文。"""
    await _require_project_member(db, project_id, current_user.id)
    v = await AIDocumentService.get_project_version(db, project_id, version_id)
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    return v


@router.post("/projects/{project_id}/versions/{version_id}/restore")
async def restore_project_version(
    project_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM
):
    """恢复版本：将其内容写回 outputs/ 文件（顺带建一条新快照）。"""
    await _require_project_member(db, project_id, current_user.id)
    result = await AIDocumentService.restore_project_version(db, project_id, version_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    await db.commit()
    return {"ok": True, "content": result["content"], "thread_id": result["thread_id"], "rel_path": result["rel_path"]}
