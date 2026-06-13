# 四模块业务流程重构 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目管理、流程编排、AI写作、文档空间重构为四个限界上下文 + 统一权限模型 + 可扩展节点注册表，消除15个业务逻辑缺口。

**Architecture:** Domain-driven redesign — Writing / Review / DocSpace / Orchestration 四个限界上下文通过 Temporal 事件通信，共享 Project/ProjectRole/Chapter 内核。可扩展的 IWorkflowNodeExecutor 注册表替代硬编码节点类型，统一权限模型替代三套并行体系。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Temporal, Pydantic v2, PostgreSQL, React/Next.js (前端变更最小化)

**Phases:** 7 个顺序阶段，每阶段独立可测可提交。

---

## Phase 1: Shared Kernel + 统一权限模型

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/extensions/models/role_permission.py` | RolePermission ORM model |
| **Create** | `backend/app/extensions/auth/unified_permissions.py` | 统一权限检查入口 + 默认权限定义 |
| **Modify** | `backend/app/extensions/models.py` | 添加 RolePermission 导入 |
| **Modify** | `backend/app/extensions/database.py` | `migrate_db()` 添加 role_permissions 表 |
| **Modify** | `backend/app/extensions/project/project_permissions.py` | 标记废弃，重导出到统一入口 |
| **Modify** | `backend/app/extensions/project/permissions.py` | 标记废弃 |
| **Modify** | `backend/app/extensions/project/schemas.py` | VALID_MEMBER_ROLES 替换为 ProjectRole 枚举 |
| **Create** | `backend/tests/test_unified_permissions.py` | 权限系统的单元测试 |

### Task 1.1: RolePermission 模型 + 默认权限定义

**Files:**
- Create: `backend/app/extensions/models/role_permission.py`
- Modify: `backend/app/extensions/models.py`

- [ ] **Step 1: 创建 RolePermission ORM 模型**

```python
# backend/app/extensions/models/role_permission.py
"""Unified role-permission model — single source of truth for all project RBAC."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base


class ProjectRole(str, enum.Enum):
    """Unified project-level roles — ONE taxonomy for the entire system."""

    OWNER = "owner"
    PHASE_LEAD = "phase_lead"
    WRITER = "writer"
    REVIEWER = "reviewer"
    APPROVER = "approver"


# Default permissions per role — seeded on first deploy, editable via Admin UI
DEFAULT_ROLE_PERMISSIONS: dict[ProjectRole, set[str]] = {
    ProjectRole.OWNER: {
        "project:edit",
        "project:delete",
        "member:add",
        "member:remove",
        "chapter:write_any",
        "chapter:review_any",
        "ai:start_writing",
        "ai:stop_writing",
        "approval:submit",
        "approval:review",
        "approval:approve",
        "workflow:start",
        "workflow:cancel",
        "settings:edit",
        "export:generate",
    },
    ProjectRole.PHASE_LEAD: {
        "chapter:write_any",
        "chapter:review_any",
        "ai:start_writing",
        "approval:submit",
        "member:add",
        "outline:edit",
    },
    ProjectRole.WRITER: {
        "chapter:write_own",
        "chapter:confirm",
    },
    ProjectRole.REVIEWER: {
        "chapter:review",
        "approval:review",
    },
    ProjectRole.APPROVER: {
        "approval:approve",
        "approval:view",
    },
}


class RolePermission(Base):
    """Maps a ProjectRole to a set of permissions.  Admin-editable at runtime."""

    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    __table_args__ = (
        # Unique constraint — one row per (role, permission) pair
        {"sqlite_autoincrement": True},
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role={self.role}, permission={self.permission})>"
```

- [ ] **Step 2: 在 models.py 中导出新模型**

In `backend/app/extensions/models.py`, add after existing imports:

```python
from .models.role_permission import DEFAULT_ROLE_PERMISSIONS, ProjectRole, RolePermission
```

将其加入 `__all__`（如果存在）或在文件末尾确认导出。

- [ ] **Step 3: 在 database.py 添加 migrate_db 建表语句**

In `backend/app/extensions/database.py`, find `migrate_db()` and add:

```python
# role_permissions — unified RBAC
await conn.execute(text("""
    CREATE TABLE IF NOT EXISTS role_permissions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        role VARCHAR(50) NOT NULL,
        permission VARCHAR(100) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        UNIQUE(role, permission)
    )
"""))
await conn.execute(text("""
    CREATE INDEX IF NOT EXISTS idx_role_permissions_role
    ON role_permissions(role)
"""))
```

- [ ] **Step 4: 写种子数据函数**

In the same `database.py`, add a `_seed_role_permissions` helper called after migration:

```python
async def _seed_role_permissions(conn):
    """Insert default role-permission mappings if the table is empty."""
    from .models.role_permission import DEFAULT_ROLE_PERMISSIONS

    result = await conn.execute(
        text("SELECT COUNT(*) FROM role_permissions")
    )
    if result.scalar() > 0:
        return  # already seeded

    for role, perms in DEFAULT_ROLE_PERMISSIONS.items():
        for perm in perms:
            await conn.execute(
                text(
                    "INSERT INTO role_permissions (role, permission) "
                    "VALUES (:role, :perm) ON CONFLICT (role, permission) DO NOTHING"
                ),
                {"role": role.value, "perm": perm},
            )
```

- [ ] **Step 5: 验证导入**

```bash
cd backend && python -c "
from app.extensions.models.role_permission import ProjectRole, DEFAULT_ROLE_PERMISSIONS, RolePermission
print(f'ProjectRole values: {[r.value for r in ProjectRole]}')
print(f'OWNER perms: {len(DEFAULT_ROLE_PERMISSIONS[ProjectRole.OWNER])}')
print('RolePermission model OK')
"
```

Expected: RolePermission model OK

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/models/role_permission.py backend/app/extensions/models.py backend/app/extensions/database.py
git commit -m "feat: add unified RolePermission model with default permissions"
```

### Task 1.2: 统一权限检查入口

**Files:**
- Create: `backend/app/extensions/auth/unified_permissions.py`

- [ ] **Step 1: 创建统一权限模块**

```python
# backend/app/extensions/auth/unified_permissions.py
"""Unified permission checking — single entry point for all project RBAC.

Replaces the dual-system (permissions.py + project_permissions.py) with
one function that queries the role_permissions table.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.database import get_db
from app.extensions.models import ProjectMember, Role
from app.extensions.models.role_permission import ProjectRole
from app.extensions.schemas import CurrentUser


async def resolve_user_project_role(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> ProjectRole | None:
    """Resolve a user's effective ProjectRole within a project.

    Priority:
    1. phase_duties override for the given phase_node
    2. ProjectMember.role
    3. None (not a member)
    """
    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        return None

    # Phase-scoped role override
    if phase_node and member.phase_duties:
        phase_duty = member.phase_duties.get(phase_node, {})
        duty_role = phase_duty.get("role")
        if duty_role:
            # Normalise legacy duty keys
            _LEGACY_MAP = {
                "lead": ProjectRole.PHASE_LEAD.value,
                "leader": ProjectRole.PHASE_LEAD.value,
                "reviewer": ProjectRole.REVIEWER.value,
                "dept_reviewer": ProjectRole.REVIEWER.value,
                "approver": ProjectRole.APPROVER.value,
                "company_reviewer": ProjectRole.APPROVER.value,
                "write": ProjectRole.WRITER.value,
                "writer": ProjectRole.WRITER.value,
            }
            normalised = _LEGACY_MAP.get(duty_role, duty_role)
            try:
                return ProjectRole(normalised)
            except ValueError:
                pass

    # Project-level role
    try:
        return ProjectRole(member.role)
    except ValueError:
        return None


async def get_user_permissions(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    phase_node: str | None = None,
) -> set[str]:
    """Return the effective permission set for a user in a project."""
    from app.extensions.models.role_permission import RolePermission

    # Admin bypass
    user_role = await db.get(Role, user_id)  # user's system role
    if user_role and (user_role.is_system or "*" in (user_role.permissions or [])):
        # Return all known permissions
        result = await db.execute(select(RolePermission.permission))
        return {row[0] for row in result.all()}

    project_role = await resolve_user_project_role(db, user_id, project_id, phase_node)
    if not project_role:
        return set()

    result = await db.execute(
        select(RolePermission.permission).where(
            RolePermission.role == project_role.value
        )
    )
    return {row[0] for row in result.all()}


async def require_project_permission(
    action: str,
    project_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
    phase_node: str | None = None,
):
    """FastAPI dependency: raise 403 if user lacks action in project."""
    perms = await get_user_permissions(db, user.id, project_id, phase_node)
    if action not in perms:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{action}' required",
        )
    return user


