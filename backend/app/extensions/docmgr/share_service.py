"""Document share service."""

import secrets
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.docmgr.share_models import DocumentShare
from app.extensions.docmgr.share_schemas import ShareCreateRequest, ShareResponse
from app.extensions.models import AIDocument

logger = logging.getLogger(__name__)


class ShareService:
    @staticmethod
    async def create_share(db: AsyncSession, user_id: UUID, document_id: UUID, data: ShareCreateRequest) -> ShareResponse:
        """Create a new share record."""
        # Verify ownership
        doc_stmt = select(AIDocument).where(AIDocument.id == document_id, AIDocument.user_id == user_id)
        doc_result = await db.execute(doc_stmt)
        if not doc_result.scalar_one_or_none():
            raise ValueError("Document not found or not owned by user")

        token = None
        if data.share_type == "link":
            token = secrets.token_urlsafe(32)

        share = DocumentShare(
            document_id=document_id,
            share_type=data.share_type,
            share_target_id=data.share_target_id,
            share_token=token,
            permission=data.permission,
            created_by=user_id,
        )
        db.add(share)

        # Mark document as shared
        doc_result2 = await db.execute(select(AIDocument).where(AIDocument.id == document_id))
        doc_obj = doc_result2.scalar_one_or_none()
        if doc_obj:
            doc_obj.is_shared = True

        await db.commit()
        await db.refresh(share)
        return ShareResponse.model_validate(share)

    @staticmethod
    async def list_shares(db: AsyncSession, document_id: UUID, user_id: UUID) -> list[ShareResponse]:
        """List all shares for a document."""
        stmt = select(DocumentShare).where(DocumentShare.document_id == document_id, DocumentShare.created_by == user_id)
        result = await db.execute(stmt)
        shares = result.scalars().all()
        return [ShareResponse.model_validate(s) for s in shares]

    @staticmethod
    async def revoke_share(db: AsyncSession, share_id: UUID, user_id: UUID) -> bool:
        """Revoke a share."""
        stmt = select(DocumentShare).where(DocumentShare.id == share_id, DocumentShare.created_by == user_id)
        result = await db.execute(stmt)
        share = result.scalar_one_or_none()
        if not share:
            return False
        await db.delete(share)
        await db.commit()
        return True

    @staticmethod
    async def get_shared_document(db: AsyncSession, token: str) -> dict | None:
        """Get a shared document by link token."""
        stmt = select(DocumentShare).where(DocumentShare.share_token == token, DocumentShare.share_type == "link")
        result = await db.execute(stmt)
        share = result.scalar_one_or_none()
        if not share:
            return None

        doc_stmt = select(AIDocument).where(AIDocument.id == share.document_id)
        doc_result = await db.execute(doc_stmt)
        doc = doc_result.scalar_one_or_none()
        if not doc:
            return None

        return {
            "document": {
                "id": str(doc.id),
                "title": doc.title,
                "content": doc.content,
                "doc_type": doc.doc_type,
            },
            "permission": share.permission,
            "shared_by": str(share.created_by),
        }

    @staticmethod
    async def list_shared_with_me(db: AsyncSession, user_id: UUID) -> list[dict]:
        """List documents shared with the current user (direct user share)."""
        stmt = (
            select(DocumentShare, AIDocument)
            .join(AIDocument, DocumentShare.document_id == AIDocument.id)
            .where(DocumentShare.share_target_id == str(user_id))
            .order_by(DocumentShare.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "document": {
                    "id": str(doc.id),
                    "title": doc.title,
                    "content": doc.content,
                    "doc_type": doc.doc_type,
                    "folder": doc.folder,
                    "updated_at": doc.updated_at.isoformat(),
                },
                "permission": share.permission,
                "share_type": share.share_type,
                "shared_by": str(share.created_by),
            }
            for share, doc in rows
        ]
