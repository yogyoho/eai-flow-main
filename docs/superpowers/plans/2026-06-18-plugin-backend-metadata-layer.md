# 插件 tab 后端(元数据层)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「设置 → 插件」tab 的 3 个前端子 tab(市场/已安装/API密钥)从全 404 变为全部可用 —— 注册目录 + 实例装机 + API Key 的纯元数据后端。

**Architecture:** 镜像已落地的 data_source 后端:3 个模型加进 `models/__init__.py`(startup `create_all` 自动建表,extensions DB / agentflow);`app/extensions/plugin/{schemas,service,routers,seed}.py`;路由 prefix `/api/extensions/plugins`,extensions auth(`get_current_user`);config 用 `jsonschema` 校验;启动预置 4 个内置插件。**纯元数据,不执行、不接 MCP。**

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) + asyncpg · Pydantic v2 · `jsonschema` · `hashlib`/`secrets` · pytest(异步)。

**关键约束:** 前端 6 文件零改动(字段与端点已与本计划一致)。所有命令在 `backend/` 下 `PYTHONPATH=. uv run pytest ...`。提交只用具体文件路径,不用 `git add -A`(活跃分支有并发 agent)。

---

## 文件结构

新增:
- `backend/app/extensions/plugin/__init__.py`(空)
- `backend/app/extensions/plugin/schemas.py` — Pydantic 模型
- `backend/app/extensions/plugin/service.py` — `PluginService` + `validate_config` + API Key 哈希
- `backend/app/extensions/plugin/routers.py` — 9 端点
- `backend/app/extensions/plugin/seed.py` — `seed_builtin_plugins` + 4 个预置插件
- `backend/tests/test_plugin_models.py`
- `backend/tests/test_plugin_service.py`
- `backend/tests/test_plugin_routers.py`

修改:
- `backend/app/extensions/models/__init__.py` — 追加 `Plugin`/`PluginInstance`/`ApiKey`
- `backend/app/extensions/database.py` — `seed_db()` 内调用 `seed_builtin_plugins`
- `backend/app/gateway/app.py` — 注册 plugin router

---

## Task 1: 数据模型(Plugin / PluginInstance / ApiKey)

**Files:**
- Modify: `backend/app/extensions/models/__init__.py`(末尾追加)
- Test: `backend/tests/test_plugin_models.py`

`models/__init__.py` 顶部已导入 `String, Text, DateTime, ForeignKey, UniqueConstraint, func`、`JSONB, UUID`、`Mapped, mapped_column`、`uuid, datetime`。

- [ ] **Step 1: 写失败测试** `backend/tests/test_plugin_models.py`:

```python
"""Tests for the plugin backend models."""

from app.extensions.models import ApiKey, Plugin, PluginInstance


class TestPluginModel:
    def test_defaults(self):
        p = Plugin(name="CAD预览", type="tool")
        assert p.name == "CAD预览"
        assert p.type == "tool"
        assert p.version == "1.0.0"
        assert p.status == "registered"
        assert p.permissions == []
        assert p.config_schema is None
        assert p.entry_point is None

    def test_tablenames(self):
        assert Plugin.__tablename__ == "plugins"
        assert PluginInstance.__tablename__ == "plugin_instances"
        assert ApiKey.__tablename__ == "plugin_api_keys"


class TestPluginInstanceModel:
    def test_defaults(self):
        inst = PluginInstance(plugin_id=None, plugin_name="x", plugin_type="tool")
        assert inst.plugin_name == "x"
        assert inst.status == "disabled"
        assert inst.config == {}
        assert inst.project_id is None


class TestApiKeyModel:
    def test_defaults(self):
        k = ApiKey(name="ci", key_prefix="abcd1234", key_hash="0" * 64)
        assert k.name == "ci"
        assert k.key_prefix == "abcd1234"
        assert k.scope == []
        assert k.expires_at is None
```

- [ ] **Step 2: 运行确认失败**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_models.py -v`
Expected: `ImportError: cannot import name 'Plugin'`

- [ ] **Step 3: 末尾追加**到 `backend/app/extensions/models/__init__.py`:

```python


