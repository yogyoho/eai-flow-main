"""AI Document routers for extensions module."""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.docmgr.folder_service import FolderService
from app.extensions.docmgr.service import AIDocumentService
from app.extensions.docmgr.share_schemas import ShareCreateRequest, ShareResponse
from app.extensions.docmgr.share_service import ShareService
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentListResponse,
    AIDocumentResponse,
    AIDocumentUpdate,
    CurrentUser,
    FolderCreate,
    FolderDeleteConfirm,
    FolderListResponse,
    FolderResponse,
    FolderSortUpdate,
    FolderTreeResponse,
    FolderUpdate,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["AI Documents"])


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
    current_user: CurrentUser = Depends(get_current_user),
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
    )
    return AIDocumentListResponse(
        documents=[await AIDocumentService.to_response(doc) for doc in documents],
        total=total,
    )


@router.get("/documents/{doc_id}", response_model=AIDocumentResponse)
async def get_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific document by ID."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return await AIDocumentService.to_detail_response(document)


@router.post("/documents", response_model=AIDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: AIDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new document."""
    document = await AIDocumentService.create(db, current_user.id, data)
    return await AIDocumentService.to_response(document)


@router.put("/documents/{doc_id}", response_model=AIDocumentResponse)
async def update_document(
    doc_id: UUID,
    data: AIDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a document."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
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
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a document."""
    document = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not document:
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
    current_user: CurrentUser = Depends(get_current_user),
):
    """Move document to a folder or to My Documents."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
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
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename a document."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = await AIDocumentService.rename(db, doc, request.title)
    return await AIDocumentService.to_response(doc)


@router.delete("/documents/batch", response_model=MessageResponse)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Batch delete documents."""
    count = await AIDocumentService.batch_delete(db, current_user.id, request.ids)
    return MessageResponse(message=f"Deleted {count} documents")


@router.get("/documents/{doc_id}/preview")
async def preview_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Read file content for preview."""
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.doc_type != "file_ref":
        return {"content": doc.content, "doc_type": doc.doc_type}
    content = await AIDocumentService.read_file_content(doc)
    return {"content": content, "doc_type": doc.doc_type, "file_mime": doc.file_mime, "file_size": doc.file_size}


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all folders for the current user."""
    folders = await AIDocumentService.list_folders(db, current_user.id, project_scope=project_scope)
    return FolderListResponse(folders=folders)


@router.get("/folders/tree", response_model=FolderTreeResponse)
async def get_folder_tree(
    project_id: UUID | None = Query(None, description="Filter by project ID"),
    project_scope: str | None = Query(None, description="Filter: personal or project"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get folder tree for the current user."""
    folders = await FolderService.get_folder_tree(
        db, current_user.id, project_id=project_id, project_scope=project_scope,
    )
    return FolderTreeResponse(
        folders=[await FolderService.to_response(f) for f in folders]
    )


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: CreateFolderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new folder or sub-folder."""
    try:
        folder = await FolderService.create_folder(
            db, current_user.id, data.name, parent_id=data.parent_id, project_id=data.project_id,
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
    current_user: CurrentUser = Depends(get_current_user),
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
    current_user: CurrentUser = Depends(get_current_user),
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
    current_user: CurrentUser = Depends(get_current_user),
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
    "brainstorm": ("你是一位创意写作助手。请基于以下文本进行头脑风暴，提供3-5个相关的扩展思路或角度，每条思路用「- 」开头。只输出思路列表，不要添加任何解释或前缀。\n\n文本：\n{text}"),
}

# Timeout for AI edit operations (seconds)
AI_EDIT_TIMEOUT_SECONDS = 120


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
    current_user: CurrentUser = Depends(get_current_user),
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
    current_user: CurrentUser = Depends(get_current_user),
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
    current_user: CurrentUser = Depends(get_current_user),
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
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all shares for a document."""
    return await ShareService.list_shares(db, doc_id, current_user.id)


@router.delete("/shares/{share_id}", response_model=MessageResponse)
async def revoke_share(
    share_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke a share."""
    revoked = await ShareService.revoke_share(db, share_id, current_user.id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Share not found")
    return MessageResponse(message="Share revoked successfully")


@router.get("/shared-with-me")
async def shared_with_me(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List documents shared with the current user."""
    return await ShareService.list_shared_with_me(db, current_user.id)


@router.get("/shared/{token}")
async def access_shared_document(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Access a shared document via link token."""
    result = await ShareService.get_shared_document(db, token)
    if not result:
        raise HTTPException(status_code=404, detail="Shared document not found or link invalid")
    return result
