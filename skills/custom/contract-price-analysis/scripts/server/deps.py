"""Shared dependencies for the management API.

``get_session`` yields an async DB session. It is the single seam routers depend
on, so tests override it via ``app.dependency_overrides[get_session] = ...``
without needing a live ``postgres-ext``.
"""

from collections.abc import AsyncGenerator

from scripts.db import async_session


async def get_session() -> AsyncGenerator:
    async with async_session() as session:
        yield session
