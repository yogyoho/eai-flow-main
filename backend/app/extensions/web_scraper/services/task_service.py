"""Task history persistence service for web scraper."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select

from app.extensions.database import AsyncSession
from app.extensions.models import ScrapTaskRecord
from app.extensions.web_scraper.schemas import (
    TaskDetailResponse,
    TaskHistoryItem,
    TaskListResponse,
)

logger = logging.getLogger(__name__)


class ScrapTaskService:
    """Scrape task persistence service."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        user_id: UUID,
        task_id: str,
        url: str,
        prompt: str | None = None,
        provider: str = "firecrawl",
        schema_name: str | None = None,
        llm_model: str | None = None,
        proxy_enabled: bool = False,
        auth_enabled: bool = False,
    ) -> ScrapTaskRecord:
        """Persist a new task record."""
        record = ScrapTaskRecord(
            user_id=user_id,
            task_id=task_id,
            url=url,
            prompt=prompt,
            provider=provider,
            schema_name=schema_name,
            llm_model=llm_model,
            proxy_enabled=proxy_enabled,
            auth_enabled=auth_enabled,
            status="pending",
            logs=[],
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Created task record: task_id={task_id}, user={user_id}")
        return record

    @staticmethod
    async def update_task(db: AsyncSession, task_id: str, **kwargs) -> ScrapTaskRecord | None:
        """Update task fields by task_id string."""
        query = select(ScrapTaskRecord).where(ScrapTaskRecord.task_id == task_id)
        result = await db.execute(query)
        record = result.scalar_one_or_none()
        if not record:
            return None

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)

        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        user_id: UUID,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScrapTaskRecord], int]:
        """Paginated task list with optional status filter."""
        conditions = [ScrapTaskRecord.user_id == user_id]
        if status_filter:
            conditions.append(ScrapTaskRecord.status == status_filter)

        count_query = select(func.count(ScrapTaskRecord.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        query = (
            select(ScrapTaskRecord)
            .where(and_(*conditions))
            .order_by(ScrapTaskRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(query)
        records = result.scalars().all()
        return list(records), total

    @staticmethod
    async def get_task(db: AsyncSession, task_id: str, user_id: UUID) -> ScrapTaskRecord | None:
        """Get single task by task_id string, scoped to user."""
        query = select(ScrapTaskRecord).where(
            and_(ScrapTaskRecord.task_id == task_id, ScrapTaskRecord.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_task_by_task_id(db: AsyncSession, task_id: str) -> ScrapTaskRecord | None:
        """Get task by short task_id string (no user scoping)."""
        query = select(ScrapTaskRecord).where(ScrapTaskRecord.task_id == task_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def to_history_item(record: ScrapTaskRecord) -> TaskHistoryItem:
        """Convert to list item."""
        return TaskHistoryItem(
            task_id=record.task_id,
            url=record.url,
            provider=record.provider,
            schema_name=record.schema_name,
            status=record.status,
            error=record.error,
            provider_used=record.provider_used,
            created_at=record.created_at.isoformat() if record.created_at else "",
            started_at=record.started_at.isoformat() if record.started_at else None,
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
        )

    @staticmethod
    def to_detail_response(record: ScrapTaskRecord) -> TaskDetailResponse:
        """Convert to detail response."""
        import json

        structured_data = None
        if record.structured_data:
            if isinstance(record.structured_data, dict):
                structured_data = record.structured_data
            elif isinstance(record.structured_data, str):
                try:
                    structured_data = json.loads(record.structured_data)
                except (json.JSONDecodeError, TypeError):
                    structured_data = None

        logs = record.logs or []
        if isinstance(logs, str):
            try:
                logs = json.loads(logs)
            except (json.JSONDecodeError, TypeError):
                logs = []

        return TaskDetailResponse(
            **ScrapTaskService.to_history_item(record).model_dump(),
            prompt=record.prompt,
            result=record.result,
            structured_data=structured_data,
            logs=logs,
            draft_id=str(record.draft_id) if record.draft_id else None,
        )

    @staticmethod
    def to_list_response(records: list[ScrapTaskRecord], total: int, page: int, page_size: int) -> TaskListResponse:
        """Convert to paginated list response."""
        return TaskListResponse(
            tasks=[ScrapTaskService.to_history_item(r) for r in records],
            total=total,
            page=page,
            page_size=page_size,
        )
