"""Async database primitives for the sales service."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.log_level.upper() == "DEBUG",
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


async def init_db() -> None:
    # Import models before create_all so metadata is populated.
    from app import models  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # ``create_all`` creates new tables but never alters an existing one.
        # Keep this additive migration explicit so rolling deployments can add
        # parallel-approval audit fields without a heavyweight migration tool.
        await conn.execute(text("ALTER TABLE approval_actions ADD COLUMN IF NOT EXISTS assignment_key VARCHAR(128)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_approval_actions_assignment_key ON approval_actions (assignment_key)"))


async def close_db() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Session factory used by Temporal activities and background jobs."""
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