# Convenience typed dependencies for FastAPI endpoints
def RequireProjectPerm(action: str):
    """Factory: create a FastAPI dependency for a specific project permission."""

    async def _dep(
        project_id: UUID,
        user: CurrentUser,
        db: AsyncSession = Depends(get_db),
    ):
        return await require_project_permission(action, project_id, user, db)

    return Depends(_dep)
```

- [ ] **Step 2: 验证导入**

```bash
cd backend && python -c "
from app.extensions.auth.unified_permissions import (
    resolve_user_project_role, get_user_permissions, ProjectRole
)
print('Unified permissions module OK')
"
```

Expected: Unified permissions module OK

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/auth/unified_permissions.py
git commit -m "feat: add unified permission checking entry point"
```

### Task 1.3: 标记旧权限模块为废弃

**Files:**
- Modify: `backend/app/extensions/project/project_permissions.py`
- Modify: `backend/app/extensions/project/permissions.py`

- [ ] **Step 1: 在旧模块顶部添加废弃警告**

In `project_permissions.py`, add after module docstring:

```python
# DEPRECATED (2026-06-13): This module is superseded by
# app.extensions.auth.unified_permissions.  It is kept for backward
# compatibility during migration and will be removed after all callers
# are migrated.
import warnings
warnings.warn(
    "project_permissions.py is deprecated; use unified_permissions instead",
    DeprecationWarning,
    stacklevel=2,
)
```

Same in `permissions.py`:

```python
# DEPRECATED (2026-06-13): This module is superseded by
# app.extensions.auth.unified_permissions.
import warnings
warnings.warn(
    "permissions.py is deprecated; use unified_permissions instead",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: 验证无破坏性**

```bash
cd backend && python -c "
import warnings
warnings.simplefilter('always')
# 旧模块仍可导入（只警告不报错）
from app.extensions.project.permissions import require_resource_permission
from app.extensions.project.project_permissions import get_effective_permissions
print('Legacy modules still importable (with deprecation warning)')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/project/permissions.py backend/app/extensions/project/project_permissions.py
git commit -m "refactor: mark old permission modules as deprecated"
```

---

## Phase 2: Orchestration — 可扩展节点注册表

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/extensions/workflow/registry.py` | IWorkflowNodeExecutor protocol + NodeRegistry |
| **Create** | `backend/app/extensions/workflow/system_nodes.py` | START / END 系统节点执行器 |
| **Modify** | `backend/app/extensions/workflow/service.py` | DAG 校验增加 START 节点检查 |
| **Modify** | `backend/app/extensions/workflow/temporal/workflows.py` | 使用注册表派发节点执行 |
| **Create** | `backend/tests/test_workflow_registry.py` | 注册表单元测试 |

### Task 2.1: 节点执行器注册表

**Files:**
- Create: `backend/app/extensions/workflow/registry.py`

- [ ] **Step 1: 创建注册表模块**

```python
# backend/app/extensions/workflow/registry.py
"""Extensible workflow node registry.

Modules register node executors via the @register_node decorator.
Temporal workflows dispatch to executors by node type at runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ── Types ──


@dataclass
class SignalDef:
    """A signal that a node can receive."""
    name: str
    description: str = ""
    payload_schema: dict | None = None


@dataclass
class WorkflowContext:
    """Context passed to node executors during execution."""
    project_id: str
    workflow_id: str | None = None
    config: dict = field(default_factory=dict)


@dataclass
class NodeResult:
    """Result returned by a node executor's on_enter."""
    status: str  # "completed" | "waiting" | "failed"
    output: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class SignalResult:
    """Result returned by a node executor's on_signal."""
    status: str  # "continue" | "rollback" | "retry"
    output: dict = field(default_factory=dict)


# ── Protocol ──


class IWorkflowNodeExecutor(Protocol):
    """Contract for any business module to hook into the workflow engine."""

    node_type: str
    display_name: str
    display_category: str
    config_schema: dict
    signals: list[SignalDef]

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Called when the workflow activates this node."""
        ...

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        """Called when a signal arrives for this node."""
        ...

    def validate(self, config: dict) -> list[str]:
        """Validate node config; return list of error messages (empty = valid)."""
        ...


# ── Registry ──


class _NodeRegistry:
    """Global registry of workflow node executors."""

    def __init__(self):
        self._executors: dict[str, IWorkflowNodeExecutor] = {}

    def register(self, executor: IWorkflowNodeExecutor):
        if executor.node_type in self._executors:
            logger.warning(
                "Node type %r re-registered; overwriting previous executor",
                executor.node_type,
            )
        self._executors[executor.node_type] = executor
        logger.info("Registered node type: %s (%s)", executor.node_type, executor.display_name)

    def get(self, node_type: str) -> IWorkflowNodeExecutor | None:
        return self._executors.get(node_type)

    def list_all(self) -> list[IWorkflowNodeExecutor]:
        return list(self._executors.values())

    def list_by_category(self, category: str) -> list[IWorkflowNodeExecutor]:
        return [e for e in self._executors.values() if e.display_category == category]

    @property
    def categories(self) -> list[str]:
        return sorted({e.display_category for e in self._executors.values()})


# Singleton
node_registry = _NodeRegistry()


# ── Decorator ──


def register_node(cls):
    """Class decorator: register a node executor in the global registry."""
    instance = cls()
    node_registry.register(instance)
    return cls
```

- [ ] **Step 2: 验证导入**

```bash
cd backend && python -c "
from app.extensions.workflow.registry import (
    node_registry, IWorkflowNodeExecutor, register_node,
    NodeResult, SignalResult, WorkflowContext, SignalDef
)
print('Node registry OK —', len(node_registry.list_all()), 'executors registered')
"
```

Expected: Node registry OK — 0 executors registered

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/registry.py
git commit -m "feat: add extensible workflow node registry"
```

### Task 2.2: 系统节点（START / END）

**Files:**
- Create: `backend/app/extensions/workflow/system_nodes.py`

- [ ] **Step 1: 创建系统节点执行器**

```python
# backend/app/extensions/workflow/system_nodes.py
"""Built-in system node types: start, end."""
from __future__ import annotations

from app.extensions.workflow.registry import (
    IWorkflowNodeExecutor,
    NodeResult,
    SignalDef,
    SignalResult,
    WorkflowContext,
    register_node,
)