class Plugin(Base):
    """Plugin registry entry (catalog). Metadata only — no execution this round."""

    __tablename__ = "plugins"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_plugins_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # data_connector|tool|output|custom
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    entry_point: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __init__(self, **kwargs):
        kwargs.setdefault("version", "1.0.0")
        kwargs.setdefault("permissions", [])
        kwargs.setdefault("status", "registered")
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Plugin(name={self.name}, type={self.type}, version={self.version})>"


class PluginInstance(Base):
    """An installed plugin instance (global only this round; project_id always null)."""

    __tablename__ = "plugin_instances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plugins.id"), nullable=False)
    plugin_name: Mapped[str] = mapped_column(String(200), nullable=False)
    plugin_type: Mapped[str] = mapped_column(String(20), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # always null this round
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")  # active|error|disabled
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __init__(self, **kwargs):
        kwargs.setdefault("config", {})
        kwargs.setdefault("status", "disabled")
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<PluginInstance(plugin_name={self.plugin_name}, status={self.status})>"


class ApiKey(Base):
    """API key for external programmatic access (issue/revoke only this round; no auth middleware)."""

    __tablename__ = "plugin_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    def __init__(self, **kwargs):
        kwargs.setdefault("scope", [])
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ApiKey(name={self.name}, key_prefix={self.key_prefix})>"
```

- [ ] **Step 4: 运行确认通过**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_models.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/models/__init__.py backend/tests/test_plugin_models.py
git commit -m "feat(plugin): add Plugin/PluginInstance/ApiKey models"
```

---

## Task 2: Pydantic schemas

**Files:**
- Create: `backend/app/extensions/plugin/__init__.py`(空文件)
- Create: `backend/app/extensions/plugin/schemas.py`
- Test: `backend/tests/test_plugin_service.py`(本任务建文件,放 TestSchemas)

- [ ] **Step 1: 建空 `backend/app/extensions/plugin/__init__.py`**(内容为空,使其成为包)

- [ ] **Step 2: 写失败测试** `backend/tests/test_plugin_service.py`:

```python
"""Tests for plugin schemas + service logic."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.extensions.plugin.schemas import (
    ApiKeyCreate,
    ApiKeyResponse,
    PluginInstanceCreate,
    PluginInstanceUpdate,
    PluginResponse,
)


class TestSchemas:
    def test_plugin_instance_create_minimal(self):
        r = PluginInstanceCreate(plugin_id=str(uuid4()))
        assert r.config == {}
        assert r.project_id is None

    def test_plugin_instance_update_partial(self):
        r = PluginInstanceUpdate(status="active")
        assert r.status == "active"
        assert r.config is None

    def test_api_key_create_requires_name(self):
        with pytest.raises(ValidationError):
            ApiKeyCreate(name="", scope=[])

    def test_plugin_response_from_attributes(self):
        class _Fake:
            id = "p1"
            name = "CAD预览"
            type = "tool"
            version = "1.0.0"
            author = None
            description = None
            config_schema = None
            entry_point = None
            icon = None
            permissions = []
            status = "registered"
            created_at = None
            updated_at = None

        resp = PluginResponse.model_validate(_Fake())
        assert resp.name == "CAD预览"

    def test_api_key_response_has_no_plaintext_field(self):
        # ApiKeyResponse must NOT expose key/key_hash — only prefix
        fields = set(ApiKeyResponse.model_fields.keys())
        assert "key" not in fields
        assert "key_hash" not in fields
        assert "key_prefix" in fields
```

- [ ] **Step 3: 运行确认失败**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py::TestSchemas -v`
Expected: `ModuleNotFoundError: No module named 'app.extensions.plugin.schemas'`

- [ ] **Step 4: 创建 `backend/app/extensions/plugin/schemas.py`**:

```python
"""Pydantic schemas for the plugin extension. Field names align with frontend
src/extensions/plugin/types.ts (snake_case in DB, frontend api.ts maps snake<->camel)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Plugin (registry) ──


class PluginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    type: str
    version: str
    author: str | None = None
    description: str | None = None
    config_schema: dict | None = None
    entry_point: str | None = None
    icon: str | None = None
    permissions: list = Field(default_factory=list)
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PluginListResponse(BaseModel):
    items: list[PluginResponse]


# ── PluginInstance ──


class PluginInstanceCreate(BaseModel):
    plugin_id: UUID | str
    project_id: UUID | str | None = None
    config: dict = Field(default_factory=dict)


class PluginInstanceUpdate(BaseModel):
    config: dict | None = None
    status: str | None = None


class PluginInstanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    plugin_id: UUID | str
    plugin_name: str
    plugin_type: str
    project_id: UUID | str | None = None
    config: dict
    status: str
    last_sync_at: datetime | None = None
    created_at: datetime | None = None


class PluginInstanceListResponse(BaseModel):
    items: list[PluginInstanceResponse]


# ── ApiKey ──


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scope: list[str] = Field(default_factory=list)
    project_id: UUID | str | None = None
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    """List/detail view — never exposes the plaintext key or the hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    name: str
    key_prefix: str
    scope: list[str] = Field(default_factory=list)
    project_id: UUID | str | None = None
    created_by: UUID | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse]


