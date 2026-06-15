"""Async DB engine + session factory for cpa_ tables.

Reuses the shared ``postgres-ext`` database (same as knowledge-factory and the
project extension module) but creates only the ``cpa_*`` tables, keeping the
contract-price data physically isolated from procurement-service tables.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from scripts.config import get_config

_engine = create_async_engine(
    get_config().database_url, echo=False, pool_pre_ping=True
)
async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def init_schema() -> None:
    """Create cpa_ tables if they do not exist (idempotent)."""
    from scripts.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