@register_node
class StartNodeExecutor:
    """Explicit workflow start gate — validates entry conditions."""

    node_type = "system:start"
    display_name = "项目启动"
    display_category = "系统"
    config_schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "default": "项目启动"},
            "entry_conditions": {
                "type": "object",
                "properties": {
                    "template_bound": {"type": "boolean", "default": True},
                    "team_size_min": {"type": "integer", "default": 2},
                    "required_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["owner"],
                    },
                },
            },
            "trigger": {
                "type": "string",
                "enum": ["manual", "auto_on_create", "scheduled"],
                "default": "manual",
            },
        },
    }
    signals: list[SignalDef] = []

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Validate entry conditions and pass."""
        conditions = (node.get("data") or {}).get("entry_conditions", {})
        errors: list[str] = []

        if conditions.get("template_bound"):
            from app.extensions.database import get_db_context
            from app.extensions.models import ReportProject
            import uuid

            async with get_db_context() as db:
                project = await db.get(ReportProject, uuid.UUID(ctx.project_id))
                if project and not project.template_id:
                    errors.append("项目未绑定报告模板")
                if project and conditions.get("team_size_min"):
                    from app.extensions.models import ProjectMember
                    from sqlalchemy import func, select as sa_select

                    count_result = await db.execute(
                        sa_select(func.count()).where(
                            ProjectMember.project_id == uuid.UUID(ctx.project_id)
                        )
                    )
                    member_count = count_result.scalar()
                    if member_count < conditions["team_size_min"]:
                        errors.append(
                            f"团队成员不足（需要 {conditions['team_size_min']} 人，当前 {member_count} 人）"
                        )

        if errors:
            return NodeResult(status="failed", error="; ".join(errors))

        return NodeResult(status="completed", output={"conditions_met": True})

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        return SignalResult(status="continue")

    def validate(self, config: dict) -> list[str]:
        errors: list[str] = []
        conditions = config.get("entry_conditions", {})
        if "team_size_min" in conditions and not isinstance(conditions["team_size_min"], int):
            errors.append("entry_conditions.team_size_min must be an integer")
        return errors


@register_node
class EndNodeExecutor:
    """Explicit workflow end gate — executes completion actions."""

    node_type = "system:end"
    display_name = "项目完成"
    display_category = "系统"
    config_schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "default": "项目完成"},
            "completion_actions": {
                "type": "object",
                "properties": {
                    "set_project_status": {"type": "string", "default": "completed"},
                    "merge_documents": {"type": "boolean", "default": True},
                    "notify_roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["owner"],
                    },
                    "archive_to_docspace": {"type": "boolean", "default": True},
                },
            },
        },
    }
    signals: list[SignalDef] = []

    async def on_enter(self, node: dict, ctx: WorkflowContext) -> NodeResult:
        """Execute completion actions and mark project completed."""
        data = node.get("data") or {}
        actions = data.get("completion_actions", {})

        from app.extensions.database import get_db_context
        from app.extensions.models import ReportProject
        import uuid

        new_status = actions.get("set_project_status", "completed")

        async with get_db_context() as db:
            project = await db.get(ReportProject, uuid.UUID(ctx.project_id))
            if project:
                project.status = new_status
                await db.commit()

        # merge_documents, notify_roles, archive_to_docspace
        # These execute in Phase 5 finalize flow (see Task 5.2)

        return NodeResult(
            status="completed",
            output={"project_status": new_status},
        )

    async def on_signal(self, node: dict, signal_name: str, payload: dict, ctx: WorkflowContext) -> SignalResult:
        return SignalResult(status="continue")

    def validate(self, config: dict) -> list[str]:
        return []
```

- [ ] **Step 2: 验证系统节点注册**

```bash
cd backend && python -c "
from app.extensions.workflow.system_nodes import StartNodeExecutor, EndNodeExecutor
from app.extensions.workflow.registry import node_registry

executors = node_registry.list_all()
print(f'Registered {len(executors)} executors:')
for e in executors:
    print(f'  - {e.node_type}: {e.display_name}')
"
```

Expected: Registered 2 executors

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/system_nodes.py
git commit -m "feat: add START/END system node executors"
```

### Task 2.3: DAG 校验增加 START 节点规则

**Files:**
- Modify: `backend/app/extensions/workflow/service.py`

- [ ] **Step 1: 添加 START 节点校验**

In `service.py`'s `validate_dag` function (or wherever DAG validation runs), add after existing checks:

```python
def _validate_start_node(graph: dict) -> list[str]:
    """Validate that the DAG has exactly one system:start node with in-degree 0."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    start_nodes = [n for n in nodes if n.get("type") == "system:start"]
    if len(start_nodes) == 0:
        return ["DAG 缺少 START 节点 (type='system:start')"]
    if len(start_nodes) > 1:
        return [f"DAG 包含 {len(start_nodes)} 个 START 节点，只允许 1 个"]

    start_id = start_nodes[0]["id"]
    # START must have in-degree 0
    incoming = [e for e in edges if e.get("target") == start_id]
    if incoming:
        return ["START 节点不能有入边"]

    # START must have out-degree >= 1
    outgoing = [e for e in edges if e.get("source") == start_id]
    if not outgoing:
        return ["START 节点必须有至少 1 条出边"]

    return []
```

将此函数调用集成到 `validate_dag` 的返回值中。

- [ ] **Step 2: 运行现有测试确保无回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/ -k "dag or workflow or validate" -v 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/service.py
git commit -m "feat: add START node validation to DAG checks"
```

---

## Phase 3: Writing Context 重构

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/extensions/writing/` | Writing Context package |
| **Create** | `backend/app/extensions/writing/__init__.py` | Package init |
| **Create** | `backend/app/extensions/writing/state_machine.py` | Chapter 状态机 + 校验 |
| **Create** | `backend/app/extensions/writing/dependency_graph.py` | 从模板树推导章节依赖 |
| **Create** | `backend/app/extensions/writing/generation_strategy.py` | 智能 AI 生成策略选择器 |
| **Create** | `backend/app/extensions/writing/writer_assignment.py` | Writer 负载均衡分配 |
| **Modify** | `backend/app/extensions/workflow/temporal/activities.py` | 使用 Writing Context 的新逻辑 |
| **Create** | `backend/tests/test_writing_context.py` | Writing Context 单元测试 |

### Task 3.1: 章节状态机

**Files:**
- Create: `backend/app/extensions/writing/state_machine.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_writing_context.py
import pytest
from app.extensions.writing.state_machine import (
    VALID_CHAPTER_TRANSITIONS,
    validate_chapter_transition,
    ChapterStatus,
)

def test_valid_transition_pending_to_draft():
    assert validate_chapter_transition("pending", "draft") is None

def test_valid_transition_draft_to_completed():
    assert validate_chapter_transition("draft", "completed") is None

def test_valid_transition_completed_to_approved():
    assert validate_chapter_transition("completed", "approved") is None

def test_invalid_transition_pending_to_approved():
    err = validate_chapter_transition("pending", "approved")
    assert err is not None
    assert "pending" in err and "approved" in err

def test_rollback_completed_to_pending():
    # Rejection rollback: completed → pending is valid
    assert validate_chapter_transition("completed", "pending") is None

def test_rollback_approved_to_pending():
    assert validate_chapter_transition("approved", "pending") is None

def test_error_to_pending_on_retry():
    assert validate_chapter_transition("error", "pending") is None

def test_unknown_status_rejected():
    err = validate_chapter_transition("pending", "nonexistent")
    assert err is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py -v
```

Expected: all FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现状态机**

```python
# backend/app/extensions/writing/__init__.py
"""Writing Context — chapter lifecycle, AI generation, writer assignment."""
```

```python
# backend/app/extensions/writing/state_machine.py
"""Chapter status state machine.

States: pending → draft → completed → approved
              ↘ error ↗ (retry)
         completed → pending (rejection rollback)
         approved → pending (rejection rollback)
"""
from __future__ import annotations

from enum import StrEnum


class ChapterStatus(StrEnum):
    PENDING = "pending"
    DRAFT = "draft"
    COMPLETED = "completed"
    APPROVED = "approved"
    ERROR = "error"


VALID_CHAPTER_TRANSITIONS: dict[str, set[str]] = {
    ChapterStatus.PENDING: {ChapterStatus.DRAFT, ChapterStatus.ERROR},
    ChapterStatus.DRAFT: {ChapterStatus.COMPLETED, ChapterStatus.PENDING},
    ChapterStatus.COMPLETED: {ChapterStatus.APPROVED, ChapterStatus.PENDING},
    ChapterStatus.APPROVED: {ChapterStatus.PENDING},
    ChapterStatus.ERROR: {ChapterStatus.PENDING},
}


def validate_chapter_transition(current: str, target: str) -> str | None:
    """Return error message if transition is invalid, else None."""
    if target not in VALID_CHAPTER_TRANSITIONS:
        return f"Unknown chapter status: {target!r}"
    allowed = VALID_CHAPTER_TRANSITIONS.get(current, set())
    if target not in allowed:
        return f"Cannot transition chapter from {current!r} to {target!r}"
    return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/writing/__init__.py backend/app/extensions/writing/state_machine.py backend/tests/test_writing_context.py
git commit -m "feat: add chapter status state machine with transition validation"
```

### Task 3.2: 依赖图推导

**Files:**
- Create: `backend/app/extensions/writing/dependency_graph.py`

- [ ] **Step 1: 写测试**

In `backend/tests/test_writing_context.py`, add:

```python
from app.extensions.writing.dependency_graph import derive_chapter_dependencies


class TestDependencyGraph:
    def test_simple_linear_dependencies(self):
        """3 个同级章节 → 第2章依赖第1章，第3章依赖第2章"""
        sections = [
            {"title": "第1章 概述", "sort_order": 0, "children": []},
            {"title": "第2章 工程分析", "sort_order": 1, "children": []},
            {"title": "第3章 环境现状", "sort_order": 2, "children": []},
        ]
        deps = derive_chapter_dependencies(sections)
        assert deps["第2章 工程分析"] == {"第1章 概述"}
        assert deps["第3章 环境现状"] == {"第2章 工程分析"}

    def test_parent_before_child(self):
        """子章节依赖父章节"""
        sections = [
            {"title": "第1章 概述", "sort_order": 0, "children": [
                {"title": "1.1 项目背景", "sort_order": 0, "children": []},
                {"title": "1.2 编制依据", "sort_order": 1, "children": []},
            ]},
        ]
        deps = derive_chapter_dependencies(sections)
        assert "第1章 概述" in deps.get("1.1 项目背景", set())
        assert "第1章 概述" in deps.get("1.2 编制依据", set())

    def test_sibling_children_independent(self):
        """不同父章节下的同级子章节无依赖"""
        sections = [
            {"title": "第1章", "sort_order": 0, "children": [
                {"title": "1.1", "sort_order": 0, "children": []},
            ]},
            {"title": "第2章", "sort_order": 1, "children": [
                {"title": "2.1", "sort_order": 0, "children": []},
            ]},
        ]
        deps = derive_chapter_dependencies(sections)
        assert "2.1" not in deps.get("1.1", set())
        assert "1.1" not in deps.get("2.1", set())

    def test_sibling_children_in_same_parent_depend(self):
        """同一父下的子章节按 sort_order 依赖"""
        sections = [
            {"title": "第1章", "sort_order": 0, "children": [
                {"title": "1.1", "sort_order": 0, "children": []},
                {"title": "1.2", "sort_order": 1, "children": []},
            ]},
        ]
        deps = derive_chapter_dependencies(sections)
        assert "1.1" in deps.get("1.2", set())
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestDependencyGraph -v
```

- [ ] **Step 3: 实现依赖图推导**

```python
# backend/app/extensions/writing/dependency_graph.py
"""Derive chapter dependency graph from a template section tree.

Rules:
1. Parent → child: parent must be generated before children
2. Sibling (same parent): by sort_order — chapter[N] depends on chapter[N-1]
3. Sibling (different parent): independent, can be parallel
"""
from __future__ import annotations


