"""Services for collaborative editing: comments and versions."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.docmgr.collab_models import CollabComment, CollabVersion
from app.extensions.models import User

logger = logging.getLogger(__name__)


class CommentService:
    @staticmethod
    async def list_comments(db: AsyncSession, doc_id: UUID) -> list[dict]:
        stmt = (
            select(CollabComment, User.username, User.full_name)
            .join(User, CollabComment.user_id == User.id, isouter=True)
            .where(CollabComment.doc_id == doc_id)
            .order_by(CollabComment.created_at)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "block_id": c.block_id,
                "content": c.content,
                "parent_id": c.parent_id,
                "user_id": c.user_id,
                "resolved": c.resolved,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "username": username,
                "full_name": full_name,
            }
            for c, username, full_name in rows
        ]

    @staticmethod
    async def create_comment(
        db: AsyncSession, user_id: UUID, doc_id: UUID, block_id: str, content: str, parent_id: UUID | None = None
    ) -> dict:
        comment = CollabComment(
            doc_id=doc_id,
            block_id=block_id,
            content=content,
            parent_id=parent_id,
            user_id=user_id,
        )
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def update_comment(db: AsyncSession, comment_id: UUID, user_id: UUID, content: str) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment or comment.user_id != user_id:
            return None
        comment.content = content
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def delete_comment(db: AsyncSession, comment_id: UUID, user_id: UUID) -> bool:
        comment = await db.get(CollabComment, comment_id)
        if not comment or comment.user_id != user_id:
            return False
        await db.delete(comment)
        await db.commit()
        return True

    @staticmethod
    async def resolve_comment(db: AsyncSession, comment_id: UUID) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment:
            return None
        comment.resolved = True
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, comment.user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def reopen_comment(db: AsyncSession, comment_id: UUID) -> dict | None:
        comment = await db.get(CollabComment, comment_id)
        if not comment:
            return None
        comment.resolved = False
        await db.commit()
        await db.refresh(comment)
        user = await db.get(User, comment.user_id)
        return {
            "id": comment.id,
            "doc_id": comment.doc_id,
            "block_id": comment.block_id,
            "content": comment.content,
            "parent_id": comment.parent_id,
            "user_id": comment.user_id,
            "resolved": comment.resolved,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }


class VersionService:
    @staticmethod
    async def list_versions(db: AsyncSession, doc_id: UUID) -> list[dict]:
        stmt = (
            select(CollabVersion, User.username, User.full_name)
            .join(User, CollabVersion.created_by == User.id, isouter=True)
            .where(CollabVersion.doc_id == doc_id)
            .order_by(CollabVersion.version.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "id": v.id,
                "doc_id": v.doc_id,
                "version": v.version,
                "summary": v.summary,
                "created_by": v.created_by,
                "created_at": v.created_at,
                "username": username,
                "full_name": full_name,
            }
            for v, username, full_name in rows
        ]

    @staticmethod
    async def create_version(
        db: AsyncSession, doc_id: UUID, user_id: UUID, snapshot: bytes, summary: str | None = None
    ) -> dict:
        stmt = select(func.coalesce(func.max(CollabVersion.version), 0) + 1).where(CollabVersion.doc_id == doc_id)
        result = await db.execute(stmt)
        next_version = result.scalar()

        version = CollabVersion(
            doc_id=doc_id,
            version=next_version,
            snapshot=snapshot,
            summary=summary,
            created_by=user_id,
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)
        user = await db.get(User, user_id)
        return {
            "id": version.id,
            "doc_id": version.doc_id,
            "version": version.version,
            "summary": version.summary,
            "created_by": version.created_by,
            "created_at": version.created_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def get_version(db: AsyncSession, doc_id: UUID, version: int) -> dict | None:
        stmt = select(CollabVersion).where(
            CollabVersion.doc_id == doc_id, CollabVersion.version == version
        )
        result = await db.execute(stmt)
        v = result.scalar_one_or_none()
        if not v:
            return None
        user = await db.get(User, v.created_by) if v.created_by else None
        return {
            "id": v.id,
            "doc_id": v.doc_id,
            "version": v.version,
            "snapshot": v.snapshot,
            "summary": v.summary,
            "created_by": v.created_by,
            "created_at": v.created_at,
            "username": user.username if user else None,
            "full_name": user.full_name if user else None,
        }

    @staticmethod
    async def get_snapshot(db: AsyncSession, doc_id: UUID, version: int) -> bytes | None:
        stmt = select(CollabVersion.snapshot).where(
            CollabVersion.doc_id == doc_id, CollabVersion.version == version
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