class ApiKeyCreateResponse(BaseModel):
    """Returned ONCE on creation — carries the plaintext key."""

    id: UUID | str
    key: str
```

- [ ] **Step 5: 运行确认通过**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py::TestSchemas -v`
Expected: 5 passed

- [ ] **Step 6: 提交**
```bash
git add backend/app/extensions/plugin/__init__.py backend/app/extensions/plugin/schemas.py backend/tests/test_plugin_service.py
git commit -m "feat(plugin): add pydantic schemas"
```

---

## Task 3: Service —— config 校验 + CRUD + API Key 哈希

**Files:**
- Create: `backend/app/extensions/plugin/service.py`
- Modify: `backend/tests/test_plugin_service.py`(追加 TestValidateConfig / TestApiKeyHashing / TestCRUD)

- [ ] **Step 1: 追加测试**到 `backend/tests/test_plugin_service.py` 末尾:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.extensions.plugin.service import PluginService


def _plugin(config_schema=None):
    m = MagicMock()
    m.config_schema = config_schema
    m.name = "CAD预览"
    m.type = "tool"
    m.version = "1.0.0"
    return m


class TestValidateConfig:
    def test_no_schema_passes(self):
        PluginService.validate_config(_plugin(config_schema=None), {"anything": 1})  # no raise

    def test_valid_config_passes(self):
        schema = {"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]}
        PluginService.validate_config(_plugin(config_schema=schema), {"host": "localhost"})

    def test_invalid_config_raises(self):
        import pytest
        from jsonschema import ValidationError

        schema = {"type": "object", "required": ["host"]}
        with pytest.raises(ValidationError):
            PluginService.validate_config(_plugin(config_schema=schema), {})


class TestApiKeyHashing:
    @pytest.mark.asyncio
    async def test_create_returns_plaintext_and_stores_hash(self):
        import hashlib

        db = AsyncMock()
        added = []

        async def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "k1"

        db.add = AsyncMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        with patch("app.extensions.plugin.service.secrets.token_urlsafe", return_value="ABCDEFGH12345678"):
            rec, raw = await PluginService.create_api_key(db, MagicMock(name="ci", scope=[], project_id=None, expires_at=None), user_id=None)
        assert raw == "ABCDEFGH12345678"  # plaintext returned once
        assert rec.key_prefix == "ABCDEFGH"  # first 8 chars
        assert rec.key_hash == hashlib.sha256(b"ABCDEFGH12345678").hexdigest()
        assert rec.key_hash != raw  # hash, not plaintext, stored


class TestInstanceCrud:
    @pytest.mark.asyncio
    async def test_create_denormalizes_name_type_and_sets_active(self):
        db = AsyncMock()
        plugin = _plugin()
        plugin.id = "pid"
        added = []

        async def _add(obj):
            added.append(obj)

        async def _flush():
            for o in added:
                o.id = "iid"

        db.add = AsyncMock(side_effect=_add)
        db.flush = AsyncMock(side_effect=_flush)
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=plugin)), \
             patch.object(PluginService, "validate_config", MagicMock(return_value=None)):
            req = MagicMock()
            req.plugin_id = "pid"
            req.config = {}
            inst = await PluginService.create_instance(db, req, user_id=None)
        assert inst.plugin_name == "CAD预览"
        assert inst.plugin_type == "tool"
        assert inst.status == "active"
        assert added, "instance should be added to session"

    @pytest.mark.asyncio
    async def test_create_404_when_plugin_missing(self):
        import pytest

        db = AsyncMock()
        with patch.object(PluginService, "get_plugin", AsyncMock(return_value=None)):
            req = MagicMock()
            req.plugin_id = "nope"
            req.config = {}
            with pytest.raises(ValueError):
                await PluginService.create_instance(db, req, user_id=None)
