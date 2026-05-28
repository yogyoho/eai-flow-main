"""项目文档路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Project, ProjectDocument
from app.schemas import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)

router = APIRouter(prefix="/documents", tags=["项目文档"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    project_id: UUID | None = Query(None),
    doc_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(ProjectDocument)
    count_stmt = select(func.count(ProjectDocument.id))

    if project_id:
        stmt = stmt.where(ProjectDocument.project_id == project_id)
        count_stmt = count_stmt.where(ProjectDocument.project_id == project_id)
    if doc_type:
        stmt = stmt.where(ProjectDocument.doc_type == doc_type)
        count_stmt = count_stmt.where(ProjectDocument.doc_type == doc_type)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(ProjectDocument.created_at.desc()))
    docs = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return DocumentListResponse(documents=[DocumentResponse.model_validate(d) for d in docs], total=total)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    doc = ProjectDocument(**data.model_dump(), uploaded_by=current_user.username)
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: UUID,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(doc, key, value)
    await db.flush()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.delete(doc)
