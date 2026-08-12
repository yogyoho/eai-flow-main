# EAI-CUSTOM: forked from contract-price-analysis/scripts/db.py(备件 csp_ 表)。
"""Async DB engine + session factory for csp_ tables.

复用共享 ``postgres-ext`` 数据库,但只建 ``csp_*`` 表,备件数据与其它扩展物理隔离。
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from scripts.config import get_config

_engine = create_async_engine(
    get_config().database_url, echo=False, pool_pre_ping=True
)
async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def init_schema() -> None:
    """Create csp_ tables if they do not exist (idempotent)."""
    from scripts.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
