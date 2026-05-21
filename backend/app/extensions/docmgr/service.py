"""AI Document service for extensions module."""

import logging
import mimetypes
from pathlib import Path
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
            doc_type=data.doc_type,
            file_ref_path=data.file_ref_path,
            file_size=data.file_size,
            file_mime=data.file_mime,
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
        if data.doc_type is not None:
            doc.doc_type = data.doc_type
        if data.file_ref_path is not None:
            doc.file_ref_path = data.file_ref_path
        if data.file_size is not None:
            doc.file_size = data.file_size
        if data.file_mime is not None:
            doc.file_mime = data.file_mime

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
            doc_type=doc.doc_type,
            file_ref_path=doc.file_ref_path,
            file_size=doc.file_size,
            file_mime=doc.file_mime,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    @staticmethod
    async def to_detail_response(doc: AIDocument) -> AIDocumentResponse:
        """Convert document model to detailed response (includes content)."""
        return await AIDocumentService.to_response(doc)

    @staticmethod
    async def _get_thread_title(db: AsyncSession, thread_id: str) -> str:
        """Get thread display name from threads_meta table."""
        from deerflow.persistence.thread_meta.model import ThreadMetaRow

        try:
            stmt = select(ThreadMetaRow.display_name).where(ThreadMetaRow.thread_id == thread_id)
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            return row or thread_id[:8]
        except Exception:
            return thread_id[:8]

    @staticmethod
    async def sync_thread_files(
        db: AsyncSession,
        user_id: UUID,
        thread_id: str,
        sandbox_dir: str,
    ) -> dict:
        """Sync sandbox files for a thread into document space as file_ref records."""
        folder_name = await AIDocumentService._get_thread_title(db, thread_id)
        synced = 0
        skipped = 0
        max_per_sync = 100

        sandbox_path = Path(sandbox_dir)
        if not sandbox_path.exists():
            return {"synced": 0, "skipped": 0}

        for filepath in sandbox_path.rglob("*"):
            if not filepath.is_file():
                continue
            if synced >= max_per_sync:
                break

            abs_path = str(filepath)
            file_size = filepath.stat().st_size
            mime_type, _ = mimetypes.guess_type(filepath.name)
            if mime_type is None:
                mime_type = "application/octet-stream"

            # Check for existing file_ref with same path and thread
            existing = await db.execute(
                select(AIDocument).where(
                    AIDocument.user_id == user_id,
                    AIDocument.file_ref_path == abs_path,
                    AIDocument.source_thread_id == thread_id,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            doc = AIDocument(
                user_id=user_id,
                title=filepath.name,
                folder=folder_name,
                source_thread_id=thread_id,
                doc_type="file_ref",
                file_ref_path=abs_path,
                file_size=file_size,
                file_mime=mime_type,
                status="active",
            )
            db.add(doc)
            synced += 1

        await db.commit()
        return {"synced": synced, "skipped": skipped}