```

- [ ] **Step 2: 运行确认失败**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py -v -k "not TestSchemas"`
Expected: `ModuleNotFoundError: No module named 'app.extensions.plugin.service'`

- [ ] **Step 3: 创建 `backend/app/extensions/plugin/service.py`**:

```python
"""Plugin service: config validation, instance CRUD, API key issuance.

Metadata only — no plugin execution this round."""

from __future__ import annotations

import hashlib
import secrets

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import ApiKey, Plugin, PluginInstance
from app.extensions.plugin.schemas import ApiKeyCreate, PluginInstanceCreate, PluginInstanceUpdate


class PluginService:
    # ── config validation ──

    @staticmethod
    def validate_config(plugin, config: dict) -> None:
        """Validate config against plugin.config_schema (JSON Schema). Raises
        jsonschema.ValidationError if invalid. No-op when schema is absent."""
        schema = plugin.config_schema
        if schema:
            jsonschema.validate(instance=config, schema=schema)

    # ── registry ──

    @staticmethod
    async def list_plugins(db: AsyncSession) -> list[Plugin]:
        result = await db.execute(select(Plugin).order_by(Plugin.name.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_plugin(db: AsyncSession, plugin_id) -> Plugin | None:
        return await db.get(Plugin, plugin_id)

    # ── instances ──

    @staticmethod
    async def list_instances(db: AsyncSession, project_id=None) -> list[PluginInstance]:
        stmt = select(PluginInstance).order_by(PluginInstance.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_instance(db: AsyncSession, req: PluginInstanceCreate, user_id=None) -> PluginInstance:
        plugin = await PluginService.get_plugin(db, req.plugin_id)
        if plugin is None:
            raise ValueError(f"插件不存在: {req.plugin_id}")
        PluginService.validate_config(plugin, req.config)
        inst = PluginInstance(
            plugin_id=plugin.id,
            plugin_name=plugin.name,
            plugin_type=plugin.type,
            project_id=req.project_id,
            config=req.config,
            status="active",
            created_by=user_id,
        )
        db.add(inst)
        await db.flush()
        return inst

    @staticmethod
    async def update_instance(db: AsyncSession, instance_id, req: PluginInstanceUpdate) -> PluginInstance | None:
        inst = await db.get(PluginInstance, instance_id)
        if inst is None:
            return None
        if req.config is not None:
            plugin = await PluginService.get_plugin(db, inst.plugin_id)
            if plugin is not None:
                PluginService.validate_config(plugin, req.config)
            inst.config = req.config
        if req.status is not None:
            inst.status = req.status
        await db.flush()
        return inst

    @staticmethod
    async def delete_instance(db: AsyncSession, instance_id) -> bool:
        inst = await db.get(PluginInstance, instance_id)
        if inst is None:
            return False
        await db.delete(inst)
        await db.flush()
        return True

    # ── API keys ──

    @staticmethod
    async def list_api_keys(db: AsyncSession) -> list[ApiKey]:
        result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def create_api_key(db: AsyncSession, req: ApiKeyCreate, user_id=None) -> tuple[ApiKey, str]:
        raw = secrets.token_urlsafe(32)
        rec = ApiKey(
            name=req.name,
            key_prefix=raw[:8],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scope=req.scope or [],
            project_id=req.project_id,
            created_by=user_id,
            expires_at=req.expires_at,
        )
        db.add(rec)
        await db.flush()
        return rec, raw

    @staticmethod
    async def delete_api_key(db: AsyncSession, key_id) -> bool:
        rec = await db.get(ApiKey, key_id)
        if rec is None:
            return False
        await db.delete(rec)
        await db.flush()
        return True
```

