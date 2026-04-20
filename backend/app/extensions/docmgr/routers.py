"""AI Document routers for extensions module."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.docmgr.service import AIDocumentService
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentListResponse,
    AIDocumentResponse,
    AIDocumentUpdate,
    CurrentUser,
    FolderListResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["AI Documents"])


@router.get("/documents", response_model=AIDocumentListResponse)
async def list_documents(
    folder: str | None = Query(None, description="Filter by folder name"),
    starred: bool | None = Query(None, description="Filter by starred status"),
    shared: bool | None = Query(None, description="Filter by shared status"),
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
        starred=starred,
        shared=shared,
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


@router.get("/folders", response_model=FolderListResponse)
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all folders for the current user."""
    folders = await AIDocumentService.list_folders(db, current_user.id)
    return FolderListResponse(folders=folders)
