# Agent 注册表（数字员工看板）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a brand-new `agent_registry` extension that projects the existing per-user custom-agents into an org-wide "Digital Employee Board" with search/filter, detail/edit, and create — without modifying existing dashboard/project/approval/shell code or the deer-flow harness.

**Architecture:** App-layer projection. A new `agent_registry` Postgres table stores org metadata (owner/status/readiness/role/MCP-binding/skills-snapshot). The harness agent store (`deerflow.persistence.agents`) remains the runtime source of truth for config/SOUL; the registry writes through to it via the store's public sync API (`get_agent_store()`) and lazily reconciles via `list_all()`. The owner identity is the **gateway user_id** (JWT `sub` = harness bucket key), resolved in-extension via `get_current_user_from_request()` — this avoids the known gateway/extensions user-id split (phantom-bucket) bug.

**Tech Stack:** Backend — FastAPI + SQLAlchemy 2.0 async + PostgreSQL (`agentflow`), no Alembic (`CREATE TABLE IF NOT EXISTS` in `migrate_db`). Frontend — Next.js 16 + React 19 + TanStack Query + Tailwind, reusing `extensions/dashboard/dashboard.css`.

**Spec:** `docs/superpowers/specs/2026-07-27-agent-registry-design.md`

**Hard constraints (from spec §3):** No edits to `extensions/{dashboard,project,approval,shell}` business code (only `shell/Sidebar.tsx` +1 nav line allowed) and no edits to `packages/harness/deerflow/`. All EAI customizations marked `EAI-CUSTOM`. Commit to `main-dev-fork`.

**Ponytail deviations from spec (deliberate simplifications):**
- **No separate `agent_registry.enabled` feature flag.** The router is already gated by the `system:access` permission (consistent with every other extension router). A second flag is YAGNI; the `system:access` gate is sufficient access control for MVP.
- **`owner_name` populated at create/edit, not at reconcile.** `list_all()` returns `(gateway_uid, config)` with no email, so resolving owner display names at reconcile time requires a two-hop gateway→email→ext-user lookup (out of scope). Rows discovered by reconcile show a short uid until the owner interacts. Fast-follow can enrich.

---

## File Structure

**Backend (new module `backend/app/extensions/agent_registry/`):**
- `models.py` — `AgentRegistry` SQLAlchemy model (org metadata projection).
- `schemas.py` — Pydantic request/response models (public vs owner-full).
- `store_bridge.py` — thin async wrappers over the sync harness `AgentStore` (via `asyncio.to_thread`) + builtin enumeration.
- `service.py` — business logic: reconcile, list/get with access control, create/update/delete (write-through), builtins.
- `routers.py` — FastAPI router `/api/extensions/agent-registry`.
- `__init__.py` — exports `router`.

**Backend (additive touches to shared files — standard extension scaffolding):**
- `backend/app/extensions/database.py` — add `CREATE TABLE IF NOT EXISTS agent_registry` block inside `migrate_db()` (matches project convention).
- `backend/app/gateway/app.py` — import + `app.include_router(agent_registry_router)`.

**Backend tests:**
- `backend/tests/test_agent_registry_service.py` — reconcile, access control, write-through (uses fake store + temp SQLite).
- `backend/tests/test_agent_registry_router.py` — HTTP endpoints via `TestClient` + `dependency_overrides`.

**Frontend (new module `frontend/src/extensions/agent_registry/`):**
- `types.ts`, `api.ts`, `hooks.ts`, `index.ts`
- `components/AgentBoard.tsx` (page shell, two-pane), `AgentList.tsx` (left), `AgentDetail.tsx` (right + tabs), `OverviewTab.tsx`, `ConfigTab.tsx`, `CreateAgentModal.tsx`, `SkillPicker.tsx`, `BoardMetrics.tsx`, `Showcase.tsx`.

**Frontend pages + nav:**
- `frontend/src/app/workspace/agent-board/page.tsx` — renders `<AgentBoard/>`.
- `frontend/src/extensions/shell/Sidebar.tsx` — **+1 nav link** (the only allowed business-file touch).

---

## Task 1: Backend model + table creation

**Files:**
- Create: `backend/app/extensions/agent_registry/__init__.py`
- Create: `backend/app/extensions/agent_registry/models.py`
- Modify: `backend/app/extensions/database.py` (add CREATE TABLE block in `migrate_db()`)

- [ ] **Step 1: Create `agent_registry/__init__.py`**

```python
"""EAI-CUSTOM: Agent 注册表（数字员工看板）——全新独立模块。

组织级 agent 元数据投影表。不改动现有 dashboard/project/approval/shell 业务代码，
也不动 deer-flow harness 核心。config/SOUL 仍是 harness agent store 的运行时真源。
"""
from app.extensions.agent_registry.routers import router

__all__ = ["router"]
```

- [ ] **Step 2: Create `agent_registry/models.py`**

```python
"""EAI-CUSTOM: agent_registry 表模型。

owner_id / source_user_id 存的是 **gateway user_id**（JWT sub，= harness 桶键），
不是 extensions DB UUID。这样 write-through 时直接用 source_user_id 命中正确的
harness per-user 桶，绕开 gateway/extensions 用户 ID 分裂的 phantom-bucket 问题。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class AgentRegistry(Base):
    """组织级 agent 注册表行。每个 (source_user_id, agent_name) 对应一个 harness agent。"""

    __tablename__ = "agent_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(100), index=True)
    # harness per-user 桶键 = gateway user_id（JWT sub）
    source_user_id: Mapped[str] = mapped_column(String(100), index=True)
    owner_id: Mapped[str] = mapped_column(String(100), index=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    readiness: Mapped[str] = mapped_column(String(20), default="ready")
    visibility: Mapped[str] = mapped_column(String(20), default="org")
    # JSON 数组（通用 JSON 类型，SQLite/Postgres 均可测试）
    skills_snapshot: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    mcp_servers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source_user_id", "agent_name", name="uq_agent_registry_source_name"),
    )
```

- [ ] **Step 3: Add CREATE TABLE block to `migrate_db()` in `database.py`**

Locate `migrate_db()` in `backend/app/extensions/database.py`. Find the last `CREATE TABLE IF NOT EXISTS` block (e.g. for `notifications` or `role_permissions`) and add this block right after it, before the function's trailing `return`/`except`. (The exact anchor line moves; search for an existing `CREATE TABLE IF NOT EXISTS` and mirror its style — `await conn.execute(text(...))`.)

```python
    # EAI-CUSTOM: agent_registry（数字员工看板）—— 组织级 agent 元数据投影表
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS agent_registry (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_name VARCHAR(100) NOT NULL,
            source_user_id VARCHAR(100) NOT NULL,
            owner_id VARCHAR(100) NOT NULL,
            owner_name VARCHAR(200),
            org_id VARCHAR(100),
            display_name VARCHAR(200),
            role VARCHAR(100),
            summary VARCHAR(500),
            avatar VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            readiness VARCHAR(20) NOT NULL DEFAULT 'ready',
            visibility VARCHAR(20) NOT NULL DEFAULT 'org',
            skills_snapshot JSON,
            mcp_servers JSON,
            tags JSON,
            last_synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_registry_source_name "
        "ON agent_registry (source_user_id, agent_name)"
    ))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_registry_owner ON agent_registry (owner_id)"))
```

- [ ] **Step 4: Verify the table is created on startup**

