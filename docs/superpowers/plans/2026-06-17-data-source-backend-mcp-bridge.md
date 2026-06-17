# 数据源后端 + MCP 桥 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「基本设置 → 数据源」tab 从前端空壳变成后端可用 + AI Agent 可经 MCP 真实取数(只读)的模块。

**Architecture:** 新增 `DataSource` 模型(落 extensions DB,自动建表);重写 `data_source/routers.py` 提供完整 CRUD + test/sync;新增 `data_source/service.py` 承载连接测试/同步/只读 SQL 守卫逻辑;新增 `data_source/mcp.py` 作为 stdio MCP server 暴露 4 个工具给 Agent,经 `get_extensions_config().database.url` 连同一 extensions 库;在 `extensions_config.json` 注册 MCP server。

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) + asyncpg · httpx · Pydantic v2 · MCP SDK(`mcp.server`)· pytest(异步)。

**关键约束(必须遵守):**
- MCP / 任何后端代码连库一律用 `get_extensions_config().database.url`(extensions DB)。**绝不**使用 `PROJECT_DB_URL`(那是独立的 `project-db` 库,与 DataSource 表无关)。
- `query_data_source` 的 database 分支必须经 `assert_readonly_select()` 守卫:仅 SELECT/WITH、禁多语句、禁 `INTO`、自动 `LIMIT 200`。
- 连接配置(connection_config)明文存 JSONB(本次不做加密)。
- 同步只做手动模式。
- 全程 TDD:每个任务先写失败测试 → 实现 → 通过 → 提交。

**运行测试:** 所有命令在 `backend/` 下执行,`PYTHONPATH=. uv run pytest <path> -v`。

---

## 文件结构

新增:
- `backend/app/extensions/data_source/schemas.py` — Pydantic 请求/响应模型
- `backend/app/extensions/data_source/service.py` — `DataSourceService`:连接测试 / 同步 / 只读守卫 / CRUD 数据访问 + `assert_readonly_select`
- `backend/app/extensions/data_source/mcp.py` — stdio MCP server(4 工具)
- `backend/tests/test_data_source_models.py`
- `backend/tests/test_data_source_service.py`
- `backend/tests/test_data_source_routers.py`
- `backend/tests/test_data_source_mcp.py`

修改:
- `backend/app/extensions/models/__init__.py` — 追加 `DataSource` 模型类
- `backend/app/extensions/data_source/routers.py` — 桩 → 完整实现
- `extensions_config.json` — `mcpServers` 增加 `data_sources`

---

## Task 1: DataSource 数据模型

**Files:**
- Modify: `backend/app/extensions/models/__init__.py`(文件末尾追加)
- Test: `backend/tests/test_data_source_models.py`

`models/__init__.py` 顶部已导入所需列类型(`String, DateTime, func, ForeignKey, UUID, JSONB` 等),无需新增 import。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_data_source_models.py`:

```python
"""Tests for the DataSource model."""

import pytest

from app.extensions.models import DataSource


class TestDataSourceModel:
    def test_defaults(self):
        ds = DataSource(
            name="生产数据库",
            type="database",
            connection_config={"host": "db", "port": "5432"},
        )
        assert ds.name == "生产数据库"
        assert ds.type == "database"
        assert ds.auth_type == "none"
        assert ds.sync_mode == "manual"
        assert ds.status == "disconnected"
        assert ds.last_sync_at is None
        assert ds.sync_config is None

    def test_connection_config_accepts_arbitrary_json(self):
        ds = DataSource(name="api1", type="api", connection_config={"url": "https://x"})
        assert ds.connection_config["url"] == "https://x"

    def test_tablename(self):
        assert DataSource.__tablename__ == "data_sources"

    def test_type_field_is_plain_string(self):
        ds = DataSource(name="f", type="gis", connection_config={})
        assert ds.type == "gis"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'DataSource' from 'app.extensions.models'`

- [ ] **Step 3: 追加模型实现**

在 `backend/app/extensions/models/__init__.py` 文件**最末尾**追加:

```python