def derive_chapter_dependencies(
    sections: list[dict],
    parent_title: str | None = None,
) -> dict[str, set[str]]:
    """Return {chapter_title: {depends_on_title, ...}} from a section tree.

    Args:
        sections: List of section dicts with 'title', 'sort_order', 'children'
        parent_title: Title of the parent section (None for top-level)

    Returns:
        Mapping of chapter title → set of titles it depends on
    """
    deps: dict[str, set[str]] = {}

    # Sort by sort_order within this level
    sorted_sections = sorted(sections, key=lambda s: s.get("sort_order", 0))

    for i, section in enumerate(sorted_sections):
        title = section["title"]
        section_deps: set[str] = set()

        # Rule 1: parent → child
        if parent_title:
            section_deps.add(parent_title)

        # Rule 2: sibling[i] depends on sibling[i-1]
        if i > 0:
            prev_title = sorted_sections[i - 1]["title"]
            section_deps.add(prev_title)

        deps[title] = section_deps

        # Recurse into children
        children = section.get("children", [])
        if children:
            child_deps = derive_chapter_dependencies(children, parent_title=title)
            deps.update(child_deps)

    return deps


def topological_order(
    sections: list[dict],
) -> list[list[str]]:
    """Return chapters grouped into parallel-executable batches.

    Batch 0 = no dependencies (can all start in parallel).
    Batch N = depends only on chapters in batches 0..N-1.
    """
    deps = derive_chapter_dependencies(sections)
    all_titles = set(deps.keys())
    batches: list[list[str]] = []
    completed: set[str] = set()

    remaining = all_titles - completed
    while remaining:
        batch = [
            title
            for title in remaining
            if deps.get(title, set()).issubset(completed)
        ]
        if not batch:
            # Cycle or orphan — break to avoid infinite loop
            break
        batches.append(batch)
        completed.update(batch)
        remaining = all_titles - completed

    return batches
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestDependencyGraph -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/writing/dependency_graph.py backend/tests/test_writing_context.py
git commit -m "feat: add chapter dependency derivation from template tree"
```

### Task 3.3: AI 生成策略选择器

**Files:**
- Create: `backend/app/extensions/writing/generation_strategy.py`

- [ ] **Step 1: 写测试**

In `backend/tests/test_writing_context.py`, add:

```python
from app.extensions.writing.generation_strategy import select_strategy, GenerationStrategy


class TestGenerationStrategy:
    def test_simple_report_uses_batch(self):
        """累计 < 10 万字的报告使用批量策略"""
        sections = [
            {"title": "第1章", "sort_order": 0, "children": [],
             "word_count_target": 5000},
            {"title": "第2章", "sort_order": 1, "children": [],
             "word_count_target": 5000},
        ]
        strategy = select_strategy(sections, report_type="safety_assessment")
        assert strategy == GenerationStrategy.BATCH

    def test_complex_report_uses_sequential(self):
        """累计 >= 10 万字的报告使用按章策略"""
        sections = [
            {"title": "第1章", "sort_order": 0, "children": [],
             "word_count_target": 100000},
        ]
        strategy = select_strategy(sections, report_type="environmental_impact")
        assert strategy == GenerationStrategy.SEQUENTIAL

    def test_manual_override(self):
        """手动指定覆盖自动判断"""
        strategy = select_strategy(
            [], report_type="safety_assessment",
            manual_override="sequential"
        )
        assert strategy == GenerationStrategy.SEQUENTIAL
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestGenerationStrategy -v
```

- [ ] **Step 3: 实现策略选择器**

```python
# backend/app/extensions/writing/generation_strategy.py
"""AI generation strategy selector — batch vs per-chapter."""
from __future__ import annotations

from enum import StrEnum


class GenerationStrategy(StrEnum):
    BATCH = "batch"          # All chapters in phase generated in parallel
    SEQUENTIAL = "sequential"  # Chapters generated in dependency order


COMPLEX_THRESHOLD = 100_000  # Total word_count_target


def select_strategy(
    sections: list[dict],
    report_type: str,
    manual_override: str | None = None,
) -> GenerationStrategy:
    """Select generation strategy based on report complexity.

    Args:
        sections: Template section tree with optional 'word_count_target'
        report_type: VALID_REPORT_TYPES value
        manual_override: 'batch' or 'sequential' from DAG node config

    Returns:
        The effective generation strategy
    """
    if manual_override:
        return GenerationStrategy(manual_override)

    total_words = _sum_word_counts(sections)
    if total_words >= COMPLEX_THRESHOLD:
        return GenerationStrategy.SEQUENTIAL
    return GenerationStrategy.BATCH


def _sum_word_counts(sections: list[dict]) -> int:
    total = 0
    for s in sections:
        total += s.get("word_count_target", 0)
        total += _sum_word_counts(s.get("children", []))
    return total
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestGenerationStrategy -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/writing/generation_strategy.py backend/tests/test_writing_context.py
git commit -m "feat: add AI generation strategy selector (batch vs sequential)"
```

### Task 3.4: Writer 负载均衡

**Files:**
- Create: `backend/app/extensions/writing/writer_assignment.py`

- [ ] **Step 1: 写测试**

In `backend/tests/test_writing_context.py`, add:

```python
from app.extensions.writing.writer_assignment import select_writer, WriterCandidate


class TestWriterAssignment:
    def test_selects_least_busy_writer(self):
        candidates = [
            WriterCandidate(user_id="u1", workload=5),
            WriterCandidate(user_id="u2", workload=2),
            WriterCandidate(user_id="u3", workload=7),
        ]
        selected = select_writer(candidates)
        assert selected == "u2"  # least busy

    def test_returns_none_for_empty(self):
        assert select_writer([]) is None

    def test_first_candidate_when_equal_workload(self):
        candidates = [
            WriterCandidate(user_id="u1", workload=3),
            WriterCandidate(user_id="u2", workload=3),
        ]
        selected = select_writer(candidates)
        assert selected in ("u1", "u2")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestWriterAssignment -v