- [ ] **Step 4: 运行确认通过**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py -v`
Expected: TestSchemas(5) + TestValidateConfig(3) + TestApiKeyHashing(1) + TestInstanceCrud(2) = 11 passed

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/plugin/service.py backend/tests/test_plugin_service.py
git commit -m "feat(plugin): service — config validation, instance CRUD, API key hashing"
```

---

## Task 4: 预置插件 seed

**Files:**
- Create: `backend/app/extensions/plugin/seed.py`
- Modify: `backend/app/extensions/database.py:1325-1331`(output seed 块之后加 plugin seed 调用)
- Test: `backend/tests/test_plugin_service.py`(追加 TestSeed)

- [ ] **Step 1: 追加测试**到 `backend/tests/test_plugin_service.py` 末尾:

```python
class TestSeed:
    @pytest.mark.asyncio
    async def test_seed_inserts_builtins_when_empty(self):
        from app.extensions.plugin import seed as seed_mod

        db = AsyncMock()
        existing = MagicMock()
        existing.scalars.return_value.first.return_value = None  # none exist
        db.execute = AsyncMock(return_value=existing)
        db.add = AsyncMock()
        db.commit = AsyncMock()
        await seed_mod.seed_builtin_plugins(db)
        assert db.add.await_count == len(seed_mod.BUILTIN_PLUGINS)

    @pytest.mark.asyncio
    async def test_seed_idempotent_when_already_present(self):
        from app.extensions.plugin import seed as seed_mod

        db = AsyncMock()
        existing = MagicMock()
        existing.scalars.return_value.first.return_value = MagicMock()  # already exists
        db.execute = AsyncMock(return_value=existing)
        db.add = AsyncMock()
        db.commit = AsyncMock()
        await seed_mod.seed_builtin_plugins(db)
        assert db.add.await_count == 0  # nothing added
```

