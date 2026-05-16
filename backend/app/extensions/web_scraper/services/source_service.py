"""Data source management service for web scraper."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select

from app.extensions.database import AsyncSession
from app.extensions.models import ScrapSource
from app.extensions.web_scraper.schemas import (
    ScrapSourceDetailResponse,
    ScrapSourceListResponse,
    ScrapSourceResponse,
)

logger = logging.getLogger(__name__)


class ScrapSourceService:
    """Data source CRUD service."""

    @staticmethod
    async def create_source(
        db: AsyncSession,
        user_id: UUID,
        data: "ScrapSourceCreate",
    ) -> ScrapSource:
        """Create a new data source."""
        source = ScrapSource(
            user_id=user_id,
            name=data.name,
            description=data.description,
            url_pattern=data.url_pattern,
            category=data.category,
            default_schema=data.default_schema,
            default_provider=data.default_provider,
            auth_config=data.auth_config,
            proxy_config=data.proxy_config,
            cron_expression=data.cron_expression,
            is_enabled=data.is_enabled,
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        logger.info(f"Created data source: {source.id}, name={source.name}")
        return source

    @staticmethod
    async def list_sources(
        db: AsyncSession,
        user_id: UUID,
        category: str | None = None,
        enabled_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScrapSource], int]:
        """Paginated source list with optional filters."""
        conditions = [ScrapSource.user_id == user_id]
        if category:
            conditions.append(ScrapSource.category == category)
        if enabled_only:
            conditions.append(ScrapSource.is_enabled == True)  # noqa: E712

        count_query = select(func.count(ScrapSource.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        query = (
            select(ScrapSource)
            .where(and_(*conditions))
            .order_by(ScrapSource.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        sources = result.scalars().all()
        return list(sources), total

    @staticmethod
    async def get_source(db: AsyncSession, source_id: UUID, user_id: UUID) -> ScrapSource | None:
        """Get single source, scoped to user."""
        query = select(ScrapSource).where(and_(ScrapSource.id == source_id, ScrapSource.user_id == user_id))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_source(db: AsyncSession, source: ScrapSource, data: "ScrapSourceUpdate") -> ScrapSource:
        """Update source fields."""
        if data.name is not None:
            source.name = data.name
        if data.description is not None:
            source.description = data.description
        if data.url_pattern is not None:
            source.url_pattern = data.url_pattern
        if data.category is not None:
            source.category = data.category
        if data.default_schema is not None:
            source.default_schema = data.default_schema
        if data.default_provider is not None:
            source.default_provider = data.default_provider
        if data.auth_config is not None:
            source.auth_config = data.auth_config
        if data.proxy_config is not None:
            source.proxy_config = data.proxy_config
        if data.cron_expression is not None:
            source.cron_expression = data.cron_expression
        if data.is_enabled is not None:
            source.is_enabled = data.is_enabled

        source.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(source)
        logger.info(f"Updated data source: {source.id}")
        return source

    @staticmethod
    async def delete_source(db: AsyncSession, source: ScrapSource) -> None:
        """Delete a data source."""
        await db.delete(source)
        await db.commit()
        logger.info(f"Deleted data source: {source.id}")

    @staticmethod
    def to_response(source: ScrapSource) -> ScrapSourceResponse:
        """Convert to response model."""
        return ScrapSourceResponse(
            id=source.id,
            name=source.name,
            url_pattern=source.url_pattern,
            category=source.category,
            default_schema=source.default_schema,
            default_provider=source.default_provider,
            is_enabled=source.is_enabled,
            last_scraped_at=source.last_scraped_at.isoformat() if source.last_scraped_at else None,
            created_at=source.created_at.isoformat() if source.created_at else "",
            updated_at=source.updated_at.isoformat() if source.updated_at else "",
        )

    @staticmethod
    def to_detail_response(source: ScrapSource) -> ScrapSourceDetailResponse:
        """Convert to detail response model."""
        return ScrapSourceDetailResponse(
            **ScrapSourceService.to_response(source).model_dump(),
            description=source.description,
            auth_config=source.auth_config,
            proxy_config=source.proxy_config,
            cron_expression=source.cron_expression,
        )

    @staticmethod
    def to_list_response(sources: list[ScrapSource], total: int, page: int, page_size: int) -> ScrapSourceListResponse:
        """Convert to paginated list response."""
        return ScrapSourceListResponse(
            sources=[ScrapSourceService.to_response(s) for s in sources],
            total=total,
            page=page,
            page_size=page_size,
        )
