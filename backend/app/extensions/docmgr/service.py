"""AI Document service for extensions module."""

import json
import logging
import mimetypes
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import AIDocument, ProjectMember
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
        folder_id: UUID | None = None,
        starred: bool | None = None,
        shared: bool | None = None,
        doc_type: str | None = None,
        project_scope: str | None = None,
        project_id: UUID | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 12,
    ) -> tuple[list[AIDocument], int]:
        """List documents with filters.

        Shows user's own documents plus documents from projects the user is a member of.
        project_scope: "personal" = no project, "project" = has project, None = both.
        project_id: filter to a specific project (takes precedence over project_scope).
        """
        # Base visibility: own docs OR docs from user's projects
        own_docs = AIDocument.user_id == user_id
        my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        project_docs = AIDocument.project_id.in_(my_project_ids)
        visibility_filter = or_(own_docs, project_docs)

        query = select(AIDocument).where(visibility_filter)
        count_query = select(func.count(AIDocument.id)).where(visibility_filter)

        if folder is not None:
            query = query.where(AIDocument.folder == folder)
            count_query = count_query.where(AIDocument.folder == folder)

        if folder_id is not None:
            query = query.where(AIDocument.folder_id == folder_id)
            count_query = count_query.where(AIDocument.folder_id == folder_id)

        if starred is not None:
            query = query.where(AIDocument.is_starred == starred)
            count_query = count_query.where(AIDocument.is_starred == starred)

        if shared is not None:
            query = query.where(AIDocument.is_shared == shared)
            count_query = count_query.where(AIDocument.is_shared == shared)

        if doc_type is not None:
            query = query.where(AIDocument.doc_type == doc_type)
            count_query = count_query.where(AIDocument.doc_type == doc_type)

        if project_scope == "personal":
            query = query.where(AIDocument.project_id.is_(None))
            count_query = count_query.where(AIDocument.project_id.is_(None))
        elif project_scope == "project":
            query = query.where(AIDocument.project_id.isnot(None))
            count_query = count_query.where(AIDocument.project_id.isnot(None))

        if project_id is not None:
            query = query.where(AIDocument.project_id == project_id)
            count_query = count_query.where(AIDocument.project_id == project_id)

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
        """Get document by ID — accessible by owner or project member."""
        own_docs = AIDocument.user_id == user_id
        my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        project_docs = AIDocument.project_id.in_(my_project_ids)
        stmt = select(AIDocument).where(AIDocument.id == doc_id, or_(own_docs, project_docs))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, data: AIDocumentCreate) -> AIDocument:
        """Create a new document."""
        # Auto-detect project_id from thread if not explicitly provided
        project_id = data.project_id
        if not project_id and data.source_thread_id:
            project_id = await AIDocumentService._detect_project_from_thread(db, data.source_thread_id)

        document = AIDocument(
            user_id=user_id,
            title=data.title,
            content=data.content,
            folder=data.folder,
            source_thread_id=data.source_thread_id,
            project_id=project_id,
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
    async def list_folders(db: AsyncSession, user_id: UUID, project_scope: str | None = None) -> list[str]:
        """List all folders for a user (own + project docs)."""
        own_docs = AIDocument.user_id == user_id
        my_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        project_docs = AIDocument.project_id.in_(my_project_ids)
        visibility_filter = or_(own_docs, project_docs)

        stmt = select(AIDocument.folder).where(visibility_filter)

        if project_scope == "personal":
            stmt = stmt.where(AIDocument.project_id.is_(None))
        elif project_scope == "project":
            stmt = stmt.where(AIDocument.project_id.isnot(None))

        stmt = stmt.distinct()
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
            project_id=doc.project_id,
            title=doc.title,
            content=doc.content,
            folder=doc.folder,
            folder_id=doc.folder_id,
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
    async def move_to_documents(db: AsyncSession, doc: AIDocument) -> AIDocument:
        """Move a file_ref document to '我的文档' by reading file content into DB."""
        if doc.doc_type != "file_ref":
            return doc
        if doc.file_ref_path and os.path.exists(doc.file_ref_path):
            text_mimes = {"text/markdown", "text/plain", "text/html", "text/x-rst"}
            if doc.file_mime in text_mimes:
                with open(doc.file_ref_path, "r", encoding="utf-8", errors="replace") as f:
                    doc.content = f.read()
            else:
                doc.content = json.dumps({"type": "binary_ref", "file_ref_path": doc.file_ref_path, "file_mime": doc.file_mime})
        else:
            doc.content = json.dumps({"type": "file_missing", "file_ref_path": doc.file_ref_path})

        doc.doc_type = "document"
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def batch_delete(db: AsyncSession, user_id: UUID, doc_ids: list[UUID]) -> int:
        """Delete multiple documents. Returns count deleted."""
        if not doc_ids:
            return 0
        if len(doc_ids) > 50:
            raise ValueError("Batch delete limited to 50 documents")
        stmt = select(AIDocument).where(
            AIDocument.user_id == user_id,
            AIDocument.id.in_(doc_ids),
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()
        count = 0
        for doc in docs:
            await db.delete(doc)
            count += 1
        await db.commit()
        return count

    @staticmethod
    async def rename(db: AsyncSession, doc: AIDocument, new_title: str) -> AIDocument:
        """Rename a document. For file_ref, also rename physical file."""
        if doc.doc_type == "file_ref" and doc.file_ref_path:
            old_path = Path(doc.file_ref_path)
            if old_path.exists():
                new_path = old_path.parent / new_title
                old_path.rename(new_path)
                doc.file_ref_path = str(new_path)
        doc.title = new_title
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def read_file_content(doc: AIDocument) -> str | None:
        """Read file content for preview. Returns None for missing files."""
        if not doc.file_ref_path or not os.path.exists(doc.file_ref_path):
            return None
        file_size = os.path.getsize(doc.file_ref_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            return None
        with open(doc.file_ref_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    @staticmethod
    async def _get_thread_title(db: AsyncSession, thread_id: str) -> str:
        """Get thread display name.

        The ``threads_meta`` table lives in the Gateway SQLite database, not
        the extensions PostgreSQL database that *db* is connected to.  Querying
        it through *db* would abort the PostgreSQL transaction.  Read from the
        Gateway's SQLite file directly instead.
        """
        try:
            import json
            import sqlite3

            from deerflow.config.paths import Paths

            paths = Paths()
            db_path = paths.base_dir / "data" / "deerflow.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                try:
                    row = conn.execute(
                        "SELECT display_name FROM threads_meta WHERE thread_id = ?",
                        (thread_id,),
                    ).fetchone()
                    if row and row[0]:
                        return row[0]
                finally:
                    conn.close()
        except Exception:
            pass

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
        project_id = await AIDocumentService._detect_project_from_thread(db, thread_id)
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
                project_id=project_id,
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

    @staticmethod
    async def _detect_project_from_thread(db: AsyncSession, thread_id: str) -> UUID | None:
        """Detect project_id from a thread_id by checking project_members."""
        stmt = select(ProjectMember.project_id).where(ProjectMember.thread_id == thread_id).limit(1)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        return row
