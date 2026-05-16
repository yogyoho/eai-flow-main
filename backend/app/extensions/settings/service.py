"""System config persistence service."""

import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import SystemConfigEntry

logger = logging.getLogger(__name__)


class SystemConfigService:

    @staticmethod
    async def get_all(db: AsyncSession) -> dict[str, str]:
        stmt = select(SystemConfigEntry)
        result = await db.execute(stmt)
        return {row.key: row.value for row in result.scalars().all()}

    @staticmethod
    async def upsert(db: AsyncSession, key: str, value: str) -> None:
        stmt = (
            pg_insert(SystemConfigEntry)
            .values(key=key, value=value, updated_at=func.now())
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value, "updated_at": func.now()},
            )
        )
        await db.execute(stmt)

    @staticmethod
    async def upsert_many(db: AsyncSession, data: dict[str, str]) -> None:
        for key, value in data.items():
            if value is not None:
                await SystemConfigService.upsert(db, key, str(value))