- [ ] **Step 2: 运行确认失败**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py::TestSeed -v`
Expected: `ModuleNotFoundError: No module named 'app.extensions.plugin.seed'`

- [ ] **Step 3: 创建 `backend/app/extensions/plugin/seed.py`**:

```python
"""Seed built-in plugins into the registry. Idempotent."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.models import Plugin

logger = logging.getLogger(__name__)

BUILTIN_PLUGINS = [
    {
        "name": "地质数据连接器",
        "type": "data_connector",
        "description": "对接地质钻孔数据库,拉取地层信息。",
        "config_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "title": "主机地址"},
                "port": {"type": "integer", "default": 5432, "title": "端口"},
                "database": {"type": "string", "title": "数据库名"},
            },
            "required": ["host", "database"],
        },
    },
    {
        "name": "环境监测连接器",
        "type": "data_connector",
        "description": "对接在线监测平台,获取实时监测数据。",
        "config_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "title": "API 地址"}},
            "required": ["url"],
        },
    },
    {
        "name": "CAD 文件预览",
        "type": "tool",
        "description": "解析 DWG/DXF,生成预览图和元数据。",
        "config_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string", "title": "文件路径"}},
        },
    },
    {
        "name": "GIS 数据可视化",
        "type": "tool",
        "description": "加载 Shapefile/GeoJSON,在报告中嵌入地图。",
        "config_schema": {
            "type": "object",
            "properties": {"layer_url": {"type": "string", "title": "图层地址"}},
        },
    },
]


async def seed_builtin_plugins(db: AsyncSession) -> None:
    """Insert built-in plugins if not present. Idempotent by (name, version)."""
    added = 0
    for p in BUILTIN_PLUGINS:
        name = p["name"]
        version = p.get("version", "1.0.0")
        existing = await db.execute(
            select(Plugin).where(Plugin.name == name, Plugin.version == version)
        )
        if existing.scalars().first():
            continue
        db.add(
            Plugin(
                name=name,
                type=p["type"],
                version=version,
                description=p.get("description"),
                config_schema=p.get("config_schema"),
                permissions=[],
                status="registered",
            )
        )
        added += 1
    if added:
        await db.commit()
        logger.info("Seeded %d built-in plugins", added)
```

- [ ] **Step 4: 运行确认通过**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_service.py::TestSeed -v`
Expected: 2 passed

- [ ] **Step 5: 挂到 `seed_db()`**。编辑 `backend/app/extensions/database.py`,在 output seed 块(line 1325-1331)之后、`finally:`(line 1332)之前,插入:

old_string(精确匹配现有):
```python
            # Seed built-in layout templates for report output
            try:
                from app.extensions.output.seed import seed_builtin_templates

                await seed_builtin_templates(session)
            except Exception as e:
                logger.warning(f"Failed to seed layout templates: {e}")
    finally:
```
new_string:
```python
            # Seed built-in layout templates for report output
            try:
                from app.extensions.output.seed import seed_builtin_templates

                await seed_builtin_templates(session)
            except Exception as e:
                logger.warning(f"Failed to seed layout templates: {e}")

            # Seed built-in plugins for the plugin marketplace
            try:
                from app.extensions.plugin.seed import seed_builtin_plugins

                await seed_builtin_plugins(session)
            except Exception as e:
                logger.warning(f"Failed to seed built-in plugins: {e}")
    finally:
```

- [ ] **Step 6: 确认 import 不破**
Run: `cd backend && PYTHONPATH=. uv run python -c "from app.extensions.plugin.seed import seed_builtin_plugins, BUILTIN_PLUGINS; print(len(BUILTIN_PLUGINS), 'plugins')"`
Expected: `4 plugins`

- [ ] **Step 7: 提交**
```bash
git add backend/app/extensions/plugin/seed.py backend/app/extensions/database.py backend/tests/test_plugin_service.py
git commit -m "feat(plugin): seed 4 built-in plugins on startup"
```

---

## Task 5: REST 路由(9 端点)

**Files:**
- Create: `backend/app/extensions/plugin/routers.py`
- Test: `backend/tests/test_plugin_routers.py`

- [ ] **Step 1: 写失败测试** `backend/tests/test_plugin_routers.py`:

```python
"""Router-level tests for plugin endpoints. Service layer is mocked."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.extensions.plugin.routers import router


def _fake_plugin(**ov):
    base = {
        "id": str(uuid4()), "name": "CAD 文件预览", "type": "tool", "version": "1.0.0",
        "author": None, "description": None, "config_schema": None, "entry_point": None,
        "icon": None, "permissions": [], "status": "registered",
        "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1),
    }
    base.update(ov)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


def _fake_instance(**ov):
    base = {
        "id": str(uuid4()), "plugin_id": str(uuid4()), "plugin_name": "CAD 文件预览",
        "plugin_type": "tool", "project_id": None, "config": {}, "status": "active",
        "last_sync_at": None, "created_at": datetime(2026, 1, 1),
    }
    base.update(ov)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


def _build_app():
    from fastapi import FastAPI

    from app.extensions.auth.middleware import get_current_user
    from app.extensions.database import get_db

    app = FastAPI()
    app.include_router(router)
    fake_user = MagicMock(id=uuid4())

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


@pytest.mark.asyncio
async def test_list_registry():
    with patch("app.extensions.plugin.routers.PluginService.list_plugins",
               AsyncMock(return_value=[_fake_plugin(name="CAD 文件预览")])):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/extensions/plugins/registry")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["name"] == "CAD 文件预览"


