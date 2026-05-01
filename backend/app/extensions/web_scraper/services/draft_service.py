"""Draft service for web scraper."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, func, select

from app.extensions.config import get_extensions_config
from app.extensions.database import AsyncSession
from app.extensions.knowledge.service import DocumentService, KnowledgeBaseService
from app.extensions.models import ScrapDraft
from app.extensions.web_scraper.schemas import ScrapDraftDetailResponse, ScrapDraftResponse

logger = logging.getLogger(__name__)


class ScrapDraftService:
    """Scrape draft service."""

    @staticmethod
    async def create_draft(
        db: AsyncSession,
        user_id: UUID,
        data: "ScrapDraftCreate",
    ) -> ScrapDraft:
        """Create a new draft."""

        draft = ScrapDraft(
            user_id=user_id,
            source_url=data.source_url,
            source_title=data.source_title,
            schema_name=data.schema_name,
            schema_display_name=data.schema_display_name,
            raw_content=data.raw_content,
            structured_data=data.structured_data,
            title=data.title,
            tags=data.tags or [],
            category=data.category,
        )

        db.add(draft)
        await db.commit()
        await db.refresh(draft)

        logger.info(f"Created scrape draft: {draft.id}, user: {user_id}")
        return draft

    @staticmethod
    async def list_drafts(
        db: AsyncSession,
        user_id: UUID,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScrapDraft], int]:
        """Get draft list."""
        conditions = [ScrapDraft.user_id == user_id]
        if status_filter:
            conditions.append(ScrapDraft.status == status_filter)

        count_query = select(func.count(ScrapDraft.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        query = select(ScrapDraft).where(and_(*conditions)).order_by(ScrapDraft.updated_at.desc()).offset(offset).limit(page_size)
        result = await db.execute(query)
        drafts = result.scalars().all()

        return list(drafts), total

    @staticmethod
    async def get_draft(
        db: AsyncSession,
        draft_id: UUID,
        user_id: UUID,
    ) -> ScrapDraft | None:
        """Get draft detail."""
        query = select(ScrapDraft).where(and_(ScrapDraft.id == draft_id, ScrapDraft.user_id == user_id))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_draft(
        db: AsyncSession,
        draft: ScrapDraft,
        data: "ScrapDraftUpdate",
    ) -> ScrapDraft:
        """Update draft."""

        if data.title is not None:
            draft.title = data.title
        if data.raw_content is not None:
            draft.raw_content = data.raw_content
        if data.structured_data is not None:
            draft.structured_data = data.structured_data
        if data.tags is not None:
            draft.tags = data.tags
        if data.category is not None:
            draft.category = data.category

        draft.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(draft)

        logger.info(f"Updated draft: {draft.id}")
        return draft

    @staticmethod
    async def delete_draft(
        db: AsyncSession,
        draft: ScrapDraft,
    ) -> None:
        """Soft delete draft."""
        draft.status = "deleted"
        draft.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Deleted draft: {draft.id}")

    @staticmethod
    async def import_to_knowledge_base(
        db: AsyncSession,
        draft: ScrapDraft,
        kb_id: UUID,
        chunk_method: str = "naive",
        auto_parse: bool = True,
    ) -> dict:
        """Import draft to knowledge base."""
        kb = await KnowledgeBaseService.get_kb_by_id(db, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")

        if kb.owner_id != draft.user_id and kb.access_type != "public":
            raise PermissionError("No permission to access this knowledge base")

        config = get_extensions_config()
        storage_path = Path(config.storage.base_path) / str(draft.user_id) / "drafts"
        storage_path.mkdir(parents=True, exist_ok=True)

        file_name = f"{draft.title[:100]}_{draft.id}.md"
        file_path = storage_path / file_name

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(draft.raw_content or "")

        doc = await DocumentService.create_doc(
            db=db,
            kb=kb,
            file_name=file_name,
            file_path=str(file_path),
            file_size=len((draft.raw_content or "").encode("utf-8")),
            auto_parse=auto_parse,
            content_type="text/markdown",
        )

        draft.status = "imported"
        draft.knowledge_base_id = kb_id
        draft.document_id = str(doc.id)
        draft.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(f"Draft imported to KB: draft={draft.id}, kb={kb_id}, doc={doc.id}")

        return {
            "success": True,
            "draft_id": draft.id,
            "document_id": str(doc.id),
            "knowledge_base_id": kb_id,
            "message": f"Successfully imported to knowledge base: {kb.name}",
        }

    @staticmethod
    def to_response(draft: ScrapDraft) -> ScrapDraftResponse:
        """Convert to response model."""
        return ScrapDraftResponse(
            id=draft.id,
            source_url=draft.source_url,
            source_title=draft.source_title,
            schema_name=draft.schema_name,
            schema_display_name=draft.schema_display_name,
            title=draft.title,
            tags=draft.tags or [],
            category=draft.category,
            status=draft.status,
            source_provider=draft.source_provider,
            scrape_date=draft.scrape_date.isoformat() if draft.scrape_date else "",
            knowledge_base_id=draft.knowledge_base_id,
            created_at=draft.created_at.isoformat() if draft.created_at else "",
            updated_at=draft.updated_at.isoformat() if draft.updated_at else "",
        )

    @staticmethod
    def to_detail_response(draft: ScrapDraft) -> ScrapDraftDetailResponse:
        """Convert to detail response model."""
        return ScrapDraftDetailResponse(
            **ScrapDraftService.to_response(draft).model_dump(),
            raw_content=draft.raw_content or "",
            structured_data=draft.structured_data,
            document_id=draft.document_id,
        )