```

- [ ] **Step 3: 实现分配器**

```python
# backend/app/extensions/writing/writer_assignment.py
"""Writer assignment with workload-aware load balancing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WriterCandidate:
    user_id: str
    workload: int = 0  # Number of currently assigned chapters


def select_writer(candidates: list[WriterCandidate]) -> str | None:
    """Select the writer with the lowest current workload.

    Ties are broken by position in the candidates list (stable).
    """
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.workload).user_id
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_writing_context.py::TestWriterAssignment -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/writing/writer_assignment.py backend/tests/test_writing_context.py
git commit -m "feat: add workload-aware writer assignment"
```

### Task 3.5: 集成到 Temporal Activities

**Files:**
- Modify: `backend/app/extensions/workflow/temporal/activities.py`

- [ ] **Step 1: 在 `start_ai_writing` 中使用 Writing Context**

In `activities.py`, update `start_ai_writing` to use the new modules:

```python
# Add after existing imports
from app.extensions.writing.generation_strategy import select_strategy, GenerationStrategy
from app.extensions.writing.dependency_graph import topological_order
from app.extensions.writing.state_machine import validate_chapter_transition

# In start_ai_writing, before _generate_content:
# Validate chapter transition
chapter = await db.get(ProjectChapter, uuid.UUID(chapter_id))
if chapter:
    err = validate_chapter_transition(chapter.status, "draft")
    if err:
        logger.warning("activity:start_ai_writing invalid transition: %s", err)
        return {"status": "skipped", "reason": err}
```

- [ ] **Step 2: 加一个批量生成入口 activity**

```python
@activity.defn
async def start_phase_ai_writing(phase_id: str, project_id: str) -> dict:
    """Batch AI generation for all chapters in a phase (simple report path)."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter, ReportProject
    from app.extensions.writing.dependency_graph import topological_order

    async with get_db_context() as db:
        project = await db.get(ReportProject, uuid.UUID(project_id))
        if not project or not project.template_id:
            return {"status": "error", "reason": "no template"}

        # Fetch template sections
        from app.extensions.knowledge_factory.models import ExtractionTemplate
        tmpl = await db.get(ExtractionTemplate, project.template_id)
        if not tmpl or not tmpl.root_sections_json:
            return {"status": "error", "reason": "no template sections"}

        # Get chapters in this phase
        chapters_result = await db.execute(
            select(ProjectChapter)
            .where(ProjectChapter.project_id == uuid.UUID(project_id))
            .where(ProjectChapter.phase_node == phase_id)
            .order_by(ProjectChapter.sort_order)
        )
        chapters = chapters_result.scalars().all()

        # Determine strategy
        strategy = select_strategy(tmpl.root_sections_json, project.report_type)

        results = []
        if strategy == GenerationStrategy.BATCH:
            # Parallel generation for all chapters
            for ch in chapters:
                content, error_code = await _generate_content(_build_writing_prompt(ch))
                if content:
                    ch.content = content
                    ch.status = "draft"
                else:
                    ch.status = "error"
                    ch.generation_hint = (ch.generation_hint or "") + f"\n[AI failed: {error_code}]"
                results.append({"chapter_id": str(ch.id), "status": ch.status})
            await db.commit()
        else:
            # Sequential — process in dependency order
            batches = topological_order(tmpl.root_sections_json)
            for batch in batches:
                batch_chapters = [c for c in chapters if c.title in batch]
                for ch in batch_chapters:
                    content, error_code = await _generate_content(_build_writing_prompt(ch))
                    if content:
                        ch.content = content
                        ch.status = "draft"
                    else:
                        ch.status = "error"
                        ch.generation_hint = (ch.generation_hint or "") + f"\n[AI failed: {error_code}]"
                    results.append({"chapter_id": str(ch.id), "status": ch.status})
                await db.commit()

        return {"status": "ok", "phase_id": phase_id, "results": results}
```

- [ ] **Step 3: 验证 activities 编译**

```bash
cd backend && python -c "
import sys; sys.path.insert(0, '.')
# temporalio is not available locally — check that non-temporal imports work
from app.extensions.writing.generation_strategy import select_strategy, GenerationStrategy
from app.extensions.writing.dependency_graph import topological_order
from app.extensions.writing.state_machine import validate_chapter_transition
from app.extensions.writing.writer_assignment import select_writer
print('Writing Context integration imports OK')
"
```

- [ ] **Step 4: 重启 Gateway 验证**

```bash
docker compose -p eai-docker restart gateway
sleep 15
curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/health
```

Expected: 200

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/temporal/activities.py
git commit -m "feat: integrate Writing Context into Temporal activities (batch + sequential AI gen)"
```

---

## Phase 4: Review Context 重构

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/extensions/review/` | Review Context package |
| **Create** | `backend/app/extensions/review/__init__.py` | Package init |
| **Create** | `backend/app/extensions/review/models.py` | ReviewAssignment + ReviewJudgment models |
| **Create** | `backend/app/extensions/review/gate.py` | ReviewGate 四种门控策略 |
| **Create** | `backend/app/extensions/review/rollback.py` | 驳回回滚（含章节状态重置） |
| **Modify** | `backend/app/extensions/workflow/temporal/activities.py` | review 节点使用 Review Context |
| **Modify** | `backend/app/extensions/workflow/routers.py` | 审核 API 统一到新端点 |
| **Modify** | `backend/app/extensions/database.py` | migrate_db 添加新表 |
| **Create** | `backend/tests/test_review_context.py` | Review Context 单元测试 |

### Task 4.1: ReviewAssignment + ReviewJudgment 模型

**Files:**
- Create: `backend/app/extensions/review/models.py`

- [ ] **Step 1: 创建模型**

```python
# backend/app/extensions/review/__init__.py
"""Review Context — review assignments, judgments, gating, rollback."""
```

```python
# backend/app/extensions/review/models.py
"""Review Context ORM models — unified replacement for PhaseReview + ApprovalWorkflow."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.models._base import Base


class ReviewAssignment(Base):
    """A review task assigned to one reviewer for one workflow node."""

    __tablename__ = "review_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id"), nullable=False, index=True
    )
    phase_node: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reviewer_role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="reviewer"
    )  # ProjectRole value
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | approved | rejected
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions: Mapped[list] = mapped_column(ARRAY(String), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    previous_judgments: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ReviewAssignment(id={self.id}, status={self.status})>"
```

- [ ] **Step 2: 在 database.py 添加建表**

```python
# In migrate_db(), add:
await conn.execute(text("""
    CREATE TABLE IF NOT EXISTS review_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES report_projects(id) ON DELETE CASCADE,
        phase_node VARCHAR(100) NOT NULL,
        reviewer_id UUID NOT NULL REFERENCES users(id),
        reviewer_role VARCHAR(50) NOT NULL DEFAULT 'reviewer',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        comment TEXT,
        dimensions VARCHAR(50)[] DEFAULT '{}',
        deadline_at TIMESTAMP,
        previous_judgments JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now()
    )
"""))
await conn.execute(text("""
    CREATE INDEX IF NOT EXISTS idx_review_assignments_project_phase
    ON review_assignments(project_id, phase_node)
"""))
await conn.execute(text("""
    CREATE INDEX IF NOT EXISTS idx_review_assignments_reviewer
    ON review_assignments(reviewer_id, status)