class DataSource(Base):
    """External data source connection (database / api / file / gis).

    connection_config is stored as plaintext JSONB (encryption is a P1 follow-up).
    Fields align 1:1 with frontend src/extensions/data-source/types.ts.
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # database|api|file|gis
    connection_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    auth_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    sync_mode: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    sync_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="disconnected", nullable=False
    )  # connected|error|disconnected|testing
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, name={self.name}, type={self.type})>"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_data_source_models.py
git commit -m "feat(data-source): add DataSource model in extensions registry"
```

---

## Task 2: Pydantic schemas

**Files:**
- Create: `backend/app/extensions/data_source/schemas.py`
- Test: `backend/tests/test_data_source_service.py`(本任务只覆盖 schema 部分,后续任务往同一文件追加)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_data_source_service.py`:

```python
"""Tests for data_source schemas + service logic."""

import pytest
from pydantic import ValidationError

from app.extensions.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    TestConnectionResult,
)


class TestSchemas:
    def test_create_minimal(self):
        ds = DataSourceCreate(
            name="prod",
            type="database",
            connection_config={"host": "h", "port": "5432"},
        )
        assert ds.auth_type == "none"
        assert ds.sync_mode == "manual"
        assert ds.sync_config is None

    def test_create_requires_name(self):
        with pytest.raises(ValidationError):
            DataSourceCreate(name="", type="api", connection_config={})

    def test_test_connection_result_defaults(self):
        r = TestConnectionResult(success=True, message="ok")
        assert r.metadata is None

    def test_response_from_attributes(self):
        # Simulate an ORM-like object via a simple namespace
        class _Fake:
            id = "abc"
            name = "n"
            type = "api"
            connection_config = {}
            auth_type = "none"
            sync_mode = "manual"
            sync_config = None
            status = "disconnected"
            last_sync_at = None
            created_by = None
            created_at = None
            updated_at = None

        resp = DataSourceResponse.model_validate(_Fake())
        assert resp.name == "n"
        assert resp.id == "abc"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestSchemas -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.data_source.schemas'`

- [ ] **Step 3: 实现 schemas**

创建 `backend/app/extensions/data_source/schemas.py`:

```python
"""Pydantic schemas for the data_source extension. Field names align with
frontend src/extensions/data-source/types.ts (snake_case in DB, the frontend
api.ts already maps snake_case <-> camelCase)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., description="database | api | file | gis")
    connection_config: dict = Field(default_factory=dict)
    auth_type: str = "none"
    sync_mode: str = "manual"
    sync_config: dict | None = None


class DataSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    type: str | None = None
    connection_config: dict | None = None
    auth_type: str | None = None
    sync_mode: str | None = None
    sync_config: dict | None = None
    status: str | None = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    type: str
    connection_config: dict
    auth_type: str
    sync_mode: str
    sync_config: dict | None = None
    status: str
    last_sync_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataSourceListResponse(BaseModel):
    items: list[DataSourceResponse]


class TestConnectionResult(BaseModel):
    success: bool
    message: str
    metadata: dict | None = None


class SyncResponse(BaseModel):
    id: UUID | str
    status: str
    last_sync_at: datetime
    metadata: dict = Field(default_factory=dict)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestSchemas -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/schemas.py backend/tests/test_data_source_service.py
git commit -m "feat(data-source): add pydantic schemas"
```

---

## Task 3: 只读 SQL 守卫 `assert_readonly_select`

安全关键逻辑,单独先做并用密集测试覆盖。

**Files:**
- Modify: `backend/app/extensions/data_source/service.py`(本任务创建该文件,只放守卫)
- Test: `backend/tests/test_data_source_service.py`(追加 TestAssertReadonlySelect)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_data_source_service.py` **末尾**追加:

```python
import pytest

from app.extensions.data_source.service import assert_readonly_select


class TestAssertReadonlySelect:
    def test_select_appends_limit(self):
        out = assert_readonly_select("SELECT * FROM users")
        assert out.endswith("LIMIT 200")

    def test_with_cte_allowed(self):
        out = assert_readonly_select("WITH x AS (SELECT 1) SELECT * FROM x")
        assert out.startswith("WITH")

    def test_existing_limit_kept(self):
        out = assert_readonly_select("SELECT * FROM users LIMIT 5")
        assert "LIMIT 5" in out
        # must not double-append
        assert out.count("LIMIT") == 1

    def test_lowercase_select_allowed(self):
        out = assert_readonly_select("select * from t")
        assert "LIMIT 200" in out

    def test_insert_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("INSERT INTO t VALUES (1)")

    def test_update_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("UPDATE t SET a=1")

    def test_delete_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("DELETE FROM t")

    def test_drop_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("DROP TABLE t")

    def test_multi_statement_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("SELECT 1; DROP TABLE t;")

    def test_select_into_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("SELECT * INTO newt FROM t")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_select("   ")

    def test_trailing_semicolon_stripped(self):
        out = assert_readonly_select("SELECT 1;")
        assert ";" not in out
        assert "LIMIT 200" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestAssertReadonlySelect -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.data_source.service'`

