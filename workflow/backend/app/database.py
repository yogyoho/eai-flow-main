"""Async database engine, session factory and bootstrap helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all workflow tables."""


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine():
    url = settings.database_url
    kwargs: dict = {"echo": settings.sql_echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # A NullPool keeps each operation on a fresh connection. The demo and
        # the test suite use several event loops (TestClient, dispatcher tests),
        # and a pooled aiosqlite connection is bound to the loop that opened it.
        kwargs.pop("pool_pre_ping", None)
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update({"pool_size": 10, "max_overflow": 20, "pool_recycle": 900})
    return create_async_engine(url, **kwargs)


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = _create_engine()
        _session_factory = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency."""

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def redacted_database_url() -> str:
    """Database URL safe for logs (password removed)."""

    url = settings.database_url
    if "@" not in url or "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    credentials, _, host = rest.rpartition("@")
    if ":" in credentials:
        user, _, _ = credentials.partition(":")
        credentials = f"{user}:***"
    return f"{scheme}://{credentials}@{host}"


async def database_health() -> dict[str, object]:
    """Cheap liveness probe used by ``/health``.

    The timeout is intentionally short: a stuck database must not make the
    orchestrator's health check hang longer than its own probe deadline.
    """

    try:

        async def _probe() -> None:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_probe(), timeout=settings.db_health_timeout_seconds)
        return {"connected": True}
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return {"connected": False, "error": type(exc).__name__}


async def init_db(seed: bool | None = None) -> None:
    """Prepare the schema and optionally seed demo data.

    ``alembic upgrade head`` is the production path. The automatic ``create_all``
    remains available for zero-setup SQLite demos and the test suite.
    """

    from . import models  # noqa: F401  (register metadata)

    if settings.auto_create_schema:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    should_seed = settings.seed_demo if seed is None else seed
    if should_seed:
        from .seed import seed_demo_data

        async with session_scope() as session:
            await seed_demo_data(session)


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
