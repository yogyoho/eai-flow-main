"""数据库连接与 Session 管理"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


engine = None
async_session_maker = None


def _get_engine():
    global engine
    if engine is None:
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            echo=settings.log_level == "DEBUG",
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return engine


def _get_session_maker():
    global async_session_maker
    if async_session_maker is None:
        async_session_maker = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return async_session_maker


async def init_db() -> None:
    """Create all tables."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine."""
    global engine, async_session_maker
    if engine:
        await engine.dispose()
        engine = None
        async_session_maker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a database session."""
    session_maker = _get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
