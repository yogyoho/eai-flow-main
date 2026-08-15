"""data_source connector — read-only SELECTs against external DBs registered in data_sources.

Reuses DataSourceService (app.extensions.data_source.service) for source-row
resolution and its fail-closed assert_readonly_select guard. ontology ONLY uses
data_source as the physical SQL read path (mother spec §11.2 boundary).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.extensions.ontology.connectors.postgres_ext import _run_in_ext_db
from app.extensions.ontology.connectors.postgres_ext import read_only_select as _pg_read_only_select


def read_only_select(
    table_name: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> tuple[str, dict[str, Any]]:
    """Build a read-only SELECT for an external DB (same builder as postgres_ext, no ``*``)."""
    if any(c == "*" for c in columns):
        raise ValueError("select * not allowed — declare columns in registry")
    return _pg_read_only_select(table_name, columns, where_sql, params, order_by, limit)


async def _resolve_source(source_id: str):
    """Fetch the data_sources row via the extensions-DB engine."""
    from app.extensions.data_source.service import DataSourceService

    async def _q(session):
        src = await DataSourceService.get_by_name(session, source_id)
        if src is None:
            raise ValueError(f"data_source not found: {source_id}")
        return src

    return await _run_in_ext_db(_q)


async def _run_external(cfg: dict, sql: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Execute a guarded SQL against the external DB named by ``cfg`` (read-only txn)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.data_source.service import _build_db_url

    engine = create_async_engine(_build_db_url(cfg or {}), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text(sql).bindparams(**(params or {})))
            return [dict(r) for r in result.mappings().all()]
    finally:
        await engine.dispose()


async def execute_select(
    source_id: str,
    table_name: str,
    columns: list[str],
    where_sql: str = "",
    params: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    from app.extensions.data_source.service import assert_readonly_select

    sql, bind = read_only_select(table_name, columns, where_sql, params, order_by, limit)
    safe_sql = assert_readonly_select(sql)  # fail-closed: SELECT/WITH only, auto LIMIT 200
    src = await _resolve_source(source_id)
    return await _run_external(src.connection_config, safe_sql, bind)


async def run_raw_select(source_id: str, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from app.extensions.data_source.service import assert_readonly_select

    safe_sql = assert_readonly_select(sql)  # aggregate SQL 同样过守卫
    src = await _resolve_source(source_id)
    return await _run_external(src.connection_config, safe_sql, params)