@pytest.mark.asyncio
async def test_install_instance_201():
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "create_instance", AsyncMock(return_value=_fake_instance())):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/instances",
                                     json={"plugin_id": str(uuid4()), "config": {}})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_install_instance_400_on_invalid_config():
    from jsonschema import ValidationError

    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "validate_config", MagicMock(side_effect=ValidationError("bad"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/instances",
                                     json={"plugin_id": str(uuid4()), "config": {}})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_instance_toggle():
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "update_instance", AsyncMock(return_value=_fake_instance(status="disabled"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(f"/api/extensions/plugins/instances/{uuid4()}",
                                      json={"status": "disabled"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_delete_instance_204():
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "delete_instance", AsyncMock(return_value=True)):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/plugins/instances/{uuid4()}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_api_key_returns_plaintext_once():
    fake_rec = MagicMock()
    fake_rec.id = str(uuid4())
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "create_api_key", AsyncMock(return_value=(fake_rec, "PLAINTEXT_KEY_123"))):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/plugins/api-keys",
                                     json={"name": "ci", "scope": []})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"] == "PLAINTEXT_KEY_123"
    assert "id" in body


@pytest.mark.asyncio
async def test_list_api_keys_no_plaintext():
    fake_key = MagicMock()
    fake_key.id = str(uuid4())
    fake_key.name = "ci"
    fake_key.key_prefix = "abcd1234"
    fake_key.scope = []
    fake_key.project_id = None
    fake_key.created_by = None
    fake_key.expires_at = None
    fake_key.last_used_at = None
    fake_key.created_at = datetime(2026, 1, 1)
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "list_api_keys", AsyncMock(return_value=[fake_key])):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/extensions/plugins/api-keys")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["key_prefix"] == "abcd1234"
    assert "key" not in item and "key_hash" not in item


@pytest.mark.asyncio
async def test_revoke_api_key_204():
    with patch.object(__import__("app.extensions.plugin.routers", fromlist=["PluginService"]).PluginService,
                      "delete_api_key", AsyncMock(return_value=True)):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/extensions/plugins/api-keys/{uuid4()}")
    assert resp.status_code == 204
```

- [ ] **Step 2: 运行确认失败**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_routers.py -v`
Expected: `ModuleNotFoundError: No module named 'app.extensions.plugin.routers'`

- [ ] **Step 3: 创建 `backend/app/extensions/plugin/routers.py`**:

```python
"""Plugin API router — registry + instances + API keys (metadata only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from jsonschema import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.plugin.schemas import (
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyCreate,
    PluginInstanceCreate,
    PluginInstanceListResponse,
    PluginInstanceResponse,
    PluginInstanceUpdate,
    PluginListResponse,
    PluginResponse,
)
from app.extensions.plugin.service import PluginService
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/plugins", tags=["plugins"])


# ── registry ──


@router.get("/registry", response_model=PluginListResponse)
async def list_registry(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await PluginService.list_plugins(db)
    return PluginListResponse(items=[PluginResponse.model_validate(i) for i in items])


@router.get("/registry/{plugin_id}", response_model=PluginResponse)
async def get_plugin(
    plugin_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    p = await PluginService.get_plugin(db, plugin_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在")
    return PluginResponse.model_validate(p)


# ── instances ──


@router.get("/instances", response_model=PluginInstanceListResponse)
async def list_instances(
    project_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await PluginService.list_instances(db, project_id=project_id)
    return PluginInstanceListResponse(items=[PluginInstanceResponse.model_validate(i) for i in items])


@router.post("/instances", response_model=PluginInstanceResponse, status_code=status.HTTP_201_CREATED)
async def install_instance(
    data: PluginInstanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        inst = await PluginService.create_instance(db, data, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    await db.commit()
    await db.refresh(inst)
    return PluginInstanceResponse.model_validate(inst)


@router.patch("/instances/{instance_id}", response_model=PluginInstanceResponse)
async def update_instance(
    instance_id: UUID,
    data: PluginInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        inst = await PluginService.update_instance(db, instance_id, data)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    if inst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件实例不存在")
    await db.commit()
    await db.refresh(inst)
    return PluginInstanceResponse.model_validate(inst)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await PluginService.delete_instance(db, instance_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="插件实例不存在")
    await db.commit()


# ── API keys ──


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    items = await PluginService.list_api_keys(db)
    return ApiKeyListResponse(items=[ApiKeyResponse.model_validate(i) for i in items])


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rec, raw = await PluginService.create_api_key(db, data, user_id=current_user.id)
    await db.commit()
    await db.refresh(rec)
    return ApiKeyCreateResponse(id=rec.id, key=raw)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    ok = await PluginService.delete_api_key(db, key_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    await db.commit()
```

- [ ] **Step 4: 运行确认通过**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_routers.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/plugin/routers.py backend/tests/test_plugin_routers.py
git commit -m "feat(plugin): REST endpoints — registry, instances, API keys"
```

---

## Task 6: 注册路由 + 全量回归

**Files:**
- Modify: `backend/app/gateway/app.py`(import + include_router)

- [ ] **Step 1: 在 `backend/app/gateway/app.py` 加 import 与注册**。

在 data_source router import 行(`from app.extensions.data_source.routers import router as data_source_router`)附近,加:
```python
from app.extensions.plugin.routers import router as plugin_router
```
在 `app.include_router(data_source_router)` 附近,加:
```python
app.include_router(plugin_router)
```
(用 grep 定位现有 `data_source_router` 两处,在其后各加一行。)

- [ ] **Step 2: 全量 plugin 测试**
Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_plugin_models.py tests/test_plugin_service.py tests/test_plugin_routers.py -q`
Expected: 5 + 13 + 8 = 26 passed(其中 service 含 TestSchemas5+ValidateConfig3+ApiKeyHashing1+InstanceCrud2+Seed2=13)

- [ ] **Step 3: import 不破**
Run: `cd backend && PYTHONPATH=. uv run python -c "from app.gateway.app import app; print('routes:', len([r for r in app.routes if '/plugins' in getattr(r,'path','')]))"`
Expected: `routes: 9`

- [ ] **Step 4: 提交**
```bash
git add backend/app/gateway/app.py
git commit -m "feat(plugin): register plugin router in gateway"
```

---

## Task 7: Docker 落地验证

- [ ] **Step 1: 重启 gateway(建表 + seed)**
Run: `docker compose -p eai-docker restart gateway && sleep 15`

- [ ] **Step 2: 表已建 + 预置插件已 seed**
Run:
```bash
PG=$(docker ps --format "{{.Names}}" | grep -iE "postgres.*ext" | head -1)
docker exec "$PG" psql -U agentflow -d agentflow -c "\dt plugin_*"
docker exec "$PG" psql -U agentflow -d agentflow -c "SELECT name, type, status FROM plugins;"
```
Expected: `plugin_instances`、`plugin_api_keys`、`plugins` 三张表;`plugins` 表有 4 行(地质数据连接器/环境监测连接器/CAD 文件预览/GIS 数据可视化)。

- [ ] **Step 3: 启动无报错**
Run: `docker compose -p eai-docker logs --tail=60 gateway 2>&1 | grep -iE "traceback|error|failed to seed" | head`
Expected: 空(无致命错误;`Failed to seed` 若有则排查)。

- [ ] **Step 4: 端到端冒烟(经前端 UI)**
打开 `http://localhost:2026/settings → 插件`:
- 市场 tab:应显示 4 个预置插件(install 按钮可点)。
- 点 install → 已安装 tab 出现该实例(状态运行中)→ 点禁用/启用、配置可操作。
- API密钥 tab:点创建 → 弹出明文 key(仅一次)→ 列表显示 prefix;点吊销可删。
Expected: 三个子 tab 全部可用,无 404。

---

## Self-Review(plan 写完后自检)

- **Spec 覆盖**:§4 三模型 → Task 1;§5 九端点 → Task 5;§6 config 校验 → Task 3;§7 预置 seed → Task 4;§8 API Key 哈希 → Task 3;§9 文件结构 → 各 Task;§10 测试 → 每 Task TDD。注册路由(Task 6)、Docker 落地(Task 7)。全覆盖。
- **占位符**:无 TBD;每步含完整可运行代码。
- **类型一致**:`PluginService` 方法名(list_plugins/get_plugin/validate_config/list_instances/create_instance/update_instance/delete_instance/list_api_keys/create_api_key/delete_api_key)在 service/router/test 三处一致;schemas 类名一致;前端 api.ts 字段(id/plugin_id/plugin_name/plugin_type/key_prefix 等)与响应模型一致。
- **前端零改动**:api.ts 的 9 个调用(registry GET、instances GET/POST/PATCH/DELETE、api-keys GET/POST/DELETE)与本计划端点一一对应;install body `{plugin_id, project_id?, config}`、toggle body `{status}`、update body `{config}` 均被 `PluginInstanceCreate`/`PluginInstanceUpdate` 覆盖。
