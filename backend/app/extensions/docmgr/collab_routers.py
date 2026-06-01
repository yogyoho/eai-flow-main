"""Routers for collaborative editing: comments and versions."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.docmgr.collab_schemas import (
    AIReviewRequest,
    AIReviewResponse,
    CommentCreateRequest,
    CommentResponse,
    CommentUpdateRequest,
    VersionCreateRequest,
    VersionDiffResponse,
    VersionResponse,
    VersionRestoreResponse,
)
from app.extensions.docmgr.collab_service import AIReviewService, CommentService, VersionService
from app.extensions.docmgr.service import AIDocumentService
from app.extensions.schemas import CurrentUser, MessageResponse

router = APIRouter(prefix="/api/extensions/docmgr", tags=["Collaboration"])


# ─── Comments ──────────────────────────────────────────────────────────────


@router.get("/documents/{doc_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return await CommentService.list_comments(db, doc_id)


@router.post("/documents/{doc_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    doc_id: UUID,
    data: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return await CommentService.create_comment(
        db, current_user.id, doc_id, data.block_id, data.content, data.parent_id
    )


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: UUID,
    data: CommentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = await CommentService.update_comment(db, comment_id, current_user.id, data.content)
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found or not owned")
    return result


@router.delete("/comments/{comment_id}", response_model=MessageResponse)
async def delete_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = await CommentService.delete_comment(db, comment_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found or not owned")
    return MessageResponse(message="Comment deleted")


@router.post("/comments/{comment_id}/resolve", response_model=CommentResponse)
async def resolve_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = await CommentService.resolve_comment(db, comment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found")
    return result


@router.post("/comments/{comment_id}/reopen", response_model=CommentResponse)
async def reopen_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = await CommentService.reopen_comment(db, comment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found")
    return result


# ─── Versions ──────────────────────────────────────────────────────────────


@router.get("/documents/{doc_id}/versions", response_model=list[VersionResponse])
async def list_versions(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return await VersionService.list_versions(db, doc_id)


@router.post("/documents/{doc_id}/versions", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    doc_id: UUID,
    data: VersionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    from app.extensions.docmgr.collab_models import CollabDocument, CollabVersion

    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    collab_doc = await db.get(CollabDocument, doc_id)
    snapshot = bytes(collab_doc.yjs_doc) if collab_doc else b""
    if not snapshot and doc.content:
        snapshot = doc.content.encode("utf-8")

    result = await VersionService.create_version(
        db, doc_id, current_user.id, snapshot, summary=data.summary
    )

    if data.generate_summary and not data.summary:
        ai_summary = await VersionService.generate_ai_summary(db, doc_id, result["version"])
        if ai_summary:
            version_obj = await db.get(CollabVersion, result["id"])
            if version_obj:
                version_obj.summary = ai_summary
                await db.commit()
                result["summary"] = ai_summary

    return result


@router.get("/documents/{doc_id}/versions/diff", response_model=VersionDiffResponse)
async def diff_versions(
    doc_id: UUID,
    from_version: int = Query(..., alias="from", description="Source version number"),
    to_version: int = Query(..., alias="to", description="Target version number"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await VersionService.diff_versions(db, doc_id, from_version, to_version)
    if not result:
        raise HTTPException(status_code=404, detail="One or both versions not found")
    return result


@router.get("/documents/{doc_id}/versions/{version}", response_model=VersionResponse)
async def get_version(
    doc_id: UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await VersionService.get_version(db, doc_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    result.pop("snapshot", None)
    return result


@router.post("/documents/{doc_id}/versions/{version}/restore", response_model=VersionRestoreResponse)
async def restore_version(
    doc_id: UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    from app.extensions.docmgr.collab_models import CollabDocument

    doc = await AIDocumentService.get_by_id(db, doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = await VersionService.get_snapshot(db, doc_id, version)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Version not found")

    collab_doc = await db.get(CollabDocument, doc_id)
    if collab_doc:
        collab_doc.yjs_doc = snapshot
        collab_doc.version += 1
        collab_doc.last_editor_id = current_user.id
        await db.commit()
    else:
        collab_doc = CollabDocument(
            doc_id=doc_id, yjs_doc=snapshot, version=1, last_editor_id=current_user.id
        )
        db.add(collab_doc)
        await db.commit()

    await VersionService.create_version(
        db, doc_id, current_user.id, snapshot, summary=f"Restored to version {version}"
    )

    return VersionRestoreResponse(version=version, message=f"Restored to version {version}")


# ─── AI Document-Level Review ────────────────────────────────────────────


@router.post("/documents/ai-review", response_model=AIReviewResponse)
async def ai_review_document(
    request: AIReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    doc = await AIDocumentService.get_by_id(db, request.doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    content = request.content or doc.content or ""
    if not content and doc.file_ref_path:
        from pathlib import Path

        ref = doc.file_ref_path
        path = Path(ref)
        if not path.is_file() and ref.startswith("/app/"):
            local_ref = ref.replace("/app/", str(Path(__file__).resolve().parents[3]) + "/")
            path = Path(local_ref)
        if path.is_file() and path.stat().st_size <= 10 * 1024 * 1024:
            content = path.read_text(encoding="utf-8", errors="replace")

    return await AIReviewService.ai_review_document(db, request.doc_id, content, request.review_type)
