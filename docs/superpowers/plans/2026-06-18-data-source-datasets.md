# 数据源数据集层(DataSourceDataset)Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给数据源加子级"业务数据集"标注层(table_name+label+description+default_query),Agent 按业务名直查;无标注时自动兜底列表明表名。

**Architecture:** `DataSourceDataset` 模型(新表,create_all 自动建;FK 级联删)→ DataSourceService 加 dataset CRUD + resolve → REST 端点嵌在 `/api/extensions/data-sources` → MCP `list_datasets`(D 兜底)/`query_dataset`(resolve→default_query 经只读守卫)。复用 `run_readonly_query`/`assert_readonly_select`/`_run_in_db`。

**Tech Stack:** Python 3.12 · SQLAlchemy 2.0 · FastAPI · MCP SDK。pytest。

**约束:** 提交用 pathspec;pytest 从 `backend/` 跑;新表 create_all 建(无需 ALTER)。

---

## 文件结构

修改:
- `backend/app/extensions/models/__init__.py` — 加 `DataSourceDataset`
- `backend/app/extensions/data_source/schemas.py` — 4 个 Dataset schema
- `backend/app/extensions/data_source/service.py` — `DataSourceService` 加 dataset 方法
- `backend/app/extensions/data_source/routers.py` — dataset 端点
- `backend/app/extensions/data_source/mcp.py` — 2 个工具 + TOOLS/ handlers

新增测试:
- `backend/tests/test_data_source_datasets.py`(model + service + router + mcp,统一文件,分类)

---

## Task 1: `DataSourceDataset` 模型

**Files:** models/__init__.py · tests/test_data_source_datasets.py(新建)

- [ ] **Step 1: 写失败测试** `backend/tests/test_data_source_datasets.py`:
```python
"""Tests for DataSourceDataset model + service + router + mcp."""

from app.extensions.models import DataSourceDataset


class TestDatasetModel:
    def test_defaults(self):
        d = DataSourceDataset(source_id="sid", table_name="noise_monitor", label="厂界噪声")
        assert d.table_name == "noise_monitor"
        assert d.label == "厂界噪声"
        assert d.description is None
        assert d.key_columns is None
        assert d.default_query is None

    def test_tablename(self):
        assert DataSourceDataset.__tablename__ == "data_source_datasets"
```

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: ImportError — DataSourceDataset 不存在。

- [ ] **Step 3: 加模型** — 在 `backend/app/extensions/models/__init__.py` 末尾(`ApiKey` 类之后)追加:
```python


class DataSourceDataset(Base):
    """A curated business dataset (table) within a DataSource — gives the agent a
    human label + description + optional default read-only query per table."""

    __tablename__ = "data_source_datasets"
    __table_args__ = (UniqueConstraint("source_id", "table_name", name="uq_datasets_source_table"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_columns: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    default_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<DataSourceDataset(label={self.label}, table={self.table_name})>"
```
(`Text`/`JSONB`/`UniqueConstraint`/`String`/`ForeignKey`/`func`/`UUID`/`Mapped`/`uuid`/`datetime` 均已在文件顶部导入。)

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: 2 passed。

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_data_source_datasets.py
git commit -m "feat(data-source): add DataSourceDataset model"
```

---

## Task 2: Schemas

**Files:** data_source/schemas.py · tests/test_data_source_datasets.py(追加 TestDatasetSchemas)

- [ ] **Step 1: 追加测试** 到 `test_data_source_datasets.py`:
```python
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.data_source.schemas import DatasetCreate, DatasetResponse


class TestDatasetSchemas:
    def test_create_minimal(self):
        d = DatasetCreate(table_name="t", label="L")
        assert d.description is None
        assert d.key_columns is None
        assert d.default_query is None

    def test_create_requires_label(self):
        with pytest.raises(ValidationError):
            DatasetCreate(table_name="t", label="")

    def test_response_from_attributes(self):
        class _Fake:
            id = "d1"; source_id = "s1"; table_name = "t"; label = "L"
            description = None; key_columns = None; default_query = None
            created_at = None; updated_at = None

        r = DatasetResponse.model_validate(_Fake())
        assert r.label == "L"
