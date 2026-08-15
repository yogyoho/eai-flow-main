"""postgres_ext connector — direct read-only SELECTs against the extensions DB.

Mirrors contract_price/mcp.py::_run_in_db (short-lived engine) + fail-closed
read-only (SET TRANSACTION READ ONLY). Column/table names come from the
versioned registry (trusted), values are bound params — no injection surface.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text


async def _resolve_db_url() -> str:
    if os.environ.get("ONTOLOGY_DB_URL"):
        return os.environ["ONTOLOGY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_ext_db(func):
    """Run func(session) against the extensions DB with a short-lived read-only engine.

    Shared by execute_select, run_raw_select, and the data_source connector
    (source-row resolution) — one engine-per-call, disposed after.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            return await func(session)
    finally:
        await engine.dispose()


def read_only_select(
    table: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> tuple[str, dict[str, Any]]:
    """Build a read-only SELECT statement (no execution)."""
    cols = ", ".join(f'"{c}"' for c in columns)
    sql = f"SELECT {cols} FROM {table}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if order_by:
        sql += f' ORDER BY "{order_by}"'
    if limit:
        sql += f" LIMIT {limit}"
    return sql, params or {}


async def execute_select(
    table: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Execute a read-only SELECT against the extensions DB and return dict rows."""
    sql, bind = read_only_select(table, columns, where_sql, params, order_by, limit)

    async def _q(session):
        result = await session.execute(text(sql).bindparams(**bind))
        return [dict(r) for r in result.mappings().all()]

    return await _run_in_ext_db(_q)


async def run_raw_select(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute an already-validated read-only SELECT (used by aggregate)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(sql).bindparams(**(params or {})))
            return [dict(r) for r in result.mappings().all()]
    finally:
        await engine.dispose()