- [ ] **Step 3: 实现守卫**

创建 `backend/app/extensions/data_source/service.py`:

```python
"""DataSource service: connection testing, sync, read-only query guard, CRUD.

NOTE on the DB connection: every function that talks to the extensions DB
receives an injected ``AsyncSession`` (router path) or builds a short-lived
engine from ``get_extensions_config().database.url`` (MCP path). NEVER use
PROJECT_DB_URL here — that points at a different database (project-db)."""

from __future__ import annotations

import re


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
    # SELECT ... INTO creates a table in Postgres — block it.
    if re.search(r"\bINTO\b", upper):
        raise ValueError("禁止 SELECT INTO 写操作")
    if not re.search(r"\bLIMIT\b", upper):
        s = f"{s} LIMIT 200"
    return s
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestAssertReadonlySelect -v`
Expected: 12 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/service.py backend/tests/test_data_source_service.py
git commit -m "feat(data-source): add read-only SELECT guard (security-critical)"
```

---

## Task 4: 连接测试 `test_connection`(按 type 分发)

**Files:**
- Modify: `backend/app/extensions/data_source/service.py`(追加)
- Test: `backend/tests/test_data_source_service.py`(追加 TestTestConnection)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_data_source_service.py` 末尾追加:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.extensions.data_source.service import DataSourceService


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_database_success(self):
        # mock create_async_engine + connection
        fake_conn = MagicMock()
        fake_conn.execute = AsyncMock()
        fake_engine = MagicMock()
        fake_engine.connect = MagicMock(return_value=AsyncMockCM(fake_conn))
        fake_engine.dispose = AsyncMock()
        with patch(
            "app.extensions.data_source.service.create_async_engine",
            return_value=fake_engine,
        ):
            result = await DataSourceService.test_connection(
                _src("database", {"host": "h", "port": "5432", "database": "d"})
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_database_failure(self):
        with patch(
            "app.extensions.data_source.service.create_async_engine",
            side_effect=RuntimeError("no host"),
        ):
            result = await DataSourceService.test_connection(_src("database", {}))
        assert result.success is False
        assert "no host" in result.message

    @pytest.mark.asyncio
    async def test_api_success(self):
        fake_resp = MagicMock(status_code=200)
        client_cm = AsyncMock()
        client_cm.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)
        ))
        client_cm.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.extensions.data_source.service.httpx.AsyncClient",
            return_value=client_cm,
        ):
            result = await DataSourceService.test_connection(
                _src("api", {"url": "https://example.com"})
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_api_http_error(self):
        fake_resp = MagicMock(status_code=500)
        client_cm = AsyncMock()
        client_cm.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)
        ))
        client_cm.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.extensions.data_source.service.httpx.AsyncClient",
            return_value=client_cm,
        ):
            result = await DataSourceService.test_connection(
                _src("api", {"url": "https://example.com"})
            )
        assert result.success is False

    def test_file_exists(self):
        import tempfile, os
        from app.extensions.data_source.service import DataSourceService
        with tempfile.NamedTemporaryFile() as f:
            result = DataSourceService.test_connection_sync(
                _src("file", {"path": f.name})
            )
        assert result.success is True

    def test_file_missing(self):
        from app.extensions.data_source.service import DataSourceService
        result = DataSourceService.test_connection_sync(
            _src("file", {"path": "/no/such/path/xyz"})
        )
        assert result.success is False

    def test_gis_configured(self):
        from app.extensions.data_source.service import DataSourceService
        result = DataSourceService.test_connection_sync(
            _src("gis", {"file_name": "a.shp", "file_size": 123})
        )
        assert result.success is True

    def test_unknown_type_fails_closed(self):
        from app.extensions.data_source.service import DataSourceService
        result = DataSourceService.test_connection_sync(_src("weird", {}))
        assert result.success is False


def _src(type_: str, cfg: dict):
    """Build a DataSource-like object for tests."""
    m = MagicMock()
    m.type = type_
    m.connection_config = cfg
    return m


class AsyncMockCM:
    """Minimal async context manager wrapper for `async with engine.connect()`."""

    def __init__(self, value):
        self._value = value

    def __aenter__(self):
        return self._value

    def __aexit__(self, *exc):
        return False
