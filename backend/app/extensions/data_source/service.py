"""DataSource service: connection testing, sync, read-only query guard, CRUD.

NOTE on the DB connection: every function that talks to the extensions DB
receives an injected ``AsyncSession`` (router path) or builds a short-lived
engine from ``get_extensions_config().database.url`` (MCP path). NEVER use
PROJECT_DB_URL here — that points at a different database (project-db)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.data_source.schemas import (
    DataSourceCreate,
    DataSourceUpdate,
    TestConnectionResult,
)

from app.extensions.models import DataSource, DataSourceDataset


# Write verbs blocked ANYWHERE in the query. Closes the PostgreSQL
# data-modifying-CTE bypass (WITH d AS (DELETE ...) SELECT ...). Whole-word
# matching (\b) avoids false positives on identifiers like update_time /
# deleted_logs (underscore is a word char, so \bUPDATE\b won't match).
_WRITE_VERBS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL)\b"
)


def assert_readonly_select(sql: str) -> str:
    """Validate that ``sql`` is a single read-only SELECT/WITH query.

    Returns a sanitized SQL string with a guaranteed LIMIT (appended if absent).
    Raises ValueError for anything that is not a single read-only statement.
    Fail-closed: ambiguous input is rejected rather than executed.
    """
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    if not s:
        raise ValueError("SQL 不能为空")
    if ";" in s:
        raise ValueError("禁止多语句查询")
    upper = s.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("仅允许 SELECT / WITH 查询")
    if _WRITE_VERBS.search(upper):
        raise ValueError("禁止写操作关键字")
    # SELECT ... INTO creates a table in Postgres — block it.
    if re.search(r"\bINTO\b", upper):
        raise ValueError("禁止 SELECT INTO 写操作")
    if not re.search(r"\bLIMIT\b", upper):
        s = f"{s} LIMIT 200"
    return s


class DataSourceService:
    """Stateless service methods for DataSource CRUD + connection ops."""

    # ── connection testing ──

    @staticmethod
    async def test_connection(source) -> TestConnectionResult:
        """Dispatch by source.type. Never raises — returns a result object."""
        t = source.type
        cfg = source.connection_config or {}
        try:
            if t == "database":
                return await _test_database(cfg)
            if t == "api":
                return await _test_api(cfg)
            # file / gis / unknown are synchronous
            return DataSourceService.test_connection_sync(source)
        except Exception as e:  # defensive: never let test_connection crash caller
            return TestConnectionResult(success=False, message=f"{type(e).__name__}: {e}")

    @staticmethod
    def test_connection_sync(source) -> TestConnectionResult:
        t = source.type
        cfg = source.connection_config or {}
        if t == "file":
            return _test_file(cfg)
        if t == "gis":
            return _test_gis(cfg)
        return TestConnectionResult(success=False, message=f"不支持的数据源类型: {t}")

    # ── sync (manual MVP) ──

    @staticmethod
    async def sync(source) -> dict:
        """Manual sync: reuse test_connection to probe, update status + timestamp.

        Caller persists last_sync_at/status on the row.
        """
        result = await DataSourceService.test_connection(source)
        return {
            "status": "connected" if result.success else "error",
            # naive UTC — DataSource.last_sync_at is TIMESTAMP WITHOUT TIME ZONE;
            # asyncpg rejects tz-aware datetimes against it (DataError → 500).
            "last_sync_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "metadata": result.metadata or {},
        }

    # ── CRUD ──

    @staticmethod
    async def list(db):
        result = await db.execute(select(DataSource).order_by(DataSource.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db, source_id):
        return await db.get(DataSource, source_id)

    @staticmethod
    async def get_by_name(db, name: str):
        result = await db.execute(select(DataSource).where(DataSource.name == name))
        return result.scalars().first()

    @staticmethod
    async def create(db, req: DataSourceCreate, user_id=None) -> DataSource:
        ds = DataSource(
            name=req.name,
            description=req.description,
            type=req.type,
            connection_config=req.connection_config,
            auth_type=req.auth_type,
            sync_mode=req.sync_mode,
            sync_config=req.sync_config,
            created_by=user_id,
        )
        db.add(ds)
        await db.flush()
        return ds

    @staticmethod
    async def update(db, source_id, req: DataSourceUpdate) -> DataSource | None:
        ds = await db.get(DataSource, source_id)
        if ds is None:
            return None
        data = req.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(ds, k, v)
        await db.flush()
        return ds

    @staticmethod
    async def delete(db, source_id) -> bool:
        ds = await db.get(DataSource, source_id)
        if ds is None:
            return False
        await db.delete(ds)
        await db.flush()
        return True

    # ── datasets (curated business tables) ──

    @staticmethod
    async def list_datasets(db: AsyncSession, source_id) -> list[DataSourceDataset]:
        result = await db.execute(
            select(DataSourceDataset)
            .where(DataSourceDataset.source_id == source_id)
            .order_by(DataSourceDataset.label.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_dataset(db: AsyncSession, dataset_id) -> DataSourceDataset | None:
        return await db.get(DataSourceDataset, dataset_id)

    @staticmethod
    async def create_dataset(db: AsyncSession, source_id, req) -> DataSourceDataset:
        source = await DataSourceService.get_by_id(db, source_id)
        if source is None:
            raise ValueError(f"数据源不存在: {source_id}")
        ds = DataSourceDataset(
            source_id=source_id,
            table_name=req.table_name,
            label=req.label,
            description=req.description,
            key_columns=req.key_columns,
            default_query=req.default_query,
        )
        db.add(ds)
        await db.flush()
        return ds

    @staticmethod
    async def update_dataset(db: AsyncSession, dataset_id, req) -> DataSourceDataset | None:
        ds = await db.get(DataSourceDataset, dataset_id)
        if ds is None:
            return None
        for k, v in req.model_dump(exclude_unset=True).items():
            setattr(ds, k, v)
        await db.flush()
        return ds

    @staticmethod
    async def delete_dataset(db: AsyncSession, dataset_id) -> bool:
        ds = await db.get(DataSourceDataset, dataset_id)
        if ds is None:
            return False
        await db.delete(ds)
        await db.flush()
        return True

    @staticmethod
    async def resolve_dataset(db: AsyncSession, source_id, label: str) -> DataSourceDataset | None:
        """Find a dataset by label within a source (first match; labels need not be unique)."""
        result = await db.execute(
            select(DataSourceDataset).where(
                DataSourceDataset.source_id == source_id,
                DataSourceDataset.label == label,
            )
        )
        return result.scalars().first()

    # ── read-only query / schema against the SOURCE's own DB ──

    @staticmethod
    async def run_readonly_query(source, sql: str) -> list[dict]:
        """Execute an already-guarded read-only SQL against the source's OWN
        database (built from source.connection_config) — NOT the extensions DB.
        Caller must pass sql through assert_readonly_select first."""
        engine = create_async_engine(_build_db_url(source.connection_config or {}), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                try:
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                except Exception:
                    pass
                res = await conn.execute(text(sql))
                return [dict(row) for row in res.mappings().all()]
        finally:
            await engine.dispose()

    @staticmethod
    async def list_tables(source) -> list[str]:
        """List public tables in the source's OWN database."""
        engine = create_async_engine(_build_db_url(source.connection_config or {}), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                res = await conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' LIMIT 50")
                )
                return [r[0] for r in res.fetchall()]
        finally:
            await engine.dispose()

    @staticmethod
    async def profile_tables(source) -> list[dict]:
        """Profile public tables in the source's OWN database: name + columns.

        One information_schema.columns query (cheap). Up to 50 tables. Columns
        are enough for the agent to map a business need to the right table.
        """
        engine = create_async_engine(_build_db_url(source.connection_config or {}), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                res = await conn.execute(
                    text(
                        "SELECT table_name, column_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_schema='public' "
                        "ORDER BY table_name, ordinal_position"
                    )
                )
                rows = res.fetchall()
        finally:
            await engine.dispose()
        tables: dict[str, list[dict]] = {}
        order: list[str] = []
        for table_name, column_name, data_type in rows:
            if table_name not in tables:
                tables[table_name] = []
                order.append(table_name)
            tables[table_name].append({"name": column_name, "type": data_type})
        return [{"name": t, "columns": tables[t]} for t in order[:50]]


def _build_db_url(cfg: dict) -> str:
    """Build a SQLAlchemy URL from a database source's connection_config."""
    driver = cfg.get("driver") or "postgresql+asyncpg"
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    database = cfg.get("database", "")
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    return f"{driver}://{username}:{password}@{host}:{port}/{database}"


async def _test_database(cfg: dict) -> TestConnectionResult:
    engine = create_async_engine(_build_db_url(cfg), poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
    return TestConnectionResult(
        success=True, message="连接成功", metadata={"engine": cfg.get("driver") or "postgresql+asyncpg"}
    )


async def _test_api(cfg: dict) -> TestConnectionResult:
    url = cfg.get("url", "")
    if not url:
        return TestConnectionResult(success=False, message="缺少 url")
    headers = cfg.get("headers") or {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if 200 <= resp.status_code < 300:
        return TestConnectionResult(
            success=True, message=f"HTTP {resp.status_code}", metadata={"status_code": resp.status_code}
        )
    return TestConnectionResult(
        success=False, message=f"HTTP {resp.status_code}", metadata={"status_code": resp.status_code}
    )


def _test_file(cfg: dict) -> TestConnectionResult:
    path = cfg.get("path", "")
    if path and Path(path).exists():
        return TestConnectionResult(success=True, message="文件存在", metadata={"path": path})
    return TestConnectionResult(success=False, message="文件不存在", metadata={"path": path})


def _test_gis(cfg: dict) -> TestConnectionResult:
    name = cfg.get("file_name", "")
    if name:
        return TestConnectionResult(
            success=True, message="已配置 GIS 文件", metadata={"file_name": name, "file_size": cfg.get("file_size")}
        )
    return TestConnectionResult(success=False, message="未上传 GIS 文件")
