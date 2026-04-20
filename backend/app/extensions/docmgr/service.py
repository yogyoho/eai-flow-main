"""AI Document service for extensions module."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import AIDocument
from app.extensions.schemas import (
    AIDocumentCreate,
    AIDocumentResponse,
    AIDocumentUpdate,
)

logger = logging.getLogger(__name__)


class AIDocumentService:
    """AI Document service."""

    @staticmethod
    async def list_docs(
        db: AsyncSession,
        user_id: UUID,
        folder: str | None = None,
        starred: bool | None = None,
        shared: bool | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 12,
    ) -> tuple[list[AIDocument], int]:
        """List documents with filters."""
        query = select(AIDocument).where(AIDocument.user_id == user_id)
        count_query = select(func.count(AIDocument.id)).where(AIDocument.user_id == user_id)

        if folder is not None:
            query = query.where(AIDocument.folder == folder)
            count_query = count_query.where(AIDocument.folder == folder)

        if starred is not None:
            query = query.where(AIDocument.is_starred == starred)
            count_query = count_query.where(AIDocument.is_starred == starred)

        if shared is not None:
            query = query.where(AIDocument.is_shared == shared)
            count_query = count_query.where(AIDocument.is_shared == shared)

        if q is not None:
            search_filter = AIDocument.title.ilike(f"%{q}%")
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        query = query.offset(skip).limit(limit).order_by(AIDocument.updated_at.desc())

        result = await db.execute(query)
        documents = result.scalars().all()

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        return list(documents), total

    @staticmethod
    async def get_by_id(db: AsyncSession, doc_id: UUID, user_id: UUID) -> AIDocument | None:
        """Get document by ID with user check."""
        stmt = select(AIDocument).where(AIDocument.id == doc_id, AIDocument.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, data: AIDocumentCreate) -> AIDocument:
        """Create a new document."""
        document = AIDocument(
            user_id=user_id,
            title=data.title,
            content=data.content,
            folder=data.folder,
            source_thread_id=data.source_thread_id,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def update(db: AsyncSession, doc: AIDocument, data: AIDocumentUpdate) -> AIDocument:
        """Update an existing document."""
        if data.title is not None:
            doc.title = data.title
        if data.content is not None:
            doc.content = data.content
        if data.folder is not None:
            doc.folder = data.folder
        if data.is_starred is not None:
            doc.is_starred = data.is_starred
        if data.is_shared is not None:
            doc.is_shared = data.is_shared
        if data.status is not None:
            doc.status = data.status

        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def delete(db: AsyncSession, doc: AIDocument) -> None:
        """Delete a document."""
        await db.delete(doc)
        await db.commit()

    @staticmethod
    async def list_folders(db: AsyncSession, user_id: UUID) -> list[str]:
        """List all folders for a user."""
        stmt = select(AIDocument.folder).where(AIDocument.user_id == user_id).distinct()
        result = await db.execute(stmt)
        folders = [row[0] for row in result.all()]
        return folders

    @staticmethod
    async def to_response(doc: AIDocument) -> AIDocumentResponse:
        """Convert document model to response."""
        return AIDocumentResponse(
            id=doc.id,
            user_id=doc.user_id,
            source_thread_id=doc.source_thread_id,
            title=doc.title,
            content=doc.content,
            folder=doc.folder,
            is_starred=doc.is_starred,
            is_shared=doc.is_shared,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    @staticmethod
    async def to_detail_response(doc: AIDocument) -> AIDocumentResponse:
        """Convert document model to detailed response (includes content)."""
        return await AIDocumentService.to_response(doc)