```

(注:`AsyncMockCM` 在第一个测试里用作 `engine.connect()` 的返回,`engine.connect` 是同步函数返回一个 async context manager。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestTestConnection -v`
Expected: FAIL — `AttributeError: ... has no attribute 'test_connection'`

- [ ] **Step 3: 实现连接测试**

在 `backend/app/extensions/data_source/service.py` 顶部 import 区追加,并在文件末尾追加 `DataSourceService` 类:

顶部 import 追加(放在 `from __future__ import annotations` 之后、`import re` 之后):

```python
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.data_source.schemas import TestConnectionResult
```

文件末尾追加:

```python


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


async def _test_database(cfg: dict) -> TestConnectionResult:
    driver = cfg.get("driver") or "postgresql+asyncpg"
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    database = cfg.get("database", "")
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    url = f"{driver}://{username}:{password}@{host}:{port}/{database}"
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
    return TestConnectionResult(success=True, message="连接成功", metadata={"engine": driver})


async def _test_api(cfg: dict) -> TestConnectionResult:
    url = cfg.get("url", "")
    if not url:
        return TestConnectionResult(success=False, message="缺少 url")
    headers = cfg.get("headers") or {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
    if 200 <= resp.status_code < 400:
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestTestConnection -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/service.py backend/tests/test_data_source_service.py
git commit -m "feat(data-source): per-type connection testing (database/api/file/gis)"
```

---

## Task 5: 同步 + CRUD 数据访问方法

**Files:**
- Modify: `backend/app/extensions/data_source/service.py`(追加 CRUD + sync 方法)
- Test: `backend/tests/test_data_source_service.py`(追加 TestSync + TestCRUD)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_data_source_service.py` 末尾追加:

```python
class TestSync:
    @pytest.mark.asyncio
    async def test_sync_connected_when_test_ok(self):
        from app.extensions.data_source.service import DataSourceService
        src = _src("api", {"url": "https://x"})
        with patch.object(
            DataSourceService, "test_connection",
            AsyncMock(return_value=TestConnectionResult(success=True, message="ok", metadata={"k": 1})),
        ):
            out = await DataSourceService.sync(src)
        assert out["status"] == "connected"
        assert out["last_sync_at"] is not None
        assert out["metadata"] == {"k": 1}

    @pytest.mark.asyncio
    async def test_sync_error_when_test_fails(self):
        from app.extensions.data_source.service import DataSourceService
        src = _src("api", {"url": "https://x"})
        with patch.object(
            DataSourceService, "test_connection",
            AsyncMock(return_value=TestConnectionResult(success=False, message="boom")),
        ):
            out = await DataSourceService.sync(src)
        assert out["status"] == "error"


class TestCRUD:
    @pytest.mark.asyncio
    async def test_create_persists_and_returns(self):
        from app.extensions.data_source.service import DataSourceService
        from app.extensions.data_source.schemas import DataSourceCreate

        db = AsyncMock()
        added = []

        async def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "new-id"

        db.add = AsyncMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        db.commit = AsyncMock()

        req = DataSourceCreate(name="n", type="api", connection_config={"url": "u"})
        out = await DataSourceService.create(db, req, user_id=None)
        assert added, "row should be added to session"
        assert out.name == "n"

    @pytest.mark.asyncio
    async def test_list_returns_scalars(self):
        from app.extensions.data_source.service import DataSourceService

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ["a", "b"]
        db.execute = AsyncMock(return_value=result_mock)

        items = await DataSourceService.list(db)
        assert items == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_by_name(self):
        from app.extensions.data_source.service import DataSourceService

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = "FOUND"
        db.execute = AsyncMock(return_value=result_mock)

        out = await DataSourceService.get_by_name(db, "prod")
        assert out == "FOUND"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py::TestSync tests/test_data_source_service.py::TestCRUD -v`
Expected: FAIL — `AttributeError: 'DataSourceService' object has no attribute 'sync'`

- [ ] **Step 3: 实现 sync + CRUD 方法**

在 `backend/app/extensions/data_source/service.py` 的 `DataSourceService` 类**内部**(在 `test_connection_sync` 方法之后)追加以下方法,并在顶部 import 区追加:

顶部 import 追加:

```python
from sqlalchemy import select