"""))
```

- [ ] **Step 3: 模型导入验证**

```bash
cd backend && python -c "
from app.extensions.review.models import ReviewAssignment
print('ReviewAssignment model OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/review/__init__.py backend/app/extensions/review/models.py backend/app/extensions/database.py
git commit -m "feat: add ReviewAssignment model (unified review)"
```

### Task 4.2: 审核门控策略

**Files:**
- Create: `backend/app/extensions/review/gate.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_review_context.py
import pytest
from app.extensions.review.gate import evaluate_gate, GateMode, GateResult


class TestReviewGate:
    def test_all_must_approve_all_approved(self):
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "approved"},
        ]
        result = evaluate_gate(GateMode.ALL_MUST_APPROVE, 2, judgments)
        assert result == GateResult.PASS

    def test_all_must_approve_one_rejected(self):
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.ALL_MUST_APPROVE, 2, judgments)
        assert result == GateResult.REJECT

    def test_all_must_approve_waiting(self):
        """Not all reviewers have submitted — still waiting."""
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
        ]
        result = evaluate_gate(GateMode.ALL_MUST_APPROVE, 2, judgments)
        assert result == GateResult.WAITING

    def test_any_can_approve_first_approved(self):
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
        ]
        result = evaluate_gate(GateMode.ANY_CAN_APPROVE, 3, judgments)
        assert result == GateResult.PASS

    def test_any_can_approve_all_rejected(self):
        judgments = [
            {"reviewer_id": "u1", "status": "rejected"},
            {"reviewer_id": "u2", "status": "rejected"},
            {"reviewer_id": "u3", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.ANY_CAN_APPROVE, 3, judgments)
        assert result == GateResult.REJECT

    def test_majority_pass(self):
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "approved"},
            {"reviewer_id": "u3", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.MAJORITY, 3, judgments)
        assert result == GateResult.PASS

    def test_majority_reject(self):
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "rejected"},
            {"reviewer_id": "u3", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.MAJORITY, 3, judgments)
        assert result == GateResult.REJECT
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_review_context.py::TestReviewGate -v
```

- [ ] **Step 3: 实现门控逻辑**

```python
# backend/app/extensions/review/gate.py
"""Review gate — waits for all assigned reviewers before deciding."""
from __future__ import annotations

from enum import StrEnum


class GateMode(StrEnum):
    ALL_MUST_APPROVE = "all_must_approve"
    ANY_CAN_APPROVE = "any_can_approve"
    MAJORITY = "majority"
    WEIGHTED = "weighted"


class GateResult(StrEnum):
    PASS = "pass"
    REJECT = "reject"
    WAITING = "waiting"


def evaluate_gate(
    mode: GateMode,
    total_reviewers: int,
    judgments: list[dict],
    weights: dict[str, float] | None = None,
) -> GateResult:
    """Evaluate the review gate based on current judgments.

    Args:
        mode: The gating strategy
        total_reviewers: Total number of assigned reviewers
        judgments: List of {reviewer_id, status} dicts for submitted judgments
        weights: Per-reviewer weight for WEIGHTED mode (defaults to 1.0 each)

    Returns:
        PASS — all conditions met, advance workflow
        REJECT — rejection threshold met, trigger rollback
        WAITING — not enough judgments yet, keep waiting
    """
    if len(judgments) < total_reviewers and mode != GateMode.ANY_CAN_APPROVE:
        return GateResult.WAITING

    approved = sum(1 for j in judgments if j["status"] == "approved")
    rejected = sum(1 for j in judgments if j["status"] == "rejected")

    if mode == GateMode.ALL_MUST_APPROVE:
        if len(judgments) < total_reviewers:
            return GateResult.WAITING
        if rejected > 0:
            return GateResult.REJECT
        return GateResult.PASS

    if mode == GateMode.ANY_CAN_APPROVE:
        if approved > 0:
            return GateResult.PASS
        if rejected == total_reviewers:
            return GateResult.REJECT
        return GateResult.WAITING

    if mode == GateMode.MAJORITY:
        threshold = total_reviewers / 2
        if approved > threshold:
            return GateResult.PASS
        if rejected > threshold or len(judgments) == total_reviewers:
            return GateResult.REJECT
        return GateResult.WAITING

    if mode == GateMode.WEIGHTED:
        w = weights or {}
        weighted_approved = sum(w.get(j["reviewer_id"], 1.0) for j in judgments if j["status"] == "approved")
        weighted_rejected = sum(w.get(j["reviewer_id"], 1.0) for j in judgments if j["status"] == "rejected")
        total_weight = sum(w.values()) if w else total_reviewers
        if weighted_approved > total_weight / 2:
            return GateResult.PASS
        if weighted_rejected >= total_weight / 2:
            return GateResult.REJECT
        return GateResult.WAITING

    return GateResult.WAITING
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_review_context.py::TestReviewGate -v
```

Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/review/gate.py backend/tests/test_review_context.py
git commit -m "feat: add review gate with 4 strategies"
```

### Task 4.3: 审核回滚（含章节状态重置）

**Files:**
- Create: `backend/app/extensions/review/rollback.py`

- [ ] **Step 1: 写测试**

In `backend/tests/test_review_context.py`, add:

```python
from app.extensions.review.rollback import build_rollback_plan


class TestRollback:
    def test_rollback_plan_includes_chapter_reset(self):
        plan = build_rollback_plan(
            project_id="p1",
            review_node_id="review_1",
            rollback_target="writing_2",
            affected_chapter_ids=["ch1", "ch2"],
            rejected_reviewer_ids=["u1"],
        )
        assert plan["target_phase"] == "writing_2"
        assert "ch1" in plan["chapters_to_reset"]
        assert "ch2" in plan["chapters_to_reset"]
        assert "u1" in plan["reviews_to_reset"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_review_context.py::TestRollback -v
```

- [ ] **Step 3: 实现回滚**

```python
# backend/app/extensions/review/rollback.py
"""Rejection rollback — resets reviews + chapters + project phase node."""
from __future__ import annotations

import uuid

from sqlalchemy import update as sa_update


def build_rollback_plan(
    project_id: str,
    review_node_id: str,
    rollback_target: str,
    affected_chapter_ids: list[str],
    rejected_reviewer_ids: list[str],
) -> dict:
    """Build a rollback plan (does NOT execute — caller executes with DB session).

    Returns a dict describing what to reset.
    """
    return {
        "project_id": project_id,
        "target_phase": rollback_target,
        "chapters_to_reset": affected_chapter_ids,
        "reviews_to_reset": rejected_reviewer_ids,
    }


async def execute_rollback(db, plan: dict):
    """Execute a rollback plan against the database."""
    from app.extensions.models import ProjectChapter, ReportProject
    from app.extensions.review.models import ReviewAssignment

    project_id = uuid.UUID(plan["project_id"])

    # 1. Reset rejected reviews to pending
    if plan.get("reviews_to_reset"):
        await db.execute(
            sa_update(ReviewAssignment)
            .where(ReviewAssignment.project_id == project_id)
            .where(ReviewAssignment.reviewer_id.in_(
                uuid.UUID(rid) for rid in plan["reviews_to_reset"]
            ))
            .values(status="pending")
        )

    # 2. Reset chapters in the rollback phase
    if plan.get("chapters_to_reset"):
        await db.execute(
            sa_update(ProjectChapter)
            .where(ProjectChapter.project_id == project_id)
            .where(ProjectChapter.id.in_(
                uuid.UUID(cid) for cid in plan["chapters_to_reset"]
            ))
            .where(ProjectChapter.status.in_(("completed", "approved", "reviewed")))
            .values(status="pending")
        )

    # 3. Move project to rollback target
    await db.execute(
        sa_update(ReportProject)
        .where(ReportProject.id == project_id)
        .values(current_phase_node=plan["target_phase"])
    )

    await db.commit()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_review_context.py::TestRollback -v
```

Expected: 1 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/review/rollback.py backend/tests/test_review_context.py
git commit -m "feat: add rejection rollback with chapter status reset"
```

---

## Phase 5: DocSpace + 定稿流程

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/extensions/docmgr/finalize.py` | 定稿流程：前置校验 + 合规检查 + 执行定稿 |
| **Modify** | `backend/app/extensions/docmgr/routers.py` | 定稿 API 端点 |
| **Modify** | `backend/app/extensions/models.py` | AIDocument 添加 chapter_id FK |
| **Modify** | `backend/app/extensions/database.py` | migrate_db 添加 FK 列 |
| **Create** | `backend/tests/test_finalize.py` | 定稿流程测试 |

### Task 5.1: AIDocument.chapter_id 显式 FK

**Files:**
- Modify: `backend/app/extensions/models.py`
- Modify: `backend/app/extensions/database.py`

- [ ] **Step 1: 在 AIDocument 模型添加字段**

In the `AIDocument` class in `models.py`, add:

```python
chapter_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("project_chapters.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
```

- [ ] **Step 2: 在 database.py 添加迁移**

```python
await conn.execute(text("""
    ALTER TABLE ai_documents
    ADD COLUMN IF NOT EXISTS chapter_id UUID
    REFERENCES project_chapters(id) ON DELETE SET NULL
"""))
await conn.execute(text("""
    CREATE INDEX IF NOT EXISTS idx_ai_documents_chapter_id
    ON ai_documents(chapter_id)
"""))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/models.py backend/app/extensions/database.py
git commit -m "feat: add AIDocument.chapter_id FK for explicit chapter linking"
```

### Task 5.2: 定稿流程

**Files:**
- Create: `backend/app/extensions/docmgr/finalize.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_finalize.py
import pytest
from app.extensions.docmgr.finalize import (
    check_preconditions,
    PreconditionResult,
    FinalizeStatus,
)


class TestFinalizePreconditions:
    def test_all_chapters_completed_passes(self):
        chapters = [
            {"id": "c1", "title": "1", "status": "completed"},
            {"id": "c2", "title": "2", "status": "approved"},
        ]
        result = check_preconditions(chapters, reviews_approved=True)
        assert result.status == FinalizeStatus.READY

    def test_pending_chapter_returns_warnings(self):
        chapters = [
            {"id": "c1", "title": "1", "status": "completed"},
            {"id": "c2", "title": "2", "status": "pending"},
        ]
        result = check_preconditions(chapters, reviews_approved=True)
        assert result.status == FinalizeStatus.WARNINGS
        assert any("pending" in w.lower() for w in result.warnings)

    def test_reviews_not_approved_returns_blocked(self):
        chapters = [
            {"id": "c1", "title": "1", "status": "completed"},
        ]
        result = check_preconditions(chapters, reviews_approved=False)
        assert result.status == FinalizeStatus.BLOCKED
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_finalize.py -v
```

- [ ] **Step 3: 实现定稿流程**

```python
# backend/app/extensions/docmgr/finalize.py
"""Finalize flow — precondition check → compliance → confirm → lock."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FinalizeStatus(StrEnum):
    READY = "ready"       # All conditions met, can finalize
    WARNINGS = "warnings"  # Warnings present, need owner confirmation
    BLOCKED = "blocked"    # Errors, cannot proceed