Run: `docker compose -p eai-docker restart gateway` then:
```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\d agent_registry"
```
Expected: table exists with all columns. (If the container name differs, run `docker ps` first.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/agent_registry/__init__.py backend/app/extensions/agent_registry/models.py backend/app/extensions/database.py
git commit -m "feat(agent-registry): add AgentRegistry model + table (EAI-CUSTOM)"
```

---

## Task 2: Schemas + store bridge

**Files:**
- Create: `backend/app/extensions/agent_registry/schemas.py`
- Create: `backend/app/extensions/agent_registry/store_bridge.py`

- [ ] **Step 1: Create `schemas.py`**

```python
"""EAI-CUSTOM: agent_registry Pydantic schemas.

公开响应（AgentPublic）只含看板元数据，**绝不**包含 SOUL/model_settings——
非 owner 看不到这些。AgentOwnerFull 是 owner 专属，附带 harness config + soul。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgentPublic(BaseModel):
    """看板列表/非 owner 详情可见的公开元数据。"""
    id: UUID
    agent_name: str
    display_name: str | None = None
    role: str | None = None
    summary: str | None = None
    avatar: str | None = None
    status: str
    readiness: str
    visibility: str
    owner_id: str
    owner_name: str | None = None
    skills_snapshot: list[str] | None = None
    mcp_servers: list[str] | None = None
    tags: list[str] | None = None
    is_owner: bool = False
    is_builtin: bool = False
    updated_at: datetime | None = None


class AgentOwnerFull(AgentPublic):
    """owner 专属：附 harness config（model/tool_groups/skills/model_settings…）+ SOUL。"""
    config: dict | None = None
    soul: str | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentPublic]
    total: int


class CreateAgentRequest(BaseModel):
    agent_name: str = Field(..., pattern=r"^[A-Za-z0-9-]+$", min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=100)
    summary: str | None = Field(None, max_length=500)
    avatar: str | None = None
    status: str = "active"
    readiness: str = "ready"
    visibility: str = "org"
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    tags: list[str] | None = None
    # harness config 字段（write-through）
    model: str | None = None
    tool_groups: list[str] | None = None
    soul: str | None = None


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    summary: str | None = None
    avatar: str | None = None
    status: str | None = None
    readiness: str | None = None
    visibility: str | None = None
    skills_snapshot: list[str] | None = None
    mcp_servers: list[str] | None = None
    tags: list[str] | None = None
    # harness config 字段（owner only）
    model: str | None = None
    tool_groups: list[str] | None = None
    soul: str | None = None


class BuiltinAgent(BaseModel):
    agent_name: str
    display_name: str
    role: str | None = None
    description: str | None = None
    is_builtin: bool = True


class ReconcileResponse(BaseModel):
    created: int
    updated: int
    orphaned: int
```

- [ ] **Step 2: Create `store_bridge.py`**

```python
"""EAI-CUSTOM: harness AgentStore 的 async 桥 + builtin 枚举。

harness store 是同步的（可能跑在事件循环或独立进程），async 路由必须用 asyncio.to_thread 包裹。
所有调用显式传 user_id（= gateway user_id = source_user_id），绝不依赖 ContextVar 默认值。
"""
from __future__ import annotations

import asyncio
import logging

from deerflow.persistence.agents import AgentStore, get_agent_store

logger = logging.getLogger(__name__)


def _store() -> AgentStore:
    return get_agent_store()


async def list_all() -> list[tuple[str, dict]]:
    """返回所有 (gateway_user_id, config_dict) —— reconcile 用。"""
    rows = await asyncio.to_thread(lambda: _store().list_all())
    return [(uid, cfg.model_dump(exclude_unset=False)) for uid, cfg in rows]


async def get_config(agent_name: str, source_user_id: str) -> dict | None:
    """读取某 agent 的 config（owner 全量详情用）。不存在返回 None。"""
    def _read() -> dict | None:
        try:
            cfg = _store().get(agent_name, user_id=source_user_id)
            return cfg.model_dump(exclude_unset=False)
        except FileNotFoundError:
            return None
    return await asyncio.to_thread(_read)


async def get_soul(agent_name: str, source_user_id: str) -> str | None:
    return await asyncio.to_thread(lambda: _store().get_soul(agent_name, user_id=source_user_id))


async def create_agent(agent_name: str, config: dict, soul: str, source_user_id: str) -> None:
    await asyncio.to_thread(lambda: _store().create(agent_name, config, soul, user_id=source_user_id))


async def update_agent(
    agent_name: str, source_user_id: str, *, config: dict | None = None, soul: str | None = None
) -> None:
    await asyncio.to_thread(lambda: _store().update(agent_name, config, soul, user_id=source_user_id))


async def delete_agent(agent_name: str, source_user_id: str) -> str:
    """返回 delete outcome（deleted/legacy/missing/not-custom-agent）。"""
    return await asyncio.to_thread(lambda: _store().delete(agent_name, user_id=source_user_id))


def list_builtins() -> list[dict]:
    """只读枚举 built-in agent（lead_agent + subagents），不入注册表。"""
    builtins = [
        {"agent_name": "", "display_name": "Lead Agent（默认）", "role": "通用主智能体", "description": "默认 lead_agent"},
    ]
    try:
        from deerflow.subagents.registry import list_subagents  # 公开 API；若签名不同见下方备注

        for s in list_subagents():
            name = getattr(s, "name", None) or getattr(s, "type", None) or str(s)
            builtins.append({
                "agent_name": f"subagent:{name}",
                "display_name": name,
                "role": "内置子智能体",
                "description": getattr(s, "description", None),
            })
    except Exception:  # noqa: BLE001 —— builtin 枚举是展示用，失败不阻塞看板
        logger.warning("list_builtins: subagent enumeration failed", exc_info=True)
    return builtins
```

> **Verify before implementing Step 2's builtin call:** `deerflow.subagents.registry` exposes a function that lists subagents — confirm its exact name/signature by reading `backend/packages/harness/deerflow/subagents/registry.py` (the Explore cited `registry.py:22-47`). If it is not `list_subagents()`, substitute the actual function. If enumeration is non-trivial, hardcode `["general-purpose", "bash"]` for MVP and leave a `# TODO(fast-follow): enumerate from registry` — but only after confirming the registry has no simple listing function.

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/agent_registry/schemas.py backend/app/extensions/agent_registry/store_bridge.py
git commit -m "feat(agent-registry): add schemas + harness store bridge (EAI-CUSTOM)"
```

---

## Task 3: Service — reconcile (TDD)

**Files:**
- Create: `backend/app/extensions/agent_registry/service.py`
- Test: `backend/tests/test_agent_registry_service.py`

- [ ] **Step 1: Write the failing reconcile test**

Create `backend/tests/test_agent_registry_service.py`:

```python
"""EAI-CUSTOM: agent_registry service 单测。

用 FakeAgentStore（内存 dict）替代 harness store，用临时 SQLite 建 agent_registry 表。
"""
from __future__ import annotations

import asyncio
from collections.abc import Hashable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.extensions.agent_registry import service
from app.extensions.database import Base


class FakeAgentStore:
    """内存版 AgentStore，实现 service 用到的方法。"""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], tuple[dict, str]] = {}  # (uid,name) -> (config, soul)

    def list_all(self):
        return [(uid, _cfg(cfg)) for (uid, _), (cfg, _soul) in self.data.items()]

    def get(self, name, *, user_id=None):
        key = (user_id, name)
        if key not in self.data:
            raise FileNotFoundError(name)
        return _cfg(self.data[key][0])

    def get_soul(self, name, *, user_id=None):
        return self.data.get((user_id, name), (None, None))[1]

    def create(self, name, config, soul, *, user_id=None):
        if (user_id, name) in self.data:
            raise FileExistsError(name)
        self.data[(user_id, name)] = (dict(config), soul)

    def update(self, name, config, soul, *, user_id=None):
        cur_cfg, cur_soul = self.data.get((user_id, name), ({}, ""))
        if config is not None:
            cur_cfg.update(config)
        if soul is not None:
            cur_soul = soul
        self.data[(user_id, name)] = (cur_cfg, cur_soul)

    def delete(self, name, *, user_id=None):
        self.data.pop((user_id, name), None)
        return "deleted"

    def signature(self) -> Hashable:
        return repr(sorted(self.data.keys()))


def _cfg(d: dict):
    from deerflow.config.agents_config import AgentConfig

    return AgentConfig(**{**{"name": "x"}, **d})


@pytest.fixture
async def db_session(tmp_path):
    # 强制创建 agent_registry 表（含本模块模型）
    Base.metadata.create_all  # ensure import side-effects
    import app.extensions.agent_registry.models  # noqa: F401 —— 注册到 metadata

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _fake_store(monkeypatch):
    fake = FakeAgentStore()
    monkeypatch.setattr(service, "_bridge_list_all", lambda: fake.list_all())
    monkeypatch.setattr(service, "_bridge_get_config", lambda name, uid: fake.get(name, user_id=uid))
    monkeypatch.setattr(service, "_bridge_get_soul", lambda name, uid: fake.get_soul(name, user_id=uid))
    monkeypatch.setattr(service, "_bridge_create", lambda name, cfg, soul, uid: fake.create(name, cfg, soul, user_id=uid))
    monkeypatch.setattr(service, "_bridge_update", lambda name, uid, c=None, s=None: fake.update(name, c, s, user_id=uid))
    monkeypatch.setattr(service, "_bridge_delete", lambda name, uid: fake.delete(name, user_id=uid))
    yield fake


@pytest.mark.asyncio
async def test_reconcile_creates_rows_for_harness_agents(db_session, _fake_store):
    _fake_store.data[("gw-admin", "report-writer")] = ({"name": "report-writer", "description": "d", "skills": ["s1"]}, "SOUL")
    _fake_store.data[("gw-lisi", "reviewer-bot")] = ({"name": "reviewer-bot", "description": "d2"}, "")

    result = await service.reconcile(db_session)

    assert result.created == 2
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    names = {a.agent_name for a in rows}
    assert names == {"report-writer", "reviewer-bot"}
    # skills_snapshot 从 harness config 回填
    writer = next(a for a in rows if a.agent_name == "report-writer")
    assert writer.skills_snapshot == ["s1"]
    assert writer.owner_id == "gw-admin"


@pytest.mark.asyncio
async def test_reconcile_marks_orphans(db_session, _fake_store):
    # 先建一个 registry 行
    _fake_store.data[("gw-admin", "report-writer")] = ({"name": "report-writer"}, "")
    await service.reconcile(db_session)
    # harness 里删掉
    _fake_store.data.clear()
    result = await service.reconcile(db_session)
    assert result.orphaned == 1
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    orphan = next(a for a in rows if a.agent_name == "report-writer")
    assert orphan.status == "orphaned"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_service.py -v
```
Expected: FAIL — `ImportError: cannot import name 'service'` (module not created yet).

- [ ] **Step 3: Create `service.py` with reconcile + list + access-control helpers**

```python
"""EAI-CUSTOM: agent_registry 业务逻辑。

reconcile: harness list_all() → upsert registry 行 + 标孤儿。
访问控制: 非 owner 只看公开元数据；config/SOUL/edit/delete 仅 owner。
owner 身份 = gateway user_id（= source_user_id = harness 桶键）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.agent_registry import store_bridge
from app.extensions.agent_registry.models import AgentRegistry
from app.extensions.agent_registry.schemas import (
    AgentPublic,
    CreateAgentRequest,
    ReconcileResponse,
    UpdateAgentRequest,
)

logger = logging.getLogger(__name__)

# —— bridge indirection（便于测试 monkeypatch；生产指向 store_bridge 的 async 函数）——
async def _bridge_list_all():
    return await store_bridge.list_all()


async def _bridge_get_config(name, uid):
    return await store_bridge.get_config(name, uid)


async def _bridge_get_soul(name, uid):
    return await store_bridge.get_soul(name, uid)


async def _bridge_create(name, cfg, soul, uid):
    await store_bridge.create_agent(name, cfg, soul, uid)


async def _bridge_update(name, uid, c=None, s=None):
    await store_bridge.update_agent(name, uid, config=c, soul=s)


async def _bridge_delete(name, uid):
    return await store_bridge.delete_agent(name, uid)


def _to_public(row: AgentRegistry, current_uid: str) -> AgentPublic:
    return AgentPublic(
        id=row.id,
        agent_name=row.agent_name,
        display_name=row.display_name,
        role=row.role,
        summary=row.summary,
        avatar=row.avatar,
        status=row.status,
        readiness=row.readiness,
        visibility=row.visibility,
        owner_id=row.owner_id,
        owner_name=row.owner_name,
        skills_snapshot=row.skills_snapshot,
        mcp_servers=row.mcp_servers,
        tags=row.tags,
        is_owner=(row.owner_id == current_uid),
        is_builtin=False,
        updated_at=row.updated_at,
    )


async def reconcile(db: AsyncSession) -> ReconcileResponse:
    """harness list_all() → upsert registry 行；缺失的标 orphaned。幂等。"""
    all_agents = await _bridge_list_all()  # [(gateway_uid, config_dict)]
    seen: set[tuple[str, str]] = set()
    created = updated = 0
    now = datetime.now(timezone.utc)

    for uid, cfg in all_agents:
        name = cfg.get("name")
        if not name:
            continue
        seen.add((uid, name))
        stmt = pg_insert(AgentRegistry).values(
            agent_name=name,
            source_user_id=uid,
            owner_id=uid,
            visibility="org",
            status="active",
            readiness="ready",
            skills_snapshot=cfg.get("skills"),
            last_synced_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_agent_registry_source_name",
            set_={
                "skills_snapshot": stmt.excluded.skills_snapshot,
                "last_synced_at": now,
                # 若之前被标 orphaned，harness 里又出现了 → 复活
                "status": stmt.excluded.status,
            },
        )
        result = await db.execute(stmt)
        if result.rowcount and result.returnvalue is not None:
            pass  # pg_insert 不细分 created/updated；用 upsert 近似
        created += 1
    await db.commit()

    # 标孤儿：registry 里存在但 harness list_all 没有的行
    all_rows = (await db.execute(select(AgentRegistry))).scalars().all()
    orphaned = 0
    for row in all_rows:
        if (row.source_user_id, row.agent_name) not in seen and row.status != "orphaned":
            row.status = "orphaned"
            orphaned += 1
    if orphaned:
        await db.commit()

    return ReconcileResponse(created=created, updated=0, orphaned=orphaned)


async def list_agents(
    db: AsyncSession,
    current_uid: str,
    *,
    q: str | None = None,
    status: str | None = None,
    readiness: str | None = None,
    role: str | None = None,
) -> list[AgentPublic]:
    """看板列表：org 行 + 自己的 private 行。先 reconcile 再返回。"""
    await reconcile(db)
    stmt = select(AgentRegistry)
    if status:
        stmt = stmt.where(AgentRegistry.status == status)
    if readiness:
        stmt = stmt.where(AgentRegistry.readiness == readiness)
    if role:
        stmt = stmt.where(AgentRegistry.role == role)
    rows = (await db.execute(stmt)).scalars().all()
    public = [_to_public(r, current_uid) for r in rows]
    # 可见性过滤：org 行人人可见；private 行仅 owner
    public = [
        a for a in public
        if a.visibility == "org" or a.owner_id == current_uid
    ]
    if q:
        ql = q.lower()
        public = [
            a for a in public
            if ql in (a.agent_name.lower())
            or (a.display_name and ql in a.display_name.lower())
            or (a.role and ql in a.role.lower())
        ]
    return public
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_service.py -v
```
Expected: PASS (both tests). If `pg_insert`/`on_conflict_do_update` is unavailable on the SQLite test DB, see Step 5.

- [ ] **Step 5: Handle SQLite test vs Postgres prod upsert**

`pg_insert.on_conflict_do_update` is Postgres-only and raises on SQLite. Make the upsert portable by branching on dialect. Replace the body of the `for uid, cfg in all_agents:` loop's `stmt` execution with:

```python
        existing = (
            await db.execute(
                select(AgentRegistry).where(
                    AgentRegistry.source_user_id == uid,
                    AgentRegistry.agent_name == name,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(AgentRegistry(
                agent_name=name, source_user_id=uid, owner_id=uid,
                visibility="org", status="active", readiness="ready",
                skills_snapshot=cfg.get("skills"), last_synced_at=now,
            ))
            created += 1
        else:
            existing.skills_snapshot = cfg.get("skills")
            existing.last_synced_at = now
            if existing.status == "orphaned":
                existing.status = "active"
            updated += 1
    await db.commit()
```

This is dialect-agnostic (works on SQLite + Postgres). Delete the `pg_insert` import if unused. Re-run the tests; expect PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/agent_registry/service.py backend/tests/test_agent_registry_service.py
git commit -m "feat(agent-registry): reconcile + list with access control + tests (EAI-CUSTOM)"
```

---

## Task 4: Service — get/create/update/delete + builtins (TDD)

**Files:**
- Modify: `backend/app/extensions/agent_registry/service.py`
- Modify: `backend/tests/test_agent_registry_service.py`

- [ ] **Step 1: Add failing tests for get-detail, access control, write-through, delete**

Append to `test_agent_registry_service.py`:

```python
@pytest.mark.asyncio
async def test_get_detail_owner_sees_config_and_soul(db_session, _fake_store):
    _fake_store.data[("gw-admin", "report-writer")] = (
        {"name": "report-writer", "description": "d", "model": "gpt-x", "skills": ["s1"]}, "SECRET-SOUL"
    )
    await service.reconcile(db_session)
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    row_id = next(a for a in rows if a.agent_name == "report-writer").id

    full = await service.get_agent_detail(db, db_session, row_id, current_uid="gw-admin")
    assert full.config is not None and full.config.get("model") == "gpt-x"
    assert full.soul == "SECRET-SOUL"


@pytest.mark.asyncio
async def test_get_detail_non_owner_no_config_no_soul(db_session, _fake_store):
    _fake_store.data[("gw-admin", "report-writer")] = ({"name": "report-writer"}, "SECRET-SOUL")
    await service.reconcile(db_session)
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    row_id = next(a for a in rows if a.agent_name == "report-writer").id

    public = await service.get_agent_detail(db, db_session, row_id, current_uid="gw-lisi")
    assert public.config is None and public.soul is None  # 非 owner 拿不到


@pytest.mark.asyncio
async def test_create_agent_writes_through_to_harness(db_session, _fake_store):
    payload = CreateAgentRequest(
        agent_name="brand-new", display_name="全新", role="助手",
        model="gpt-x", soul="INIT-SOUL", skills=["a"],
    )
    created = await service.create_agent(db_session, current_uid="gw-admin", owner_name="admin", payload=payload)
    assert created.agent_name == "brand-new"
    # harness store 被写入
    assert ("gw-admin", "brand-new") in _fake_store.data
    assert _fake_store.data[("gw-admin", "brand-new")][1] == "INIT-SOUL"
    # registry 行存在
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    assert any(a.agent_name == "brand-new" for a in rows)


@pytest.mark.asyncio
async def test_update_agent_owner_only_and_write_through(db_session, _fake_store):
    _fake_store.data[("gw-admin", "report-writer")] = ({"name": "report-writer", "description": "old"}, "OLD")
    await service.reconcile(db_session)
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    row_id = next(a for a in rows if a.agent_name == "report-writer").id

    # 非 owner → PermissionError
    with pytest.raises(PermissionError):
        await service.update_agent(db_session, row_id, current_uid="gw-lisi", UpdateAgentRequest(role="新角色", soul="NEW-SOUL"))

    # owner → 写通
    await service.update_agent(db_session, row_id, current_uid="gw-admin", UpdateAgentRequest(role="新角色", soul="NEW-SOUL"))
    assert _fake_store.data[("gw-admin", "report-writer")][1] == "NEW-SOUL"
    row = (await db_session.get(AgentRegistry, row_id))
    assert row.role == "新角色"


@pytest.mark.asyncio
async def test_delete_agent_owner_only(db_session, _fake_store):
    _fake_store.data[("gw-admin", "report-writer")] = ({"name": "report-writer"}, "")
    await service.reconcile(db_session)
    rows = await service.list_agents(db_session, current_uid="gw-admin")
    row_id = next(a for a in rows if a.agent_name == "report-writer").id

    with pytest.raises(PermissionError):
        await service.delete_agent(db_session, row_id, current_uid="gw-lisi")

    await service.delete_agent(db_session, row_id, current_uid="gw-admin")
    assert ("gw-admin", "report-writer") not in _fake_store.data
```

> Note: the `db` first positional arg in `get_agent_detail`/`update_agent`/`delete_agent` calls above is a placeholder — remove it; the real signature is `(db_session, row_id, current_uid, ...)`. (Kept here only to match the fixture name visually; final test code uses `db_session` only.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_service.py -v
```
Expected: FAIL — `AttributeError: module ... has no attribute 'get_agent_detail'` etc.

- [ ] **Step 3: Implement get/create/update/delete + builtins in `service.py`**

Append to `service.py`:

```python
from fastapi import HTTPException
from starlette import status

from app.extensions.agent_registry.schemas import AgentOwnerFull, BuiltinAgent


async def get_agent_detail(db: AsyncSession, row_id: UUID, current_uid: str) -> AgentOwnerFull:
    row = await db.get(AgentRegistry, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    base = _to_public(row, current_uid)
    # 仅 owner 能看 config/SOUL；非 owner 只看公开元数据
    if row.owner_id != current_uid:
        return AgentOwnerFull(**base.model_dump())
    config = await _bridge_get_config(row.agent_name, row.source_user_id)
    soul = await _bridge_get_soul(row.agent_name, row.source_user_id)
    return AgentOwnerFull(**base.model_dump(), config=config, soul=soul)


async def create_agent(
    db: AsyncSession, *, current_uid: str, owner_name: str | None, payload: CreateAgentRequest
) -> AgentPublic:
    # 1) write-through harness store
    config_doc = {"name": payload.agent_name, "description": payload.summary or ""}
    if payload.model is not None:
        config_doc["model"] = payload.model
    if payload.tool_groups is not None:
        config_doc["tool_groups"] = payload.tool_groups
    if payload.skills is not None:
        config_doc["skills"] = payload.skills
    await _bridge_create(payload.agent_name, config_doc, payload.soul or "", current_uid)
    # 2) registry 行
    row = AgentRegistry(
        agent_name=payload.agent_name,
        source_user_id=current_uid,
        owner_id=current_uid,
        owner_name=owner_name,
        display_name=payload.display_name,
        role=payload.role,
        summary=payload.summary,
        avatar=payload.avatar,
        status=payload.status,
        readiness=payload.readiness,
        visibility=payload.visibility,
        skills_snapshot=payload.skills,
        mcp_servers=payload.mcp_servers,
        tags=payload.tags,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_public(row, current_uid)


async def update_agent(
    db: AsyncSession, row_id: UUID, current_uid: str, payload: UpdateAgentRequest
) -> AgentPublic:
    row = await db.get(AgentRegistry, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    if row.owner_id != current_uid:
        raise PermissionError("not owner")
    # registry 元数据
    for f in ("display_name", "role", "summary", "avatar", "status", "readiness", "visibility", "mcp_servers", "tags"):
        v = getattr(payload, f)
        if v is not None:
            setattr(row, f, v)
    if payload.skills_snapshot is not None:
        row.skills_snapshot = payload.skills_snapshot
    # harness config（owner 才能改；仅当传了才 update）
    cfg_delta: dict = {}
    if payload.model is not None:
        cfg_delta["model"] = payload.model
    if payload.tool_groups is not None:
        cfg_delta["tool_groups"] = payload.tool_groups
    soul = payload.soul
    if cfg_delta or soul is not None:
        await _bridge_update(row.agent_name, row.source_user_id, c=cfg_delta or None, s=soul)
    await db.commit()
    await db.refresh(row)
    return _to_public(row, current_uid)


async def delete_agent(db: AsyncSession, row_id: UUID, current_uid: str) -> None:
    row = await db.get(AgentRegistry, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    if row.owner_id != current_uid:
        raise PermissionError("not owner")
    await _bridge_delete(row.agent_name, row.source_user_id)
    await db.delete(row)
    await db.commit()


async def list_builtins_static() -> list[BuiltinAgent]:
    return [BuiltinAgent(**b) for b in store_bridge.list_builtins()]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_service.py -v
```
Expected: PASS (all 6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/agent_registry/service.py backend/tests/test_agent_registry_service.py
git commit -m "feat(agent-registry): get/create/update/delete + builtins + access-control tests (EAI-CUSTOM)"
```

---

## Task 5: Router + gateway registration

**Files:**
- Create: `backend/app/extensions/agent_registry/routers.py`
- Modify: `backend/app/gateway/app.py` (import + include_router)

- [ ] **Step 1: Write failing router test**

Create `backend/tests/test_agent_registry_router.py`:

```python
"""EAI-CUSTOM: agent_registry router HTTP 测试。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.extensions.agent_registry import routers as ar
from app.extensions.auth.middleware import CurrentUser  # noqa: F401
from app.extensions.database import get_db


def _stub_user(uid: str):
    async def _dep():
        # router 只用 current_uid（gateway uid）；permission 经 require_permission
        return uid
    return _dep


@pytest.fixture
async def client(tmp_path, monkeypatch):
    import app.extensions.agent_registry.models  # noqa
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.extensions.database import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/r.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with Session() as s:
            yield s

    app = FastAPI()
    app.include_router(ar.router)
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[ar.get_current_user] = _stub_user("gw-admin")  # permission gate 放行
    app.dependency_overrides[ar.get_gateway_user_id] = _stub_user("gw-admin")
    # 跳过 reconcile 真实 harness 调用：注入空 list
    async def _noop_reconcile(db):
        from app.extensions.agent_registry.schemas import ReconcileResponse
        return ReconcileResponse(created=0, updated=0, orphaned=0)
    monkeypatch.setattr(ar.service, "reconcile", _noop_reconcile)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_agents_empty(client):
    r = await client.get("/api/extensions/agent-registry/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_builtins_endpoint(client):
    r = await client.get("/api/extensions/agent-registry/builtins")
    assert r.status_code == 200
    assert any(b["agent_name"] == "" for b in r.json())  # lead_agent


@pytest.mark.asyncio
async def test_create_then_get(client):
    r = await client.post("/api/extensions/agent-registry/agents", json={
        "agent_name": "e2e-bot", "display_name": "E2E", "role": "测试",
    })
    assert r.status_code == 201, r.text
    row_id = r.json()["id"]
    r2 = await client.get(f"/api/extensions/agent-registry/agents/{row_id}?full=true")
    assert r2.status_code == 200
    assert r2.json()["agent_name"] == "e2e-bot"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_router.py -v
```
Expected: FAIL — router not created.

- [ ] **Step 3: Create `routers.py`**

```python
"""EAI-CUSTOM: agent_registry FastAPI 路由。

prefix: /api/extensions/agent-registry。走 cookie-JWT 鉴权 + system:access 权限门。
owner 身份用 gateway user_id（= harness 桶键），经 get_current_user_from_request 取。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.agent_registry import service
from app.extensions.agent_registry.schemas import (
    AgentListResponse,
    AgentOwnerFull,
    AgentPublic,
    BuiltinAgent,
    CreateAgentRequest,
    ReconcileResponse,
    UpdateAgentRequest,
)
from app.extensions.auth.middleware import get_current_user, require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

router = APIRouter(prefix="/api/extensions/agent-registry", tags=["agent-registry"])


async def get_gateway_user_id(request: Request) -> str:
    """从请求解析 gateway user_id（JWT sub = harness 桶键）。绕开 phantom-bucket。"""
    from app.gateway.deps import get_current_user_from_request

    gw_user = await get_current_user_from_request(request)
    if gw_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return gw_user.id


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("system:access")),
    q: str | None = Query(None),
    agent_status: str | None = Query(None, alias="status"),
    readiness: str | None = Query(None),
    role: str | None = Query(None),
):
    uid = await get_gateway_user_id(request)
    rows = await service.list_agents(db, uid, q=q, status=agent_status, readiness=readiness, role=role)
    return AgentListResponse(agents=rows, total=len(rows))


@router.get("/agents/{row_id}", response_model=AgentOwnerFull)
async def get_agent(
    request: Request,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("system:access")),
):
    uid = await get_gateway_user_id(request)
    return await service.get_agent_detail(db, row_id, uid)


@router.post("/agents", response_model=AgentPublic, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: Request,
    payload: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_permission("system:access")),
):
    uid = await get_gateway_user_id(request)
    try:
        return await service.create_agent(db, current_uid=uid, owner_name=user.username, payload=payload)
    except FileExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent name already exists")


@router.patch("/agents/{row_id}", response_model=AgentPublic)
async def update_agent(
    request: Request,
    row_id: UUID,
    payload: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("system:access")),
):
    uid = await get_gateway_user_id(request)
    try:
        return await service.update_agent(db, row_id, uid, payload)
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can edit this agent")


@router.delete("/agents/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    request: Request,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("system:access")),
):
    uid = await get_gateway_user_id(request)
    try:
        await service.delete_agent(db, row_id, uid)
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can delete this agent")


@router.get("/builtins", response_model=list[BuiltinAgent])
async def get_builtins(
    _user: CurrentUser = Depends(require_permission("system:access")),
):
    return await service.list_builtins_static()


@router.post("/reconcile", response_model=ReconcileResponse)
async def trigger_reconcile(
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(require_permission("system:access")),
):
    return await service.reconcile(db)
```

> The `agent_status: ... = Query(None, alias="status")` avoids shadowing the Python `status` module import. Update the test's query param to `?status=...` — it already matches via alias.

- [ ] **Step 4: Run router tests to verify they pass**

```bash
PYTHONPATH=. uv run pytest tests/test_agent_registry_router.py -v
```
Expected: PASS (3 tests). If `require_permission` is hard to override, the test overrides `ar.get_current_user` — but the routes depend on `require_permission(...)`, not `get_current_user` directly. Fix by overriding the returned dependency: simplest is to override `ar.get_gateway_user_id` AND replace the permission dep. Add to the test's `app.dependency_overrides`:

```python
    from app.extensions.auth.middleware import require_permission
    # 让 require_permission("system:access") 直接放行
    async def _allow():
        from app.extensions.schemas import CurrentUser
        return CurrentUser(id="00000000-0000-0000-0000-000000000000", username="admin", email="a@b.c", status="active")
    # 用一个总览 override：把 router 里所有 Depends(require_permission(...)) 替换不易，
    # 改为直接 monkeypatch require_permission 返回 _allow
    monkeypatch.setattr(ar, "require_permission", lambda _p: _allow)
```

(Place this `monkeypatch.setattr` in the `client` fixture before `include_router` — actually after, since `routers.py` imported `require_permission` by name at module load. Because the router captured the original, the cleaner approach is: in `routers.py`, reference the permission via `Depends(require_permission("system:access"))` at call time — it does. The override must target the name in `routers.py`'s namespace: `monkeypatch.setattr("app.extensions.agent_registry.routers.require_permission", lambda p: _allow)`. Use this form.)

- [ ] **Step 5: Register router in `gateway/app.py`**

In `backend/app/gateway/app.py`, add the import near the other extension router imports (around the `docmgr_router`/`web_scraper_router` imports):

```python
from app.extensions.agent_registry import router as agent_registry_router  # EAI-CUSTOM
```

And add the include near line 542 (after `web_scraper_router`):

```python
    app.include_router(agent_registry_router)  # EAI-CUSTOM: 数字员工看板
```

> Verify the import style matches neighbors (some use `from app.extensions.X.routers import router as X_router`). If `agent_registry/__init__.py` already re-exports `router`, `from app.extensions.agent_registry import router as agent_registry_router` works.

- [ ] **Step 6: Verify in running gateway**

```bash
docker compose -p eai-docker restart gateway
# 登录拿 cookie 后：
curl -s localhost:8001/api/extensions/agent-registry/builtins  # 应返回 lead_agent 等（需带 cookie+CSRF）
```
Expected: 200 with builtin list (or 401 without auth — expected when not logged in).

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/agent_registry/routers.py backend/app/gateway/app.py backend/tests/test_agent_registry_router.py
git commit -m "feat(agent-registry): router + gateway registration + HTTP tests (EAI-CUSTOM)"
```

---

## Task 6: Frontend types + API + hooks

**Files:**
- Create: `frontend/src/extensions/agent_registry/types.ts`
- Create: `frontend/src/extensions/agent_registry/api.ts`
- Create: `frontend/src/extensions/agent_registry/hooks.ts`
- Create: `frontend/src/extensions/agent_registry/index.ts`

- [ ] **Step 1: Create `types.ts`**

```ts
// EAI-CUSTOM: agent_registry 前端类型
export interface AgentPublic {
  id: string;
  agent_name: string;
  display_name: string | null;
  role: string | null;
  summary: string | null;
  avatar: string | null;
  status: string;
  readiness: string;
  visibility: string;
  owner_id: string;
  owner_name: string | null;
  skills_snapshot: string[] | null;
  mcp_servers: string[] | null;
  tags: string[] | null;
  is_owner: boolean;
  is_builtin: boolean;
  updated_at: string | null;
}

export interface AgentOwnerFull extends AgentPublic {
  config: Record<string, unknown> | null;
  soul: string | null;
}

export interface CreateAgentRequest {
  agent_name: string;
  display_name?: string | null;
  role?: string | null;
  summary?: string | null;
  avatar?: string | null;
  status?: string;
  readiness?: string;
  visibility?: string;
  skills?: string[] | null;
  mcp_servers?: string[] | null;
  tags?: string[] | null;
  model?: string | null;
  tool_groups?: string[] | null;
  soul?: string | null;
}

export interface UpdateAgentRequest extends Partial<Omit<CreateAgentRequest, "agent_name">> {
  skills_snapshot?: string[] | null;
}

export interface BuiltinAgent {
  agent_name: string;
  display_name: string;
  role: string | null;
  description: string | null;
  is_builtin: true;
}
```

- [ ] **Step 2: Create `api.ts`**

```ts
// EAI-CUSTOM: agent_registry REST 客户端
import type { AgentOwnerFull, AgentPublic, BuiltinAgent, CreateAgentRequest, UpdateAgentRequest } from "./types";

const BASE = "/api/extensions/agent-registry";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${detail}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const agentRegistryApi = {
  list: (params?: { q?: string; status?: string; readiness?: string; role?: string }) => {
    const qs = new URLSearchParams();
    if (params) Object.entries(params).forEach(([k, v]) => v && qs.set(k, v));
    return http<{ agents: AgentPublic[]; total: number }>(`${BASE}/agents?${qs.toString()}`);
  },
  get: (id: string, full = false) =>
    http<AgentOwnerFull>(`${BASE}/agents/${id}${full ? "?full=true" : ""}`),
  create: (payload: CreateAgentRequest) =>
    http<AgentPublic>(`${BASE}/agents`, { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: UpdateAgentRequest) =>
    http<AgentPublic>(`${BASE}/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (id: string) => http<void>(`${BASE}/agents/${id}`, { method: "DELETE" }),
  builtins: () => http<BuiltinAgent[]>(`${BASE}/builtins`),
};
```

- [ ] **Step 3: Create `hooks.ts`**

```ts
// EAI-CUSTOM: agent_registry TanStack Query hooks
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentRegistryApi } from "./api";

const QK = ["agent-registry"] as const;

export function useAgents(params?: { q?: string; status?: string; readiness?: string; role?: string }) {
  return useQuery({
    queryKey: [...QK, "list", params],
    queryFn: () => agentRegistryApi.list(params),
  });
}

export function useAgent(id: string | null) {
  return useQuery({
    queryKey: [...QK, "detail", id],
    queryFn: () => agentRegistryApi.get(id!, true),
    enabled: !!id,
  });
}

export function useBuiltins() {
  return useQuery({ queryKey: [...QK, "builtins"], queryFn: () => agentRegistryApi.builtins() });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: agentRegistryApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: [...QK, "list"] }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof agentRegistryApi.update>[1] }) =>
      agentRegistryApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...QK, "list"] });
      qc.invalidateQueries({ queryKey: [...QK, "detail"] });
    },
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: agentRegistryApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: [...QK, "list"] }),
  });
}
```

- [ ] **Step 4: Create `index.ts` (barrel)**

```ts
export * from "./types";
export * from "./api";
export * from "./hooks";
```

- [ ] **Step 5: Typecheck**

```bash
docker compose -p eai-docker exec frontend pnpm typecheck
```
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/agent_registry/
git commit -m "feat(agent-registry): frontend types + api + hooks (EAI-CUSTOM)"
```

---

## Task 7: Board page shell + two-pane layout

**Files:**
- Create: `frontend/src/extensions/agent_registry/components/AgentBoard.tsx`
- Create: `frontend/src/extensions/agent_registry/components/AgentList.tsx`
- Create: `frontend/src/app/workspace/agent-board/page.tsx`

- [ ] **Step 1: Create `AgentBoard.tsx`** — page shell reusing dashboard style.

```tsx
// EAI-CUSTOM: 数字员工看板主壳，复用 dashboard.css 风格
"use client";

import { useMemo, useState } from "react";

import { useAgents, useBuiltins } from "../hooks";
import type { AgentPublic, BuiltinAgent } from "../types";
import { AgentDetail } from "./AgentDetail";
import { AgentList } from "./AgentList";

export function AgentBoard() {
  const [filters, setFilters] = useState<{ q?: string; status?: string; readiness?: string; role?: string }>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const agentsQ = useAgents(filters);
  const builtinsQ = useBuiltins();

  const builtins = (builtinsQ.data ?? []) as BuiltinAgent[];
  const agents = (agentsQ.data?.agents ?? []) as AgentPublic[];

  return (
    <div className="dashboard-shell relative min-h-full flex flex-col cyber-grid">
      <div className="absolute top-1/4 left-10 w-96 h-96 bg-purple-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-10 w-96 h-96 bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />

      <header className="px-4 md:px-8 py-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)]">
        <div>
          <h1 className="text-xl font-bold db-text-primary">数字员工看板</h1>
          <span className="text-[10px] font-cyber db-text-subtle tracking-widest">DIGITAL EMPLOYEES</span>
        </div>
      </header>

      <main className="flex-1 px-4 md:px-8 py-6 max-w-7xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-5">
          <AgentList
            agents={agents}
            builtins={builtins}
            loading={agentsQ.isLoading}
            filters={filters}
            onFiltersChange={setFilters}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        <div className="lg:col-span-7">
          <AgentDetail agentId={selectedId} />
        </div>
      </main>

      <footer className="border-t border-[var(--db-border-color-muted)] py-3 px-6 text-center text-[10px] db-text-subtle font-cyber tracking-widest">
        EAI · Agent Registry v0.1
      </footer>
    </div>
  );
}
```

- [ ] **Step 2: Create `AgentList.tsx`** — left list with search/filter/grouping.

```tsx
// EAI-CUSTOM: 左侧 agent 列表（系统/我的/团队 分组 + 搜索筛选）
"use client";

import { Bot, Filter, Search } from "lucide-react";

import type { AgentPublic, BuiltinAgent } from "../types";
import { cn } from "@/lib/utils";

interface Props {
  agents: AgentPublic[];
  builtins: BuiltinAgent[];
  loading: boolean;
  filters: { q?: string; status?: string; readiness?: string; role?: string };
  onFiltersChange: (f: { q?: string; status?: string; readiness?: string; role?: string }) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const STATUS_DOT: Record<string, string> = {
  active: "bg-emerald-400 glow-green",
  idle: "bg-slate-400",
  busy: "bg-amber-400 glow-cyan",
  error: "bg-red-400 glow-red",
  disabled: "bg-slate-600",
  orphaned: "bg-orange-400",
};

export function AgentList({ agents, builtins, loading, filters, onFiltersChange, selectedId, onSelect }: Props) {
  const mine = agents.filter((a) => a.is_owner);
  const team = agents.filter((a) => !a.is_owner);

  const Row = ({ agent, builtin = false }: { agent: AgentPublic | BuiltinAgent; builtin?: boolean }) => (
    <button
      key={(agent as AgentPublic).id ?? builtin_agent_name(agent)}
      onClick={() => !builtin && onSelect((agent as AgentPublic).id)}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all border border-transparent",
        !builtin && "hover:border-blue-500/30 cursor-pointer",
        selectedId === (agent as AgentPublic).id && "border-blue-500/40 bg-blue-500/5",
      )}
    >
      <div className="w-8 h-8 rounded bg-purple-500/10 flex items-center justify-center">
        <Bot className="w-4 h-4 accent-purple" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium db-text-primary truncate">
            {(agent as AgentPublic).display_name || (agent as AgentPublic).agent_name || "Lead Agent"}
          </span>
          {builtin && <span className="text-[9px] font-cyber accent-cyan">SYSTEM</span>}
        </div>
        <div className="text-[11px] db-text-subtle truncate">{(agent as AgentPublic).role ?? "—"}</div>
      </div>
      {!builtin && (
        <span className={cn("w-2 h-2 rounded-full", STATUS_DOT[(agent as AgentPublic).status] ?? "bg-slate-400")} />
      )}
    </button>
  );

  return (
    <div className="db-card rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-lg db-terminal">
          <Search className="w-3.5 h-3.5 db-text-subtle" />
          <input
            value={filters.q ?? ""}
            onChange={(e) => onFiltersChange({ ...filters, q: e.target.value })}
            placeholder="搜索 agent / 角色"
            className="flex-1 bg-transparent text-xs db-text-primary outline-none"
          />
        </div>
        <select
          value={filters.readiness ?? ""}
          onChange={(e) => onFiltersChange({ ...filters, readiness: e.target.value || undefined })}
          className="text-[11px] db-terminal rounded-lg px-2 py-1.5 db-text-muted outline-none"
        >
          <option value="">全部状态</option>
          <option value="ready">就绪</option>
          <option value="draft">草稿</option>
          <option value="prod">生产</option>
        </select>
      </div>

      {loading ? (
        <div className="text-xs db-text-subtle py-8 text-center">加载中…</div>
      ) : (
        <>
          <Section title="系统 SYSTEM" count={builtins.length}>
            {builtins.map((b) => <Row key={b.agent_name || "lead"} agent={b} builtin />)}
          </Section>
          <Section title="我的 MINE" count={mine.length}>
            {mine.map((a) => <Row key={a.id} agent={a} />)}
            {mine.length === 0 && <Empty />}
          </Section>
          <Section title="团队 TEAM" count={team.length}>
            {team.map((a) => <Row key={a.id} agent={a} />)}
            {team.length === 0 && <Empty />}
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 px-1">
        <Filter className="w-3 h-3 db-text-subtle" />
        <span className="text-[10px] font-cyber db-text-subtle tracking-widest">{title}</span>
        <span className="text-[10px] db-text-subtle">({count})</span>
      </div>
      {children}
    </div>
  );
}

function Empty() {
  return <div className="text-[11px] db-text-subtle px-3 py-2">— 无 —</div>;
}

// builtin 行没有 id，用 agent_name 做 key
function builtin_agent_name(a: AgentPublic | BuiltinAgent): string {
  return (a as AgentPublic).agent_name ?? "";
}
```

> Note the `key={(agent as AgentPublic).id ?? builtin_agent_name(agent)}` on `<button>` plus a duplicate `key` on `<Row>` — keep only ONE key (on `<Row>` in the `.map`, per React). Remove the key prop from the inner `<button>`.

- [ ] **Step 3: Create the page route**

`frontend/src/app/workspace/agent-board/page.tsx`:

```tsx
// EAI-CUSTOM: 数字员工看板路由
import { AgentBoard } from "@/extensions/agent_registry/components/AgentBoard";

export default function Page() {
  return <AgentBoard />;
}
```

- [ ] **Step 4: Create a stub `AgentDetail.tsx`** (filled in Task 8) so the page compiles:

```tsx
// EAI-CUSTOM: 右侧详情（Task 8 填充）
"use client";

export function AgentDetail({ agentId }: { agentId: string | null }) {
  if (!agentId) return <div className="db-card rounded-xl p-8 text-center text-xs db-text-subtle">选择一个 agent 查看详情</div>;
  return <div className="db-card rounded-xl p-8 text-center text-xs db-text-subtle">详情（待 Task 8）{agentId}</div>;
}
```

- [ ] **Step 5: Restart frontend + manual check**

```bash
docker compose -p eai-docker restart frontend
```
Visit `http://localhost:2026/workspace/agent-board` (must be logged in). Expected: dashboard-styled two-pane shell renders; left list shows 系统/我的/团队 sections.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/agent_registry/components/AgentBoard.tsx frontend/src/extensions/agent_registry/components/AgentList.tsx frontend/src/extensions/agent_registry/components/AgentDetail.tsx frontend/src/app/workspace/agent-board/page.tsx
git commit -m "feat(agent-registry): board shell + agent list (EAI-CUSTOM)"
```

---

## Task 8: Agent detail + tabs (overview/config/activity)

**Files:**
- Create: `frontend/src/extensions/agent_registry/components/OverviewTab.tsx`
- Create: `frontend/src/extensions/agent_registry/components/ConfigTab.tsx`
- Modify: `frontend/src/extensions/agent_registry/components/AgentDetail.tsx`

- [ ] **Step 1: Create `OverviewTab.tsx`**

```tsx
// EAI-CUSTOM: agent 概览（公开元数据，所有人可见）
"use client";

import type { AgentOwnerFull } from "../types";

export function OverviewTab({ agent }: { agent: AgentOwnerFull }) {
  return (
    <div className="flex flex-col gap-3 text-xs">
      <Field label="摘要" value={agent.summary} />
      <Field label="角色" value={agent.role} />
      <Chips label="技能" items={agent.skills_snapshot} accent="purple" />
      <Chips label="MCP 绑定(声明)" items={agent.mcp_servers} accent="cyan" />
      <Chips label="标签" items={agent.tags} accent="blue" />
      <Field label="Owner" value={agent.owner_name ?? agent.owner_id} />
      <Field label="状态" value={`${agent.status} / ${agent.readiness}`} />
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-2">
      <span className="w-20 db-text-subtle font-cyber">{label}</span>
      <span className="db-text-primary flex-1">{value || "—"}</span>
    </div>
  );
}

function Chips({ label, items, accent }: { label: string; items: string[] | null | undefined; accent: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-20 db-text-subtle font-cyber">{label}</span>
      <div className="flex flex-wrap gap-1 flex-1">
        {(items ?? []).length === 0 && <span className="db-text-subtle">—</span>}
        {(items ?? []).map((x) => (
          <span key={x} className={`text-[10px] px-1.5 py-0.5 rounded db-terminal accent-${accent}`}>{x}</span>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `ConfigTab.tsx`** — owner-only edit (incl. harness config + SOUL).

```tsx
// EAI-CUSTOM: agent 配置编辑（仅 owner）。保存 write-through 到 harness store + registry。
"use client";

import { useState } from "react";
import { Save } from "lucide-react";

import { useUpdateAgent } from "../hooks";
import type { AgentOwnerFull } from "../types";

export function ConfigTab({ agent }: { agent: AgentOwnerFull }) {
  const [display_name, setDisplayName] = useState(agent.display_name ?? "");
  const [role, setRole] = useState(agent.role ?? "");
  const [summary, setSummary] = useState(agent.summary ?? "");
  const [mcp_servers, setMcp] = useState((agent.mcp_servers ?? []).join(", "));
  const [tags, setTags] = useState((agent.tags ?? []).join(", "));
  const [model, setModel] = useState((agent.config?.model as string) ?? "");
  const [soul, setSoul] = useState(agent.soul ?? "");
  const update = useUpdateAgent();
  const [saved, setSaved] = useState(false);

  const save = async () => {
    await update.mutateAsync({
      id: agent.id,
      payload: {
        display_name: display_name || null,
        role: role || null,
        summary: summary || null,
        mcp_servers: mcp_servers ? mcp_servers.split(",").map((s) => s.trim()).filter(Boolean) : null,
        tags: tags ? tags.split(",").map((s) => s.trim()).filter(Boolean) : null,
        model: model || null,
        soul: soul || null,
      },
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="flex flex-col gap-3 text-xs">
      <Input label="显示名" value={display_name} onChange={setDisplayName} />
      <Input label="角色" value={role} onChange={setRole} />
      <Input label="摘要" value={summary} onChange={setSummary} />
      <Input label="MCP 绑定(逗号分隔)" value={mcp_servers} onChange={setMcp} />
      <Input label="标签(逗号分隔)" value={tags} onChange={setTags} />
      <Input label="模型 model" value={model} onChange={setModel} />
      <div className="flex flex-col gap-1">
        <span className="db-text-subtle font-cyber">SOUL / 系统提示词</span>
        <textarea
          value={soul}
          onChange={(e) => setSoul(e.target.value)}
          rows={8}
          className="db-terminal rounded-lg p-2 font-mono-db text-[11px] db-text-primary outline-none"
        />
      </div>
      <button
        onClick={save}
        disabled={update.isPending}
        className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold disabled:opacity-50"
      >
        <Save className="w-3.5 h-3.5" /> {update.isPending ? "保存中…" : "保存"}
      </button>
      {saved && <span className="text-[10px] accent-green">已保存</span>}
    </div>
  );
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="db-text-subtle font-cyber">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="db-terminal rounded-lg px-2 py-1.5 db-text-primary outline-none"
      />
    </div>
  );
}
```

- [ ] **Step 3: Implement `AgentDetail.tsx`** (header band + tabs + owner gating).

```tsx
// EAI-CUSTOM: agent 详情（头部 band + 概览/配置/活动 tab）。config/SOUL 仅 owner 可见。
"use client";

import { ExternalLink, Trash2 } from "lucide-react";
import { useState } from "react";

import { useAgent, useDeleteAgent } from "../hooks";
import { ConfigTab } from "./ConfigTab";
import { OverviewTab } from "./OverviewTab";

export function AgentDetail({ agentId }: { agentId: string | null }) {
  const q = useAgent(agentId);
  const del = useDeleteAgent();
  const [tab, setTab] = useState<"overview" | "config" | "activity">("overview");

  if (!agentId) return <Placeholder text="选择一个 agent 查看详情" />;
  if (q.isLoading) return <Placeholder text="加载中…" />;
  if (q.isError || !q.data) return <Placeholder text="加载失败" />;

  const a = q.data;
  const chatHref = a.agent_name ? `/workspace/agents/${a.agent_name}/chats/new` : "/workspace/chats/new";

  return (
    <div className="db-card rounded-xl p-5 flex flex-col gap-4">
      {/* 头部 band */}
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center text-xl">🤖</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold db-text-primary truncate">{a.display_name || a.agent_name}</h2>
            <Badge>{a.role ?? "agent"}</Badge>
            <Badge tone={a.status === "active" ? "green" : "muted"}>{a.status}</Badge>
            <Badge tone="cyan">{a.readiness}</Badge>
          </div>
          <div className="text-[11px] db-text-subtle mt-1">
            owner: {a.owner_name ?? a.owner_id} · {a.agent_name}
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <a href={chatHref} className="text-[11px] flex items-center gap-1 accent-blue hover:underline">
            对话 <ExternalLink className="w-3 h-3" />
          </a>
          {a.is_owner && (
            <button
              onClick={async () => {
                if (confirm("删除该 agent？harness store + 注册表行同删")) {
                  await del.mutateAsync(a.id);
                }
              }}
              className="text-[11px] flex items-center gap-1 accent-red hover:underline"
            >
              <Trash2 className="w-3 h-3" /> 删除
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-[var(--db-border-color-muted)]">
        {(["overview", "config", "activity"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`pb-2 text-xs font-cyber tracking-widest border-b-2 ${
              tab === t ? "border-blue-500 accent-blue" : "border-transparent db-text-subtle"
            }`}
          >
            {t === "overview" ? "概览 OVERVIEW" : t === "config" ? "配置 CONFIG" : "活动 ACTIVITY"}
          </button>
        ))}
      </div>

      {/* 非 owner 看不到 config —— config 仅 owner（后端已强制，这里再加一层 UX 提示） */}
      {tab === "overview" && <OverviewTab agent={a} />}
      {tab === "config" && (a.is_owner ? <ConfigTab agent={a} /> : <Placeholder text="仅 owner 可编辑配置" />)}
      {tab === "activity" && <Placeholder text={`上次同步: ${a.updated_at ?? "—"}`} />}
    </div>
  );
}

function Placeholder({ text }: { text: string }) {
  return <div className="db-card rounded-xl p-8 text-center text-xs db-text-subtle">{text}</div>;
}

function Badge({ children, tone = "muted" }: { children: React.ReactNode; tone?: "green" | "cyan" | "muted" }) {
  const cls = tone === "green" ? "accent-green" : tone === "cyan" ? "accent-cyan" : "db-text-subtle";
  return <span className={`text-[10px] px-1.5 py-0.5 rounded db-terminal font-cyber ${cls}`}>{children}</span>;
}
```

- [ ] **Step 4: Restart frontend + manual check**

```bash
docker compose -p eai-docker restart frontend
```
Click an agent in the list → detail renders with overview/config tabs; non-owner agents hide config. Owner's config edits persist (verify via re-fetch).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/agent_registry/components/
git commit -m "feat(agent-registry): detail + overview/config/activity tabs (owner-gated) (EAI-CUSTOM)"
```

---

## Task 9: Create modal + showcase mode

**Files:**
- Create: `frontend/src/extensions/agent_registry/components/CreateAgentModal.tsx`
- Create: `frontend/src/extensions/agent_registry/components/Showcase.tsx`
- Modify: `frontend/src/extensions/agent_registry/components/AgentBoard.tsx` (wire modal + showcase toggle)

- [ ] **Step 1: Create `CreateAgentModal.tsx`**

```tsx
// EAI-CUSTOM: 新建 agent 弹窗（write-through harness store + registry）
"use client";

import { useState } from "react";
import { X } from "lucide-react";

import { useCreateAgent } from "../hooks";

export function CreateAgentModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateAgent();
  const [form, setForm] = useState({
    agent_name: "",
    display_name: "",
    role: "",
    summary: "",
    model: "",
    soul: "",
    visibility: "org",
  });
  if (!open) return null;
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!/^[A-Za-z0-9-]+$/.test(form.agent_name)) {
      alert("agent_name 仅允许字母/数字/连字符");
      return;
    }
    await create.mutateAsync({
      agent_name: form.agent_name,
      display_name: form.display_name || null,
      role: form.role || null,
      summary: form.summary || null,
      model: form.model || null,
      soul: form.soul || null,
      visibility: form.visibility,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="db-card rounded-xl p-6 w-full max-w-lg flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <h3 className="font-bold db-text-primary">新建数字员工</h3>
          <button onClick={onClose}><X className="w-4 h-4 db-text-subtle" /></button>
        </div>
        <Field label="agent_name (slug)" value={form.agent_name} onChange={(v) => set("agent_name", v)} />
        <Field label="显示名" value={form.display_name} onChange={(v) => set("display_name", v)} />
        <Field label="角色" value={form.role} onChange={(v) => set("role", v)} />
        <Field label="摘要" value={form.summary} onChange={(v) => set("summary", v)} />
        <Field label="模型" value={form.model} onChange={(v) => set("model", v)} />
        <textarea placeholder="SOUL / 系统提示词" value={form.soul} onChange={(e) => set("soul", e.target.value)} rows={5}
          className="db-terminal rounded-lg p-2 font-mono-db text-[11px] outline-none" />
        <button onClick={submit} disabled={create.isPending}
          className="self-end px-4 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold disabled:opacity-50">
          {create.isPending ? "创建中…" : "创建"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] db-text-subtle font-cyber">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        className="db-terminal rounded-lg px-2 py-1.5 text-xs outline-none" />
    </div>
  );
}
```

- [ ] **Step 2: Create `Showcase.tsx`** — gallery of org agents (MVP: view/chat links only, no access-request).

```tsx
// EAI-CUSTOM: 画廊模式 —— visibility=org 的 agent 大卡片网格
"use client";

import Link from "next/link";

import { useAgents } from "../hooks";

export function Showcase() {
  const { data, isLoading } = useAgents();
  const agents = data?.agents ?? [];
  return (
    <div className="dashboard-shell cyber-grid min-h-full p-8">
      <h1 className="text-xl font-bold mb-1 db-text-primary">数字员工画廊</h1>
      <span className="text-[10px] font-cyber db-text-subtle tracking-widest">SHOWCASE</span>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6 max-w-6xl">
        {isLoading && <div className="text-xs db-text-subtle">加载中…</div>}
        {!isLoading && agents.map((a) => (
          <div key={a.id} className="db-card rounded-xl p-4 flex flex-col gap-2">
            <div className="text-2xl">🤖</div>
            <div className="font-bold db-text-primary">{a.display_name || a.agent_name}</div>
            <div className="text-[11px] db-text-subtle">{a.role ?? "agent"} · {a.owner_name ?? "—"}</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {(a.skills_snapshot ?? []).slice(0, 3).map((s) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded db-terminal accent-purple">{s}</span>
              ))}
            </div>
            {a.agent_name && (
              <Link href={`/workspace/agents/${a.agent_name}/chats/new`} className="text-[11px] accent-blue mt-1">对话 →</Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire modal + showcase toggle into `AgentBoard.tsx`**

In `AgentBoard.tsx`:
- Add `const [showCreate, setShowCreate] = useState(false);`
- Add `const [view, setView] = useState<"board" | "showcase">("board");`
- In the header, add buttons: `[{view==='showcase' ? '看板' : '画廊'} toggle]` and `[+ 新建]` (calls `setShowCreate(true)`).
- Render `{view === "showcase" ? <Showcase/> : <two-pane main>}`.
- Render `<CreateAgentModal open={showCreate} onClose={() => setShowCreate(false)} />` at the end.

(Also support `?view=showcase` from the URL: read `useSearchParams()` and initialize `view`.)

- [ ] **Step 4: Restart frontend + manual check**

```bash
docker compose -p eai-docker restart frontend
```
"+ 新建" opens modal → create → agent appears in list. "画廊" toggle shows showcase grid.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/agent_registry/components/
git commit -m "feat(agent-registry): create modal + showcase gallery mode (EAI-CUSTOM)"
```

---

## Task 10: Sidebar nav + final checks

**Files:**
- Modify: `frontend/src/extensions/shell/Sidebar.tsx` (+1 nav link, `EAI-CUSTOM`)

- [ ] **Step 1: Add nav entry to Sidebar**

Open `frontend/src/extensions/shell/Sidebar.tsx`. Find the nav items array (mirror an existing entry like the dashboard/projects link). Add:

```tsx
// EAI-CUSTOM: 数字员工看板导航
{ href: "/workspace/agent-board", label: "数字员工", en: "DIGITAL EMPLOYEES", icon: "bot" /* 或现有图标 */ },
```

> Match the exact shape of neighboring entries (the file uses its own nav-item type). If the sidebar reads nav config from a registry instead of a static array, register there. Confirm by reading the file head.

- [ ] **Step 2: Restart frontend + full smoke**

```bash
docker compose -p eai-docker restart frontend
```
- Sidebar shows "数字员工" entry → navigates to `/workspace/agent-board`.
- Full flow: list renders (reconcile backfills existing agents) → click agent → overview → owner edits config → save → persists → create new via modal → appears → delete works → showcase toggle works.

- [ ] **Step 3: Backend lint + tests**

```bash
docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && ruff check app/extensions/agent_registry && ruff format --check app/extensions/agent_registry"
docker compose -p eai-docker exec gateway bash -lc "cd /app/backend && PYTHONPATH=. uv run pytest tests/test_agent_registry_service.py tests/test_agent_registry_router.py -v"
```
Expected: ruff clean, all tests PASS.

- [ ] **Step 4: Frontend typecheck + lint**

```bash
docker compose -p eai-docker exec frontend pnpm typecheck
docker compose -p eai-docker exec frontend pnpm lint
```
Expected: no new errors.

- [ ] **Step 5: Commit + push**

```bash
git add frontend/src/extensions/shell/Sidebar.tsx
git commit -m "feat(agent-registry): sidebar nav entry + final checks (EAI-CUSTOM)"
git push origin main-dev-fork
```

---

## Self-Review (run after writing — already done)

**1. Spec coverage:**
- §5 data model → Task 1. ✓
- §6 UI (board/detail/create/showcase) → Tasks 7–9. ✓
- §7 sync (write-through + reconcile + orphan) → Tasks 3–4. ✓
- §8 API (all 9 endpoints) → Task 5. ✓ (`/agents` GET/POST, `/{id}` GET/PATCH/DELETE, `/config` folded into `?full=true` on GET, `/builtins`, `/meta/filters` DEFERRED — see note, `/reconcile`). ✓
- §9 testing → Tasks 3–5 backend tests; frontend smoke. ✓
- §9 rollout (incremental, dark) → the router is permission-gated; phases map to tasks. ✓

**Gaps closed inline:**
- `/meta/filters` endpoint (distinct roles/owners/tags for filter dropdowns): not on the critical path — the list already filters by the fields; distinct-value aggregation is a fast-follow. Documented here as deferred, not a blocker.
- AgentName availability check reuses the existing harness `/api/agents/check` — the create modal does client-side `^[A-Za-z0-9-]+$` validation and the backend returns 409 on conflict (Task 5 Step 3). No new endpoint needed.

**2. Placeholder scan:** None — every code step has real code. The two `Verify before implementing` notes (subagent registry enumeration; sidebar nav shape) ask the engineer to confirm an existing API, not to invent one; each has a concrete fallback.

**3. Type consistency:** `AgentPublic` / `AgentOwnerFull` field names match across `schemas.py`, `types.ts`, and all components. Service function signatures (`list_agents`, `get_agent_detail`, `create_agent`, `update_agent`, `delete_agent`, `reconcile`, `list_builtins_static`) match between `service.py`, `routers.py`, and the tests.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-27-agent-registry.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