from app.extensions.data_source.schemas import DataSourceCreate, DataSourceUpdate
from app.extensions.models import DataSource
```

(注意:`from app.extensions.data_source.schemas import TestConnectionResult` 已在 Task 4 导入;把 schemas 导入合并为一行:
`from app.extensions.data_source.schemas import DataSourceCreate, DataSourceUpdate, TestConnectionResult`)

在 `DataSourceService` 类内追加:

```python
    # ── sync (manual MVP) ──

    @staticmethod
    async def sync(source) -> dict:
        """Manual sync: reuse test_connection to probe, update status + timestamp.

        Caller persists last_sync_at/status on the row.
        """
        result = await DataSourceService.test_connection(source)
        return {
            "status": "connected" if result.success else "error",
            "last_sync_at": datetime.now(timezone.utc),
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
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_service.py -v`
Expected: 全部通过(Task 2/3/4/5 合计)

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/service.py backend/tests/test_data_source_service.py
git commit -m "feat(data-source): add manual sync + CRUD service methods"
```

---

## Task 6: REST 路由(替换桩)

**Files:**
- Modify: `backend/app/extensions/data_source/routers.py`(整文件重写)
- Test: `backend/tests/test_data_source_routers.py`(新建)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_data_source_routers.py`:

```python
"""Router-level tests for data_source endpoints. Service layer is mocked."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.extensions.data_source.routers import router
from app.extensions.data_source.schemas import DataSourceCreate


def _build_app(override_user=None, override_db=None):
    """Minimal FastAPI app with the router + dependency overrides."""
    from fastapi import FastAPI

    from app.extensions.auth.middleware import get_current_user
    from app.extensions.database import get_db

    app = FastAPI()
    app.include_router(router)

    fake_user = override_user or MagicMock(id=uuid4())

    async def _fake_db():
        yield override_db or AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


@pytest.mark.asyncio
async def test_list_returns_items():
    fake_ds = MagicMock()
    fake_ds.name = "prod"
    with patch(
        "app.extensions.data_source.routers.DataSourceService.list",
        AsyncMock(return_value=[fake_ds]),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/extensions/data-sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["name"] == "prod"


@pytest.mark.asyncio
async def test_create_returns_201():
    created = MagicMock()
    created.id = str(uuid4())
    created.name = "n"
    created.type = "api"
    created.connection_config = {}
    created.auth_type = "none"
    created.sync_mode = "manual"
    created.sync_config = None
    created.status = "disconnected"
    created.last_sync_at = None
    created.created_by = None
    created.created_at = None
    created.updated_at = None

    with patch(
        "app.extensions.data_source.routers.DataSourceService.create",
        AsyncMock(return_value=created),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/extensions/data-sources",
                json={"name": "n", "type": "api", "connection_config": {}},
            )
    assert resp.status_code == 201
    assert resp.json()["name"] == "n"


@pytest.mark.asyncio
async def test_delete_returns_204_when_found():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.delete",
        AsyncMock(return_value=True),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/data-sources/{uuid4()}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_returns_404_when_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.delete",
        AsyncMock(return_value=False),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/data-sources/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_test_endpoint_delegates_to_service():
    from app.extensions.data_source.schemas import TestConnectionResult

    src = MagicMock()
    src.name = "prod"
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=src),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.test_connection",
        AsyncMock(return_value=TestConnectionResult(success=True, message="ok")),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/test")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_test_endpoint_404_when_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=None),
    ):
        app = _build_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/test")
    assert resp.status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_routers.py -v`
Expected: FAIL — 现桩路由没有 POST/DELETE/test 端点(404 / method not allowed)

- [ ] **Step 3: 重写 routers.py**

用以下内容**整文件替换** `backend/app/extensions/data_source/routers.py`:

```python
"""Data source API router — CRUD + connection test + manual sync."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.data_source.schemas import (
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    SyncResponse,
    TestConnectionResult,
)
from app.extensions.data_source.service import DataSourceService
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/data-sources", tags=["data-sources"])


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await DataSourceService.list(db)
    return DataSourceListResponse(items=[DataSourceResponse.model_validate(i) for i in items])


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = await DataSourceService.get_by_name(db, data.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据源名称已存在")
    ds = await DataSourceService.create(db, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse.model_validate(ds)


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    return DataSourceResponse.model_validate(ds)


@router.patch("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    source_id: UUID,
    data: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.update(db, source_id, data)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse.model_validate(ds)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await DataSourceService.delete(db, source_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    await db.commit()


@router.post("/{source_id}/test", response_model=TestConnectionResult)
async def test_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    ds.status = "testing"
    await db.flush()
    result = await DataSourceService.test_connection(ds)
    ds.status = "connected" if result.success else "error"
    await db.commit()
    return result


@router.post("/{source_id}/sync", response_model=SyncResponse)
async def sync_data_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    out = await DataSourceService.sync(ds)
    ds.status = out["status"]
    ds.last_sync_at = out["last_sync_at"]
    await db.commit()
    await db.refresh(ds)
    return SyncResponse(
        id=ds.id, status=ds.status, last_sync_at=ds.last_sync_at, metadata=out["metadata"]
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_routers.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/routers.py backend/tests/test_data_source_routers.py
git commit -m "feat(data-source): full CRUD + test/sync REST endpoints"
```

---

## Task 7: MCP server(`data_source/mcp.py`)

**Files:**
- Create: `backend/app/extensions/data_source/mcp.py`
- Test: `backend/tests/test_data_source_mcp.py`(新建)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_data_source_mcp.py`:

```python
"""Tests for the data_source MCP server (tool wiring + read-only enforcement)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.extensions.data_source import mcp as ds_mcp


@pytest.mark.asyncio
async def test_list_tools_returns_four():
    tools = await ds_mcp.list_tools.__wrapped__() if hasattr(ds_mcp.list_tools, "__wrapped__") else ds_mcp.TOOLS
    names = {t.name for t in tools}
    assert names == {"list_data_sources", "get_data_source_schema", "query_data_source", "test_data_source"}


@pytest.mark.asyncio
async def test_list_data_sources_handler():
    fake = MagicMock()
    fake.id = "id1"
    fake.name = "prod"
    fake.type = "database"
    fake.status = "connected"
    fake.last_sync_at = None
    rows = [fake]

    async def _run(func):
        return await func(MagicMock())

    with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
        "app.extensions.data_source.service.DataSourceService.list", AsyncMock(return_value=rows)
    ):
        out = await ds_mcp._handle_list_data_sources({})
    payload = json.loads(out[0].text)
    assert payload[0]["name"] == "prod"


@pytest.mark.asyncio
async def test_query_rejects_write_sql():
    out = await ds_mcp._handle_query_data_source(
        {"name": "prod", "params": {"sql": "DELETE FROM users"}}
    )
    payload = json.loads(out[0].text)
    assert payload["success"] is False
    assert "仅允许" in payload["message"] or "禁止" in payload["message"]


@pytest.mark.asyncio
async def test_query_executes_readonly_sql():
    fake_row = MagicMock()
    fake_row._mapping = {"id": 1, "name": "x"}

    result_mock = MagicMock()
    result_mock.mappings.return_value.all.return_value = [fake_row._mapping]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    src = MagicMock()
    src.name = "prod"
    src.type = "database"
    src.connection_config = {}

    async def _run_in_db(func):
        return await func(session)

    async def _run_probe(func):
        return await func(session)

    with patch("app.extensions.data_source.mcp._run_in_db", _run_in_db), patch(
        "app.extensions.data_source.mcp._run_in_db_probe", _run_probe
    ), patch(
        "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
    ):
        out = await ds_mcp._handle_query_data_source(
            {"name": "prod", "params": {"sql": "SELECT id, name FROM users"}}
        )
    payload = json.loads(out[0].text)
    assert payload["success"] is True
    assert payload["rows"] == [{"id": 1, "name": "x"}]
    # sanitized SQL must carry LIMIT
    assert "LIMIT" in payload["sql"].upper()


@pytest.mark.asyncio
async def test_query_404_when_source_missing():
    with patch(
        "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=None)
    ):
        out = await ds_mcp._handle_query_data_source({"name": "nope", "params": {"sql": "SELECT 1"}})
    payload = json.loads(out[0].text)
    assert payload["success"] is False
    assert "不存在" in payload["message"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_mcp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.data_source.mcp'`

- [ ] **Step 3: 实现 MCP server**

创建 `backend/app/extensions/data_source/mcp.py`:

```python
"""Data source MCP Server — exposes read-only data query tools to the agent.

DB connection: resolves the EXTENSIONS database URL via
``get_extensions_config().database.url`` (same DB where the data_sources table
lives). NEVER uses PROJECT_DB_URL — that is a different database.

Optional override: set DATA_SOURCE_DB_URL to point elsewhere.
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


async def _resolve_db_url() -> str:
    if os.environ.get("DATA_SOURCE_DB_URL"):
        return os.environ["DATA_SOURCE_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    url = await _resolve_db_url()
    engine = create_async_engine(url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


# Alias kept for symmetry with query handler (separate engine for probes).
_run_in_db_probe = _run_in_db


TOOLS = [
    Tool(
        name="list_data_sources",
        description="列出所有已配置的外部数据源(名称/类型/状态/最近同步时间)。",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_data_source_schema",
        description="获取某数据源的结构信息(database 返回表/字段概览,api 返回 url 与说明)。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    Tool(
        name="query_data_source",
        description="从数据源取数。database 执行【只读】SQL(强制 SELECT/WITH,自动 LIMIT 200);api 发 GET。",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object", "description": "database: {sql}; api: {query, headers}"},
            },
            "required": ["name", "params"],
        },
    ),
    Tool(
        name="test_data_source",
        description="测试某数据源的连接。",
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


# ── handlers ──


async def _handle_list_data_sources(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    async def _q(session):
        rows = await DataSourceService.list(session)
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "type": r.type,
                "status": r.status,
                "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            }
            for r in rows
        ]

    data = await _run_in_db(_q)
    return _ok({"success": True, "data_sources": data})


async def _handle_get_data_source_schema(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    name = arguments["name"]

    async def _q(session):
        return await DataSourceService.get_by_name(session, name)

    src = await _run_in_db(_q)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})
    if src.type == "database":
        # best-effort: list a few tables via information_schema
        async def _probe(session):
            from sqlalchemy import text

            res = await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' LIMIT 50"
                )
            )
            return [r[0] for r in res.fetchall()]

        try:
            tables = await _run_in_db_probe(_probe)
            return _ok({"success": True, "name": name, "type": "database", "tables": tables})
        except Exception as e:  # probe failure is non-fatal
            return _ok({"success": True, "name": name, "type": "database", "tables": [], "probe_error": str(e)})
    return _ok({"success": True, "name": name, "type": src.type, "connection_config_keys": list((src.connection_config or {}).keys())})


async def _handle_query_data_source(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService, assert_readonly_select

    name = arguments["name"]
    params = arguments.get("params") or {}

    async def _lookup(session):
        return await DataSourceService.get_by_name(session, name)

    src = await _run_in_db(_lookup)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})

    if src.type == "database":
        sql = params.get("sql", "")
        try:
            safe_sql = assert_readonly_select(sql)
        except ValueError as e:
            return _ok({"success": False, "message": str(e)})

        async def _q(session):
            from sqlalchemy import text

            res = await session.execute(text(safe_sql))
            return [dict(row) for row in res.mappings().all()]

        try:
            rows = await _run_in_db(_q)
            return _ok({"success": True, "name": name, "sql": safe_sql, "row_count": len(rows), "rows": rows})
        except Exception as e:
            return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})

    if src.type == "api":
        import httpx

        url = (src.connection_config or {}).get("url", "")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params.get("query"), headers=params.get("headers"))
            return _ok({"success": True, "name": name, "status_code": resp.status_code, "text": resp.text[:4000]})
        except Exception as e:
            return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})

    return _ok({"success": False, "message": f"该类型({src.type})不支持 query,请用 get_data_source_schema"})


async def _handle_test_data_source(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    name = arguments["name"]

    async def _q(session):
        src = await DataSourceService.get_by_name(session, name)
        if src is None:
            return None
        return await DataSourceService.test_connection(src)

    result = await _run_in_db(_q)
    if result is None:
        return _ok({"success": False, "message": f"数据源不存在: {name}"})
    return _ok({"success": result.success, "message": result.message, "metadata": result.metadata})


# ── server ──

server = Server("data_sources")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "list_data_sources": _handle_list_data_sources,
        "get_data_source_schema": _handle_get_data_source_schema,
        "query_data_source": _handle_query_data_source,
        "test_data_source": _handle_test_data_source,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_mcp.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/extensions/data_source/mcp.py backend/tests/test_data_source_mcp.py
git commit -m "feat(data-source): add read-only MCP server (4 tools) for agent data access"
```

---

## Task 8: 注册 MCP server + 数据库迁移落地

**Files:**
- Modify: `extensions_config.json`(`mcpServers` 增 `data_sources`)

- [ ] **Step 1: 编辑 extensions_config.json**

在 `extensions_config.json` 的 `"mcpServers"` 对象内,紧挨 `"project"` 条目之后,新增一个 key(保持 JSON 合法,注意前一个条目末尾逗号):

```json
"data_sources": {
  "enabled": true,
  "type": "stdio",
  "command": "/app/backend/.venv/bin/python",
  "args": ["-m", "app.extensions.data_source.mcp"],
  "env": {},
  "cwd": "/app/backend",
  "url": null,
  "headers": {},
  "oauth": null,
  "description": "External data source query tools (read-only) for report writing agent"
},
```

- [ ] **Step 2: 校验 JSON 合法 + 配置可加载**

Run: `cd backend && python -c "import json; json.load(open('../extensions_config.json')); print('JSON OK')"`
Expected: `JSON OK`

Run(确认 MCP 模块可被 import,不依赖运行时 DB): `cd backend && PYTHONPATH=. uv run python -c "from app.extensions.data_source import mcp; print(sorted(t.name for t in mcp.TOOLS))"`
Expected: `['get_data_source_schema', 'list_data_sources', 'query_data_source', 'test_data_source']`

- [ ] **Step 3: 提交**

```bash
git add extensions_config.json
git commit -m "feat(data-source): register data_sources MCP server in extensions_config"
```

---

## Task 9: 全量回归 + Docker 落地验证

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && make test`
Expected: 全部通过(含新增 4 个 data_source 测试文件)。若有无关既有用例失败,记录但不视为本特性回归。

- [ ] **Step 2: lint**

Run: `cd backend && make lint`
Expected: 通过(ruff)。如报本特性文件的格式问题,运行 `make format` 后再次 `make lint`。

- [ ] **Step 3: 重启 gateway,触发建表 + 加载新 MCP server**

Run:
```bash
docker compose -p eai-docker restart gateway
```
等待 ~10s 后看日志确认:
Run: `docker compose -p eai-docker logs --tail=50 gateway | grep -iE "data_source|create_all|table"` 
Expected: 无致命错误;`init_db` 正常完成。

- [ ] **Step 4: 验证表已建 + REST 可用**

确认表存在:
Run: `docker compose -p eai-docker exec postgres-ext psql -U agentflow -d agentflow -c "\dt data_sources"`
Expected: 列出 `data_sources` 表。
(若容器名不同,用 `docker ps` 找到 postgres-ext 容器名替换。)

REST 冒烟(需带鉴权 cookie,可走前端 UI 验证):打开 `http://localhost:2026/settings → 数据源`,点「添加数据源」→ 选 file 类型 → 填一个真实路径 → 创建 → 点「测试连接」。
Expected: 创建成功,卡片出现,测试连接返回结果。

- [ ] **Step 5: 验证 Agent 能看到数据源 MCP 工具**

在前端任意 thread 对话中,让 Agent 调用 `list_data_sources`(或观察工具列表)。或直接验证 MCP 能拉起:
Run: `docker compose -p eai-docker exec gateway /app/backend/.venv/bin/python -m app.extensions.data_source.mcp < /dev/null &; sleep 2; echo "MCP module launches OK"`
Expected: 进程能启动(stdio 等待输入即正常),不报 `DATA_SOURCE_DB_URL`/`PROJECT_DB_URL` 相关错误。

- [ ] **Step 6: 最终提交(若有 lint/format 修正)**

```bash
git add -A
git commit -m "test(data-source): full regression + docker landing verification"
```

---

## Self-Review(plan 写完后自检结果)

- **Spec 覆盖**:spec §4 模型 → Task 1;§5 端点 → Task 6;§6 test 连接 → Task 4;§7 同步 → Task 5;§8 MCP 桥(4 工具 + 只读守卫 + extensions 库)→ Task 3 + Task 7;§9 注册 → Task 8;§10 测试 → 每个 Task 内 TDD。全部覆盖。
- **占位符扫描**:无 TBD/TODO;每个代码步骤含完整可运行代码。
- **类型一致性**:`DataSourceService` 方法名(list/get_by_id/get_by_name/create/update/delete/test_connection/test_connection_sync/sync)在 service / router / mcp 三处一致;`assert_readonly_select` 在 service 定义、mcp 引用,签名一致;schemas 类名在 schemas/router/test 一致。
- **关键约束**:MCP 连库走 `get_extensions_config().database.url`(Task 7 `_resolve_db_url`),并在文件 docstring 明确禁用 `PROJECT_DB_URL`;只读守卫 Task 3 单测 12 例。