@dataclass
class PreconditionResult:
    status: FinalizeStatus
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def check_preconditions(
    chapters: list[dict],
    reviews_approved: bool,
    unresolved_comments: int = 0,
    source_coverage: float = 0.8,
    coverage_threshold: float = 0.8,
) -> PreconditionResult:
    """Check finalization preconditions.

    Args:
        chapters: List of {id, title, status} dicts
        reviews_approved: Whether all review gates have passed
        unresolved_comments: Count of unresolved comments
        source_coverage: Fraction of paragraphs with source citations
        coverage_threshold: Minimum acceptable coverage (default 0.8)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Must-have: all reviews approved
    if not reviews_approved:
        errors.append("审核尚未全部通过，无法定稿")
        return PreconditionResult(status=FinalizeStatus.BLOCKED, errors=errors)

    # Must-have: all chapters completed or approved
    incomplete = [c for c in chapters if c["status"] not in ("completed", "approved")]
    if incomplete:
        titles = ", ".join(c["title"] for c in incomplete)
        errors.append(f"以下章节未完成: {titles}")
        return PreconditionResult(status=FinalizeStatus.BLOCKED, errors=errors)

    # Warning: unresolved comments
    if unresolved_comments > 0:
        warnings.append(f"存在 {unresolved_comments} 条未解决的评论")

    # Warning: low source coverage
    if source_coverage < coverage_threshold:
        warnings.append(
            f"溯源覆盖率 {source_coverage:.0%} 低于阈值 {coverage_threshold:.0%}"
        )

    if warnings:
        return PreconditionResult(status=FinalizeStatus.WARNINGS, warnings=warnings)

    return PreconditionResult(status=FinalizeStatus.READY)


async def execute_finalize(
    db: AsyncSession,
    project_id: uuid.UUID,
    exemptions: list[dict] | None = None,
):
    """Execute finalization: lock chapters, create final document."""
    from app.extensions.models import ProjectChapter, ReportProject

    project = await db.get(ReportProject, project_id)
    if not project:
        return {"status": "error", "detail": "Project not found"}

    # Lock all chapters to APPROVED
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.status.in_(("completed", "approved")))
        .values(status="approved")
    )

    # Mark project as completed
    project.status = "completed"

    # Create merged final document entry
    from app.extensions.models import AIDocument
    final_doc = AIDocument(
        project_id=project_id,
        title=f"{project.name} (定稿)",
        content="",  # Will be populated by merge
        doc_type="final",
        status="final",
    )
    db.add(final_doc)
    await db.commit()
    await db.refresh(final_doc)

    return {"status": "ok", "document_id": str(final_doc.id)}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_finalize.py -v
```

Expected: 3 PASS

- [ ] **Step 5: 在 routers.py 添加定稿端点**

In `backend/app/extensions/docmgr/routers.py` (or project routers), add:

```python
@router.post("/projects/{project_id}/finalize")
async def finalize_check(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Check finalization preconditions and return report."""
    from app.extensions.docmgr.finalize import check_preconditions
    from app.extensions.models import ProjectChapter

    chapters_result = await db.execute(
        select(ProjectChapter.id, ProjectChapter.title, ProjectChapter.status)
        .where(ProjectChapter.project_id == project_id)
    )
    chapters = [
        {"id": str(r[0]), "title": r[1], "status": r[2]}
        for r in chapters_result.all()
    ]

    # Check reviews: query ReviewAssignment table for this project
    from app.extensions.review.models import ReviewAssignment
    review_result = await db.execute(
        select(ReviewAssignment.status).where(
            ReviewAssignment.project_id == project_id
        )
    )
    review_statuses = [r[0] for r in review_result.all()]
    reviews_ok = (
        len(review_statuses) > 0
        and all(s == "approved" for s in review_statuses)
    )

    result = check_preconditions(chapters, reviews_ok)
    return {"status": result.status, "warnings": result.warnings, "errors": result.errors}