```

- [ ] **Step 2: 运行确认失败**(ModuleNotFoundError: DatasetCreate)
- [ ] **Step 3: 加 schemas** — 在 `backend/app/extensions/data_source/schemas.py` 末尾追加:
```python


class DatasetCreate(BaseModel):
    table_name: str = Field(..., min_length=1, max_length=200)
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    key_columns: list | None = None
    default_query: str | None = None


class DatasetUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    key_columns: list | None = None
    default_query: str | None = None


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    source_id: UUID | str
    table_name: str
    label: str
    description: str | None = None
    key_columns: list | None = None
    default_query: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: 5 passed(2 + 3)。
- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/data_source/schemas.py backend/tests/test_data_source_datasets.py
git commit -m "feat(data-source): dataset pydantic schemas"
```

---

## Task 3: Service dataset CRUD + resolve

**Files:** data_source/service.py · tests/test_data_source_datasets.py(追加 TestDatasetService)

- [ ] **Step 1: 追加测试**:
```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.extensions.data_source.service import DataSourceService


def _src():
    m = MagicMock(); m.id = "sid"; return m


class TestDatasetService:
    @pytest.mark.asyncio
    async def test_create_checks_source_exists(self):
        db = AsyncMock()
        req = MagicMock(); req.table_name = "t"; req.label = "L"
        req.description = None; req.key_columns = None; req.default_query = None
        with patch.object(DataSourceService, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(ValueError):
                await DataSourceService.create_dataset(db, "sid", req)

    @pytest.mark.asyncio
    async def test_create_persists(self):
        db = AsyncMock(); added = []
        def _add(o): added.append(o)
        db.add = MagicMock(side_effect=_add); db.flush = AsyncMock()
        req = MagicMock(); req.table_name = "noise"; req.label = "厂界噪声"
        req.description = "d"; req.key_columns = ["a"]; req.default_query = None
        with patch.object(DataSourceService, "get_by_id", AsyncMock(return_value=_src())):
            ds = await DataSourceService.create_dataset(db, "sid", req)
        assert added and ds.label == "厂界噪声"

    @pytest.mark.asyncio
    async def test_list_by_source(self):
        db = AsyncMock()
        rm = MagicMock(); rm.scalars.return_value.all.return_value = ["x", "y"]
        db.execute = AsyncMock(return_value=rm)
        out = await DataSourceService.list_datasets(db, "sid")
        assert out == ["x", "y"]

    @pytest.mark.asyncio
    async def test_resolve_by_label(self):
        db = AsyncMock()
        rm = MagicMock(); rm.scalars.return_value.first.return_value = "FOUND"
        db.execute = AsyncMock(return_value=rm)
        assert await DataSourceService.resolve_dataset(db, "sid", "厂界噪声") == "FOUND"
```

- [ ] **Step 2: 运行确认失败**(AttributeError: create_dataset 不存在)
- [ ] **Step 3a: 顶部 import** — `backend/app/extensions/data_source/service.py` 顶部 import 区加:
```python
from app.extensions.models import ApiKey, DataSource, DataSourceDataset, Plugin, PluginInstance
```
(把 `DataSourceDataset` 加进现有 `from app.extensions.models import ...` 行。)

- [ ] **Step 3b: 加方法** — 在 `DataSourceService` 类内(`delete` 方法之后、`# ── read-only query` 注释之前)加:
```python
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
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: 9 passed(5 + 4)。
- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/data_source/service.py backend/tests/test_data_source_datasets.py
git commit -m "feat(data-source): dataset CRUD + resolve service methods"
```

---

## Task 4: REST 端点

**Files:** data_source/routers.py · tests/test_data_source_datasets.py(追加 TestDatasetRouter)

- [ ] **Step 1: 追加测试**:
```python
from datetime import datetime
from httpx import ASGITransport, AsyncClient

from app.extensions.data_source.routers import router


def _fake_dataset(**ov):
    base = {"id": str(uuid4()), "source_id": "sid", "table_name": "noise",
            "label": "厂界噪声", "description": None, "key_columns": None,
            "default_query": None, "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1)}
    base.update(ov); m = MagicMock()
    for k, v in base.items(): setattr(m, k, v)
    return m


def _build_app():
    from fastapi import FastAPI
    from app.extensions.auth.middleware import get_current_user
    from app.extensions.database import get_db
    app = FastAPI(); app.include_router(router)
    async def _db(): yield AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=uuid4())
    app.dependency_overrides[get_db] = _db
    return app


class TestDatasetRouter:
    @pytest.mark.asyncio
    async def test_list_datasets(self):
        with patch("app.extensions.data_source.routers.DataSourceService.list_datasets",
                   AsyncMock(return_value=[_fake_dataset()])):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get("/api/extensions/data-sources/sid/datasets")
        assert r.status_code == 200
        assert r.json()["items"][0]["label"] == "厂界噪声"

    @pytest.mark.asyncio
    async def test_create_dataset_201(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(return_value=_fake_dataset())):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/sid/datasets",
                                 json={"table_name": "noise", "label": "厂界噪声"})
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_create_404_when_source_missing(self):
        with patch("app.extensions.data_source.routers.DataSourceService.create_dataset",
                   AsyncMock(side_effect=ValueError("no source"))):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/extensions/data-sources/sid/datasets",
                                 json={"table_name": "noise", "label": "L"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_dataset_204(self):
        with patch("app.extensions.data_source.routers.DataSourceService.delete_dataset",
                   AsyncMock(return_value=True)):
            app = _build_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.delete("/api/extensions/data-sources/datasets/" + str(uuid4()))
        assert r.status_code == 204
```

- [ ] **Step 2: 运行确认失败**(端点不存在 → 404/405)
- [ ] **Step 3: 加端点** — 在 `backend/app/extensions/data_source/routers.py`,顶部 schemas import 行加 `DatasetCreate, DatasetListResponse, DatasetResponse, DatasetUpdate`,然后在文件末尾(`sync_data_source` 之后)加:
```python


# ── datasets (curated business tables within a source) ──


@router.get("/{source_id}/datasets", response_model=DatasetListResponse)
async def list_datasets(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await DataSourceService.list_datasets(db, source_id)
    return DatasetListResponse(items=[DatasetResponse.model_validate(i) for i in items])


@router.post("/{source_id}/datasets", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    source_id: UUID,
    data: DatasetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ds = await DataSourceService.create_dataset(db, source_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    await db.commit()
    await db.refresh(ds)
    return DatasetResponse.model_validate(ds)


@router.patch("/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: UUID,
    data: DatasetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ds = await DataSourceService.update_dataset(db, dataset_id, data)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    await db.commit()
    await db.refresh(ds)
    return DatasetResponse.model_validate(ds)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await DataSourceService.delete_dataset(db, dataset_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    await db.commit()
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: 13 passed(9 + 4)。
- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/data_source/routers.py backend/tests/test_data_source_datasets.py
git commit -m "feat(data-source): dataset REST endpoints"
```

---

## Task 5: MCP list_datasets + query_dataset

**Files:** data_source/mcp.py · tests/test_data_source_datasets.py(追加 TestDatasetMcp)

- [ ] **Step 1: 追加测试**:
```python
import json
from app.extensions.data_source import mcp as ds_mcp


class TestDatasetMcp:
    @pytest.mark.asyncio
    async def test_list_datasets_returns_curated(self):
        src = MagicMock(); src.id = "sid"; src.name = "prod"
        ds = MagicMock(); ds.label = "厂界噪声"; ds.table_name = "noise"
        ds.description = "d"; ds.key_columns = ["a"]; ds.default_query = None
        async def _run(func): return await func(MagicMock())
        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.list_datasets", AsyncMock(return_value=[ds])
        ):
            out = await ds_mcp._handle_list_datasets({"source_name": "prod"})
        payload = json.loads(out[0].text)
        assert payload["success"] is True
        assert payload["datasets"][0]["label"] == "厂界噪声"
        assert payload.get("auto") is not True

    @pytest.mark.asyncio
    async def test_list_datasets_fallback_when_none(self):
        src = MagicMock(); src.id = "sid"; src.name = "prod"
        async def _run(func): return await func(MagicMock())
        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.list_datasets", AsyncMock(return_value=[])
        ), patch(
            "app.extensions.data_source.service.DataSourceService.list_tables", AsyncMock(return_value=["t1", "t2"])
        ):
            out = await ds_mcp._handle_list_datasets({"source_name": "prod"})
        payload = json.loads(out[0].text)
        assert payload["auto"] is True
        assert [d["table_name"] for d in payload["datasets"]] == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_query_dataset_runs_default_query(self):
        src = MagicMock(); src.id = "sid"; src.name = "prod"
        ds = MagicMock(); ds.default_query = "SELECT 1"
        async def _run(func): return await func(MagicMock())
        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.resolve_dataset", AsyncMock(return_value=ds)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.run_readonly_query", AsyncMock(return_value=[{"x": 1}])
        ):
            out = await ds_mcp._handle_query_dataset({"source_name": "prod", "label": "L"})
        payload = json.loads(out[0].text)
        assert payload["success"] is True
        assert payload["rows"] == [{"x": 1}]

    @pytest.mark.asyncio
    async def test_query_dataset_missing_label(self):
        src = MagicMock(); src.id = "sid"; src.name = "prod"
        async def _run(func): return await func(MagicMock())
        with patch("app.extensions.data_source.mcp._run_in_db", _run), patch(
            "app.extensions.data_source.service.DataSourceService.get_by_name", AsyncMock(return_value=src)
        ), patch(
            "app.extensions.data_source.service.DataSourceService.resolve_dataset", AsyncMock(return_value=None)
        ):
            out = await ds_mcp._handle_query_dataset({"source_name": "prod", "label": "nope"})
        payload = json.loads(out[0].text)
        assert payload["success"] is False
        assert "数据集不存在" in payload["message"]
```

- [ ] **Step 2: 运行确认失败**(_handle_list_datasets 不存在)
- [ ] **Step 3: 加 handler + 注册** — 在 `backend/app/extensions/data_source/mcp.py`:

在 `TOOLS` 列表加两项(在 `test_data_source` Tool 之后):
```python
    Tool(
        name="list_datasets",
        description="列出某数据源下已标注的业务数据集(label/表/描述);无标注时自动列出源库的表名。",
        inputSchema={"type": "object", "properties": {"source_name": {"type": "string"}}, "required": ["source_name"]},
    ),
    Tool(
        name="query_dataset",
        description="按业务名(label)查询某数据源的数据集:执行该数据集的 default_query(只读)。",
        inputSchema={
            "type": "object",
            "properties": {"source_name": {"type": "string"}, "label": {"type": "string"}},
            "required": ["source_name", "label"],
        },
    ),
```

在 `_handle_test_data_source` 之后加两个 handler:
```python
async def _handle_list_datasets(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService

    source_name = arguments["source_name"]

    async def _q(session):
        src = await DataSourceService.get_by_name(session, source_name)
        if src is None:
            return None
        datasets = await DataSourceService.list_datasets(session, src.id)
        return (src, datasets)

    result = await _run_in_db(_q)
    if result is None:
        return _ok({"success": False, "message": f"数据源不存在: {source_name}"})
    src, datasets = result
    if datasets:
        return _ok({
            "success": True,
            "source": source_name,
            "datasets": [
                {
                    "label": d.label,
                    "table_name": d.table_name,
                    "description": d.description,
                    "key_columns": d.key_columns,
                    "has_default_query": bool(d.default_query),
                }
                for d in datasets
            ],
        })
    # D fallback: no curated datasets → auto-list tables from the source's own DB
    try:
        tables = await DataSourceService.list_tables(src)
        return _ok({
            "success": True, "source": source_name, "auto": True,
            "note": "未标注数据集,自动列出源库的表名",
            "datasets": [{"label": t, "table_name": t} for t in tables],
        })
    except Exception as e:
        return _ok({"success": True, "source": source_name, "auto": True, "datasets": [], "note": f"无标注数据集,且自动列出失败: {e}"})


async def _handle_query_dataset(arguments: dict) -> list[TextContent]:
    from app.extensions.data_source.service import DataSourceService, assert_readonly_select

    source_name = arguments["source_name"]
    label = arguments["label"]

    async def _lookup(session):
        src = await DataSourceService.get_by_name(session, source_name)
        if src is None:
            return (None, None)
        ds = await DataSourceService.resolve_dataset(session, src.id, label)
        return (src, ds)

    src, ds = await _run_in_db(_lookup)
    if src is None:
        return _ok({"success": False, "message": f"数据源不存在: {source_name}"})
    if ds is None:
        return _ok({"success": False, "message": f"数据集不存在: {label};用 list_datasets 查看"})
    if not ds.default_query:
        return _ok({"success": False, "message": f"数据集'{label}'未配置 default_query;请用 query_data_source 编写 SQL"})
    try:
        safe_sql = assert_readonly_select(ds.default_query)
    except ValueError as e:
        return _ok({"success": False, "message": str(e)})
    try:
        rows = await DataSourceService.run_readonly_query(src, safe_sql)
        return _ok({"success": True, "source": source_name, "dataset": label, "sql": safe_sql, "row_count": len(rows), "rows": rows})
    except Exception as e:
        return _ok({"success": False, "message": f"{type(e).__name__}: {e}"})
```

在 `call_tool` 的 `handlers` dict 加:
```python
        "list_datasets": _handle_list_datasets,
        "query_dataset": _handle_query_dataset,
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_datasets.py -q`
Expected: 17 passed(13 + 4)。
- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/data_source/mcp.py backend/tests/test_data_source_datasets.py
git commit -m "feat(data-source): MCP list_datasets (D fallback) + query_dataset"
```

---

## Task 6: 落地验证

- [ ] **Step 1: 全量数据源测试**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py tests/test_data_source_service.py tests/test_data_source_routers.py tests/test_data_source_mcp.py tests/test_data_source_datasets.py tests/test_prompt_template.py -q`
Expected: 全绿。

- [ ] **Step 2: 重启 gateway(建新表)**
`docker compose -p eai-docker restart gateway && sleep 18`
```bash
PG=$(docker ps --format "{{.Names}}" | grep -iE "postgres.*ext" | head -1)
docker exec "$PG" psql -U agentflow -d agentflow -c "\dt data_source_datasets"
```
Expected: 表存在。

- [ ] **Step 3: 端到端(经 API)** — 给"测试数据库"加一个数据集(table=plugins, label="平台插件清单", default_query="SELECT name,type FROM plugins LIMIT 10")→ `list_datasets("测试数据库")` 返回它 → `query_dataset("测试数据库","平台插件清单")` 返回真实插件行。(可用容器内 python 调 _handle_* 验证。)

---

## Self-Review

- **Spec 覆盖**:§3 模型 → T1;§4 schemas → T2;§5 service → T3;§6 端点 → T4;§7 MCP → T5;§10 验收 → T6。全覆盖。
- **占位符**:无 TBD;每步完整代码。
- **类型一致**:`DataSourceService.{list_datasets,get_dataset,create_dataset,update_dataset,delete_dataset,resolve_dataset}` 在 service/router/mcp/test 一致;`DatasetCreate/Update/Response/ListResponse` 一致;MCP handler `_handle_list_datasets`/`_handle_query_dataset` + TOOLS/handlers 注册一致。
- **复用**:query_dataset 复用 `assert_readonly_select`+`run_readonly_query`(只读通道);list_datasets D 兜底复用 `list_tables`;均经 `_run_in_db` 查 extensions 库。