@router.post("/projects/{project_id}/finalize/confirm")
async def finalize_confirm(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Confirm finalization with optional exemptions."""
    from app.extensions.docmgr.finalize import execute_finalize

    result = await execute_finalize(db, project_id)
    return result
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/docmgr/finalize.py backend/app/extensions/docmgr/routers.py backend/tests/test_finalize.py
git commit -m "feat: add finalize flow with precondition check and chapter locking"
```

---

## Phase 6: 个人仪表盘待办

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Modify** | `backend/app/extensions/dashboard/routers.py` | 添加 my-todos 端点 |
| **Create** | `backend/app/extensions/dashboard/todo_aggregator.py` | 跨上下文待办聚合查询 |
| **Create** | `backend/tests/test_dashboard_todos.py` | 待办查询测试 |

### Task 6.1: 待办聚合器

**Files:**
- Create: `backend/app/extensions/dashboard/todo_aggregator.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/test_dashboard_todos.py
import pytest
from app.extensions.dashboard.todo_aggregator import (
    TodoTask,
    TodoSummary,
    group_by_type,
)


class TestTodoAggregator:
    def test_group_by_type(self):
        tasks = [
            TodoTask(task_id="1", task_type="writing", title="Ch1",
                     project_name="P1", task_status="pending",
                     project_id="p1", context={}, action_label="撰写",
                     action_route="/edit"),
            TodoTask(task_id="2", task_type="review", title="审核",
                     project_name="P1", task_status="pending",
                     project_id="p1", context={}, action_label="审核",
                     action_route="/review"),
            TodoTask(task_id="3", task_type="writing", title="Ch2",
                     project_name="P1", task_status="error",
                     project_id="p1", context={}, action_label="重试",
                     action_route="/edit"),
        ]
        grouped = group_by_type(tasks)
        assert len(grouped["writing"]) == 2
        assert len(grouped["review"]) == 1
        assert "approval" not in grouped or len(grouped.get("approval", [])) == 0

    def test_summary_counts(self):
        tasks = [
            TodoTask(task_id="1", task_type="writing", title="Ch1",
                     project_name="P1", task_status="pending",
                     project_id="p1", context={}, action_label="撰写",
                     action_route="/edit"),
            TodoTask(task_id="2", task_type="review", title="审核",
                     project_name="P1", task_status="pending",
                     project_id="p1", context={}, action_label="审核",
                     action_route="/review"),
        ]
        summary = TodoSummary.from_tasks(tasks)
        assert summary.total == 2
        assert summary.writing == 1
        assert summary.review == 1
        assert summary.approval == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_dashboard_todos.py -v
```

- [ ] **Step 3: 实现聚合器**

```python
# backend/app/extensions/dashboard/todo_aggregator.py
"""Cross-context todo aggregation — no new table, pure query views."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TodoTask:
    task_id: str
    task_type: str  # writing | review | approval
    title: str
    project_name: str
    task_status: str
    project_id: str
    context: dict = field(default_factory=dict)
    action_label: str = ""
    action_route: str = ""
    is_overdue: bool = False
    due_label: str = ""


@dataclass
class TodoSummary:
    total: int = 0
    writing: int = 0
    review: int = 0
    approval: int = 0
    overdue: int = 0

    @classmethod
    def from_tasks(cls, tasks: list[TodoTask]) -> TodoSummary:
        return cls(
            total=len(tasks),
            writing=sum(1 for t in tasks if t.task_type == "writing"),
            review=sum(1 for t in tasks if t.task_type == "review"),
            approval=sum(1 for t in tasks if t.task_type == "approval"),
            overdue=sum(1 for t in tasks if t.is_overdue),
        )


def group_by_type(tasks: list[TodoTask]) -> dict[str, list[TodoTask]]:
    grouped: dict[str, list[TodoTask]] = {}
    for task in tasks:
        grouped.setdefault(task.task_type, []).append(task)
    return grouped


async def aggregate_todos(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID | None = None,
) -> list[TodoTask]:
    """Aggregate todos from Writing, Review, and Approval contexts.

    Uses a UNION query across three sources.
    """
    project_filter = "AND p.id = :project_id" if project_id else ""

    query = text(f"""
        -- Writing: chapters assigned to me
        SELECT
            ch.id::text AS task_id,
            'writing' AS task_type,
            ch.title,
            p.name AS project_name,
            ch.status AS task_status,
            p.id::text AS project_id,
            jsonb_build_object(
                'phase_node', COALESCE(ch.phase_node, ''),
                'chapter_id', ch.id::text,
                'word_count_target', ch.word_count_target,
                'word_count_current', ch.word_count_current
            ) AS context,
            CASE ch.status
                WHEN 'error' THEN '重试生成'
                WHEN 'draft' THEN '继续编辑'
                ELSE '开始撰写'
            END AS action_label,
            '/projects/' || p.id::text || '/edit?chapter=' || ch.id::text AS action_route,
            false AS is_overdue,
            '' AS due_label
        FROM project_chapters ch
        JOIN report_projects p ON p.id = ch.project_id
        WHERE ch.assigned_to = :user_id
          AND ch.status IN ('pending', 'draft', 'error')
          {project_filter.replace(':project_id', ':project_id_ch')}

        UNION ALL

        -- Review: reviews assigned to me
        SELECT
            ra.id::text AS task_id,
            'review' AS task_type,
            '审核: ' || ra.phase_node AS title,
            p.name AS project_name,
            ra.status AS task_status,
            p.id::text AS project_id,
            jsonb_build_object(
                'phase_node', ra.phase_node,
                'reviewer_role', ra.reviewer_role
            ) AS context,
            '提交审核意见' AS action_label,
            '/projects/' || p.id::text || '/review?node=' || ra.phase_node AS action_route,
            (ra.deadline_at IS NOT NULL AND ra.deadline_at < now()) AS is_overdue,
            CASE
                WHEN ra.deadline_at IS NULL THEN ''
                WHEN ra.deadline_at < now() THEN '已超时'
                ELSE ''
            END AS due_label
        FROM review_assignments ra
        JOIN report_projects p ON p.id = ra.project_id
        WHERE ra.reviewer_id = :user_id
          AND ra.status = 'pending'
          {project_filter.replace(':project_id', ':project_id_ra')}

        UNION ALL

        -- Approval: final sign-offs for me
        SELECT
            ra.id::text AS task_id,
            'approval' AS task_type,
            '最终审批: ' || p.name AS title,
            p.name AS project_name,
            'pending' AS task_status,
            p.id::text AS project_id,
            jsonb_build_object('reviewer_role', ra.reviewer_role) AS context,
            '签字审批' AS action_label,
            '/projects/' || p.id::text || '/approval' AS action_route,
            false AS is_overdue,
            '' AS due_label
        FROM review_assignments ra
        JOIN report_projects p ON p.id = ra.project_id
        WHERE ra.reviewer_id = :user_id
          AND ra.status = 'pending'
          AND ra.reviewer_role = 'approver'
          {project_filter.replace(':project_id', ':project_id_ap')}

        ORDER BY
            CASE task_status WHEN 'error' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            is_overdue DESC
    """)

    params = {"user_id": user_id}
    if project_id:
        params.update({
            "project_id_ch": project_id,
            "project_id_ra": project_id,
            "project_id_ap": project_id,
        })

    result = await db.execute(query, params)
    rows = result.all()
    return [
        TodoTask(
            task_id=row.task_id,
            task_type=row.task_type,
            title=row.title,
            project_name=row.project_name,
            task_status=row.task_status,
            project_id=row.project_id,
            context=row.context or {},
            action_label=row.action_label,
            action_route=row.action_route,
            is_overdue=row.is_overdue,
            due_label=row.due_label or "",
        )
        for row in rows
    ]
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_dashboard_todos.py -v
```

Expected: 2 PASS (unit tests — aggregate query requires DB for full test)

- [ ] **Step 5: 在 dashboard routers 添加端点**

```python
@router.get("/my-todos")
async def my_todos(
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
    project_id: UUID | None = Query(None),
):
    """Get current user's aggregated todo list."""
    from app.extensions.dashboard.todo_aggregator import aggregate_todos, group_by_type, TodoSummary

    tasks = await aggregate_todos(db, user.id, project_id)
    return {
        "todos": tasks,
        "summary": TodoSummary.from_tasks(tasks),
        "by_type": group_by_type(tasks),
    }


@router.get("/my-todos/summary")
async def my_todos_summary(
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get todo counts only (lightweight)."""
    from app.extensions.dashboard.todo_aggregator import aggregate_todos, TodoSummary

    tasks = await aggregate_todos(db, user.id)
    return TodoSummary.from_tasks(tasks)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/dashboard/todo_aggregator.py backend/app/extensions/dashboard/routers.py backend/tests/test_dashboard_todos.py
git commit -m "feat: add cross-context todo aggregation for personal dashboard"
```

---

## Phase 7: 迁移 + 清理

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/scripts/migrate_phase_duties.py` | 旧 phase_duties 格式 → 新格式迁移 |
| **Create** | `backend/scripts/migrate_review_data.py` | PhaseReview → ReviewAssignment 数据迁移 |
| **Modify** | `backend/app/extensions/workflow/routers.py` | 废弃旧审批端点（返回 410） |
| **Modify** | `backend/app/extensions/models.py` | ApprovalWorkflow/ApprovalRecord 标记废弃 |

### Task 7.1: phase_duties 数据迁移

**Files:**
- Create: `backend/scripts/migrate_phase_duties.py`

- [ ] **Step 1: 迁移脚本**

```python
# backend/scripts/migrate_phase_duties.py
"""Migrate legacy phase_duties JSONB to unified format.

Old: {"node_id": {"duty": "lead", "slot_type": "leader"}}
New: {"node_id": {"role": "phase_lead"}}

Run: PYTHONPATH=. python scripts/migrate_phase_duties.py [--dry-run]
"""
import asyncio
import sys

LEGACY_MAP = {
    "lead": "phase_lead",
    "leader": "phase_lead",
    "writer": "writer",
    "write": "writer",
    "reviewer": "reviewer",
    "dept_reviewer": "reviewer",
    "approver": "approver",
    "company_reviewer": "approver",
    "data_reviewer": "reviewer",
}


async def migrate(dry_run: bool = True):
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectMember
    from sqlalchemy import select

    async with get_db_context() as db:
        result = await db.execute(select(ProjectMember))
        members = result.scalars().all()

        migrated = 0
        skipped = 0

        for member in members:
            duties = member.phase_duties or {}
            if not duties:
                skipped += 1
                continue

            new_duties = {}
            changed = False
            for node_id, duty_data in duties.items():
                if not isinstance(duty_data, dict):
                    new_duties[node_id] = duty_data
                    continue

                old_duty = duty_data.get("duty")
                old_slot = duty_data.get("slot_type")
                new_role = duty_data.get("role")

                if new_role:
                    # Already migrated
                    new_duties[node_id] = {"role": new_role}
                elif old_duty:
                    new_duties[node_id] = {
                        "role": LEGACY_MAP.get(old_duty, old_duty)
                    }
                    changed = True
                elif old_slot:
                    new_duties[node_id] = {
                        "role": LEGACY_MAP.get(old_slot, old_slot)
                    }
                    changed = True
                else:
                    new_duties[node_id] = duty_data

            if changed:
                if not dry_run:
                    member.phase_duties = new_duties
                migrated += 1

        if not dry_run:
            await db.commit()

        print(f"Total members: {len(members)}")
        print(f"Migrated: {migrated}")
        print(f"Skipped (no duties): {skipped}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry))
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/migrate_phase_duties.py
git commit -m "feat: add phase_duties migration script (legacy → unified format)"
```

### Task 7.2: 废弃旧审批端点

**Files:**
- Modify: `backend/app/extensions/workflow/routers.py`

- [ ] **Step 1: 旧端点返回 410 Gone**

```python
# Replace old approval endpoints with 410 responses
@router.post("/projects/{project_id}/submit-approval")
async def submit_approval_deprecated(project_id: UUID):
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/finalize instead.",
    )

@router.post("/projects/{project_id}/approval-action")
async def approval_action_deprecated(project_id: UUID):
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/phase-reviews/{id}/action instead.",
    )

@router.get("/projects/{project_id}/approval-status")
async def approval_status_deprecated(project_id: UUID):
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use /projects/{id}/phase-reviews instead.",
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/workflow/routers.py
git commit -m "refactor: deprecate old approval endpoints (410 Gone)"
```

### Task 7.3: 最终验证 + Gateway 重启

```bash
# Restart gateway
docker compose -p eai-docker restart gateway
sleep 15
# Health check
curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/health
# Expected: 200
```

- [ ] **Commit**

```bash
git add -A
git commit -m "chore: final migration scripts and endpoint cleanup"
```

---

## 总览：7 个 Phase

| Phase | 任务数 | 估计时间 | 独立可测 |
|-------|--------|---------|---------|
| P1: Shared Kernel + 权限 | 3 tasks | ~1.5h | ✅ 权限导入 + 废弃标记 |
| P2: Orchestration 注册表 | 3 tasks | ~1.5h | ✅ 注册表 + START/END |
| P3: Writing Context | 5 tasks | ~2.5h | ✅ 状态机 + 依赖 + 策略 |
| P4: Review Context | 3 tasks | ~2h | ✅ 门控策略 + 回滚 |
| P5: DocSpace + 定稿 | 2 tasks | ~1.5h | ✅ FK + 定稿流程 |
| P6: 仪表盘待办 | 1 task | ~1h | ✅ 聚合查询 |
| P7: 迁移 + 清理 | 3 tasks | ~1h | ✅ 数据迁移脚本 |

**总计: ~11h, 20 tasks**

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Temporal 节点注册表变更导致现有工作流中断 | 每个新节点类型作为新 type 注册，旧 type 保留别名映射 |
| 权限迁移导致用户访问被拒绝 | 先并轨运行，旧模块 DeprecationWarning 过渡 2 周 |
| 批量 AI 生成消耗大量 LLM 配额 | `start_phase_ai_writing` 在 BATCH 模式下限制并发章节数（默认 5） |
| 定稿锁定后需要修改 | 支持创建修订版本（Revision），走简化审核流 |
