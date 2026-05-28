# 项目管理 RBAC + 成员工作台 + 审核流程 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目管理模块实现全链路 RBAC 权限控制、角色驱动的成员工作台、以及灵活的审核流程。

**Architecture:** 在现有 `require_permission` 基础上新增资源级权限矩阵（`PERMISSION_MATRIX`），通过 `require_resource_permission()` FastAPI 依赖注入检查。前端通过 `useProjectPermissions()` Hook 消费 `GET /projects/{id}/my-permissions` 返回的权限列表，驱动 Tab 可见性和操作按钮显隐。审核流程在 `ApprovalWorkflow` 模型上新增 `reviewer_id` 字段，支持经理灵活指定审核人。

**Tech Stack:** FastAPI + SQLAlchemy async（后端），React 19 + TanStack Query + Next.js 16（前端），pytest + vitest（测试）

---

## File Structure

### Backend — 新建文件

| 文件 | 职责 |
|------|------|
| `backend/app/extensions/project/permissions.py` | 权限矩阵定义 + `require_resource_permission()` 依赖工厂 |
| `backend/tests/test_project_permissions.py` | 权限检查函数的单元测试 |

### Backend — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/app/extensions/models.py:603-629` | `ApprovalWorkflow` 新增 `reviewer_id` 字段 |
| `backend/app/extensions/project/schemas.py` | 新增 `MyPermissionsResponse`、`ApprovalSubmitRequest`、`ApprovalStatusOut`；更新 `VALID_MEMBER_ROLES` 添加 `"writer"` |
| `backend/app/extensions/project/service.py` | 新增 `get_my_permissions()`、`submit_approval()`、`approval_action()`、`get_approval_status()`；`create_project()` 自动添加 manager 成员 |
| `backend/app/extensions/project/routers.py` | 所有端点添加资源级权限检查；新增 4 个审核端点 + 1 个权限查询端点 |

### Frontend — 新建文件

| 文件 | 职责 |
|------|------|
| `frontend/src/extensions/project/hooks/useProjectPermissions.ts` | 权限 Hook + Tab 注册表 |
| `frontend/src/extensions/project/tabRegistry.ts` | Tab 配置常量（角色→默认页、权限→可见性） |

### Frontend — 修改文件

| 文件 | 修改内容 |
|------|---------|
| `frontend/src/extensions/project/types.ts` | 更新 `MemberRole` 枚举（去掉 issuer）；新增 `ProjectMembership`、`ApprovalStepConfig` 类型 |
| `frontend/src/extensions/project/api.ts` | 新增 `getMyPermissions()`、`submitApproval()`、`approvalAction()`、`getApprovalStatus()` |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | 重构：使用 `useProjectPermissions` + Tab 注册表驱动视图 |
| `frontend/src/extensions/project/components/WorkspaceTabs.tsx` | 支持动态 Tab 列表（从注册表过滤）、默认页逻辑 |
| `frontend/src/extensions/project/components/MemberWorkspace.tsx` | 重构：展示被分配章节列表、按状态分组、操作按钮权限控制 |
| `frontend/src/extensions/project/components/ApprovalTab.tsx` | 重构：审核链配置 UI + 审核操作 UI + 状态可视化 |
| `frontend/src/extensions/project/components/MembersTab.tsx` | 添加权限控制：manager 才能添加/移除成员 |
| `frontend/src/extensions/project/components/KanbanBoard.tsx` | 添加权限控制：非 manager 只能操作自己被分配的卡片 |
| `frontend/src/extensions/project/components/AiToolsTab.tsx` | 添加权限控制：只有有 `ai:toolbox` 权限的角色可见 |

---

## Phase 1A: 权限基础设施

### Task 1: 后端权限矩阵 + 检查函数

**Files:**
- Create: `backend/app/extensions/project/permissions.py`
- Test: `backend/tests/test_project_permissions.py`

- [ ] **Step 1: 写权限检查函数的测试**

```python
# backend/tests/test_project_permissions.py
"""Tests for project permission matrix and check functions."""

import pytest
from app.extensions.project.permissions import (
    PERMISSION_MATRIX,
    ROLE_ORDER,
    check_permission,
    get_default_tab,
    get_permissions_for_role,
)


class TestPermissionMatrix:
    """Test the permission matrix structure and completeness."""

    def test_role_order_has_five_roles(self):
        assert len(ROLE_ORDER) == 5
        assert ROLE_ORDER == ["manager", "editor", "writer", "reviewer", "approver"]

    def test_all_actions_have_five_bools(self):
        for action, allowed in PERMISSION_MATRIX.items():
            assert len(allowed) == 5, f"Action '{action}' has {len(allowed)} entries, expected 5"


class TestCheckPermission:
    """Test check_permission for specific role/action combinations."""

    def test_manager_can_do_almost_everything(self):
        assert check_permission("manager", "project:edit") is True
        assert check_permission("manager", "member:add") is True
        assert check_permission("manager", "outline:edit") is True
        assert check_permission("manager", "chapter:write_any") is True
        assert check_permission("manager", "ai:start_writing") is True
        assert check_permission("manager", "approval:submit") is True
        assert check_permission("manager", "export:generate") is True

    def test_editor_can_edit_outline_and_chapters(self):
        assert check_permission("editor", "outline:edit") is True
        assert check_permission("editor", "chapter:write_own") is True
        assert check_permission("editor", "ai:start_editing") is True
        assert check_permission("editor", "ai:toolbox") is True
        # editor cannot manage project or members
        assert check_permission("editor", "project:edit") is False
        assert check_permission("editor", "member:add") is False

    def test_writer_can_only_write_own_chapters(self):
        assert check_permission("writer", "chapter:write_own") is True
        assert check_permission("writer", "ai:start_editing") is True
        assert check_permission("writer", "ai:toolbox") is True
        # writer cannot edit outline
        assert check_permission("writer", "outline:edit") is False
        assert check_permission("writer", "chapter:write_any") is False

    def test_reviewer_can_review_but_not_approve(self):
        assert check_permission("reviewer", "approval:review") is True
        assert check_permission("reviewer", "chapter:view_all") is True
        assert check_permission("reviewer", "outline:view") is True
        # reviewer cannot approve
        assert check_permission("reviewer", "approval:approve") is False
        assert check_permission("reviewer", "chapter:write_own") is False

    def test_approver_can_approve_but_not_review(self):
        assert check_permission("approver", "approval:approve") is True
        assert check_permission("approver", "chapter:view_all") is True
        # approver cannot review (reviewer role)
        assert check_permission("approver", "approval:review") is False
        assert check_permission("approver", "chapter:write_own") is False

    def test_unknown_role_returns_false(self):
        assert check_permission("unknown", "chapter:view_all") is False

    def test_unknown_action_returns_false(self):
        assert check_permission("manager", "nonexistent:action") is False


class TestGetPermissionsForRole:
    def test_returns_all_allowed_actions(self):
        perms = get_permissions_for_role("manager")
        assert "project:edit" in perms
        assert "member:add" in perms
        assert "chapter:write_own" in perms

    def test_writer_permissions_subset_of_editor(self):
        writer_perms = set(get_permissions_for_role("writer"))
        editor_perms = set(get_permissions_for_role("editor"))
        # writer perms that are True should also be True for editor
        for p in writer_perms:
            assert p in editor_perms, f"Writer has '{p}' but editor doesn't"

    def test_empty_for_unknown_role(self):
        assert get_permissions_for_role("nonexistent") == []


class TestGetDefaultTab:
    def test_manager_defaults_to_dashboard(self):
        assert get_default_tab("manager") == "dashboard"

    def test_editor_defaults_to_my_workspace(self):
        assert get_default_tab("editor") == "my-workspace"

    def test_writer_defaults_to_my_workspace(self):
        assert get_default_tab("writer") == "my-workspace"

    def test_reviewer_defaults_to_kanban(self):
        assert get_default_tab("reviewer") == "kanban"

    def test_approver_defaults_to_kanban(self):
        assert get_default_tab("approver") == "kanban"

    def test_unknown_defaults_to_dashboard(self):
        assert get_default_tab("unknown") == "dashboard"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_permissions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.extensions.project.permissions'`

- [ ] **Step 3: 实现权限模块**

```python
# backend/app/extensions/project/permissions.py
"""Project-level RBAC permission matrix and check functions."""

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import CurrentUser, require_permission
from app.extensions.models import ProjectMember

ROLE_ORDER = ["manager", "editor", "writer", "reviewer", "approver"]

PERMISSION_MATRIX: dict[str, list[bool]] = {
    #                     manager  editor  writer  reviewer  approver
    "project:edit":       [True,   False,  False,  False,    False],
    "project:delete":     [True,   False,  False,  False,    False],
    "project:advance":    [True,   False,  False,  False,    False],

    "member:add":         [True,   False,  False,  False,    False],
    "member:remove":      [True,   False,  False,  False,    False],
    "member:list":        [True,   True,   True,   False,    False],

    "outline:edit":       [True,   True,   False,  False,    False],
    "outline:view":       [True,   True,   True,   True,     True],

    "chapter:write_own":  [True,   True,   True,   False,    False],
    "chapter:write_any":  [True,   False,  False,  False,    False],
    "chapter:view_all":   [True,   True,   True,   True,     True],
    "chapter:assign":     [True,   False,  False,  False,    False],
    "chapter:status":     [True,   False,  False,  False,    False],

    "ai:start_writing":   [True,   False,  False,  False,    False],
    "ai:start_editing":   [True,   True,   True,   False,    False],
    "ai:toolbox":         [True,   True,   True,   False,    False],

    "approval:submit":    [True,   False,  False,  False,    False],
    "approval:review":    [True,   False,  False,  True,     False],
    "approval:approve":   [True,   False,  False,  False,    True],
    "approval:view":      [True,   True,   True,   True,     True],

    "export:generate":    [True,   False,  False,  False,    False],
    "export:view":        [True,   True,   True,   True,     True],
}


def check_permission(role: str, action: str) -> bool:
    allowed = PERMISSION_MATRIX.get(action)
    if not allowed:
        return False
    idx = ROLE_ORDER.index(role) if role in ROLE_ORDER else -1
    return idx >= 0 and allowed[idx]


def get_permissions_for_role(role: str) -> list[str]:
    return [action for action, allowed in PERMISSION_MATRIX.items() if check_permission(role, action)]


def get_default_tab(role: str) -> str:
    defaults = {
        "manager": "dashboard",
        "editor": "my-workspace",
        "writer": "my-workspace",
        "reviewer": "kanban",
        "approver": "kanban",
    }
    return defaults.get(role, "dashboard")


async def get_project_role(
    db: AsyncSession, project_id: UUID, user_id: UUID
) -> str | None:
    result = await db.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_user_project_permissions(
    db: AsyncSession, project_id: UUID, user_id: UUID, is_admin: bool = False
) -> tuple[str | None, list[str]]:
    if is_admin:
        role = "manager"
    else:
        role = await get_project_role(db, project_id, user_id)
    if not role:
        return None, []
    return role, get_permissions_for_role(role)


def require_resource_permission(action: str):
    """FastAPI dependency: check current user's permission for a project resource."""
    async def _check(
        project_id: UUID,
        user: CurrentUser = Depends(require_permission("system:access")),
        db: AsyncSession = Depends(get_db),
    ) -> str:
        from app.extensions.models import Role
        role_row = await db.get(Role, user.role_id) if user.role_id else None
        is_admin = role_row is not None and ("*" in (role_row.permissions or []) or role_row.is_system)
        role = "manager" if is_admin else await get_project_role(db, project_id, user.id)
        if not role:
            raise HTTPException(status_code=403, detail="不是项目成员")
        if not check_permission(role, action):
            raise HTTPException(status_code=403, detail=f"角色 '{role}' 无权执行 '{action}'")
        return role
    return _check


# Lazy import to avoid circular dependency at module level
def get_db():
    from app.extensions.database import get_db as _get_db
    return _get_db()
```

注意：`get_db()` 需要用延迟导入。实际的 `get_db` 依赖来自 `app.extensions.database`，与 `routers.py` 中现有用法一致。后续 Step 会根据实际路径修正。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_permissions.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/project/permissions.py tests/test_project_permissions.py
git commit -m "feat(project): add permission matrix and RBAC check functions"
```

---

### Task 2: 更新 schemas — 添加 writer 角色 + 新增权限/审核 schemas

**Files:**
- Modify: `backend/app/extensions/project/schemas.py:24` (VALID_MEMBER_ROLES)
- Modify: `backend/app/extensions/project/schemas.py` (新增 schemas)

- [ ] **Step 1: 更新 VALID_MEMBER_ROLES，添加 "writer"**

在 `schemas.py` 第 24 行，将：

```python
VALID_MEMBER_ROLES = ["manager", "editor", "reviewer", "approver"]
```

改为：

```python
VALID_MEMBER_ROLES = ["manager", "editor", "writer", "reviewer", "approver"]
```

- [ ] **Step 2: 新增权限和审核相关 schemas**

在 `schemas.py` 文件末尾（约第 202 行之后）添加：

```python
# --- Permission schemas ---


class MyPermissionsResponse(BaseModel):
    role: str | None
    permissions: list[str]
    default_tab: str


# --- Approval workflow schemas ---


class ApprovalStepConfig(BaseModel):
    step_order: int
    step_name: str
    reviewer_id: UUID


class ApprovalSubmitRequest(BaseModel):
    steps: list[ApprovalStepConfig]


class ApprovalWorkflowWithRecords(BaseModel):
    id: UUID
    step_order: int
    step_name: str
    reviewer_id: UUID | None = None
    role_required: str
    status: str
    records: list[ApprovalRecordOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ApprovalStatusOut(BaseModel):
    project_id: UUID
    current_step: int | None
    total_steps: int
    steps: list[ApprovalWorkflowWithRecords]
    all_approved: bool

```

- [ ] **Step 3: 运行现有测试确认无破坏**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_writing_service.py -v`
Expected: 全部 PASS（schema 变更不应影响已有测试）

- [ ] **Step 4: 提交**

```bash
cd backend
git add app/extensions/project/schemas.py
git commit -m "feat(project): add writer role, permission and approval schemas"
```

---

### Task 3: ApprovalWorkflow 模型添加 reviewer_id 字段

**Files:**
- Modify: `backend/app/extensions/models.py:603-629`

- [ ] **Step 1: 在 ApprovalWorkflow 类中添加 reviewer_id 字段**

在 `models.py` 的 `ApprovalWorkflow` 类中（约第 625 行，`role_required` 之后），添加：

```python
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
```

完整效果：`ApprovalWorkflow` 应包含字段 `id`, `project_id`, `step_order`, `step_name`, `role_required`, `reviewer_id`, `status`, `created_at`。

- [ ] **Step 2: 创建 Alembic 迁移**

Run:
```bash
cd backend
PYTHONPATH=. uv run alembic revision --autogenerate -m "add reviewer_id to approval_workflows"
```

检查生成的迁移文件，确认只有 `approval_workflows` 表添加了 `reviewer_id` 列。然后执行：

```bash
PYTHONPATH=. uv run alembic upgrade head
```

- [ ] **Step 3: 提交**

```bash
cd backend
git add app/extensions/models.py alembic/versions/
git commit -m "feat(project): add reviewer_id to ApprovalWorkflow model"
```

---

### Task 4: Service 层 — 权限查询 + 审核流程函数

**Files:**
- Modify: `backend/app/extensions/project/service.py`

- [ ] **Step 1: 新增 `get_my_permissions` 函数**

在 `service.py` 中（约第 535 行，`start_chapter_editing` 函数之后），添加：

```python
async def get_my_permissions(
    db: AsyncSession, project_id: UUID, user_id: UUID, is_admin: bool = False
) -> dict:
    from app.extensions.project.permissions import get_user_project_permissions, get_default_tab
    role, permissions = await get_user_project_permissions(db, project_id, user_id, is_admin)
    return {
        "role": role,
        "permissions": permissions,
        "default_tab": get_default_tab(role) if role else "dashboard",
    }
```

- [ ] **Step 2: 新增审核流程函数**

继续在 `service.py` 末尾添加：

```python
async def submit_approval(
    db: AsyncSession, project_id: UUID, manager_id: UUID,
    steps: list[dict],
) -> dict:
    """Manager submits project for approval, creating workflow steps."""
    from app.extensions.models import ApprovalWorkflow, ReportProject

    project = await _get_project_or_404(db, project_id)

    # Validate: only manager can submit
    from app.extensions.project.permissions import get_project_role
    role = await get_project_role(db, project_id, manager_id)
    if role != "manager":
        raise HTTPException(status_code=403, detail="只有经理可以提交审核")

    # Delete existing workflows if any
    existing = await db.execute(
        select(ApprovalWorkflow).where(ApprovalWorkflow.project_id == project_id)
    )
    for wf in existing.scalars().all():
        await db.delete(wf)

    # Create new workflow steps
    for step_data in steps:
        workflow = ApprovalWorkflow(
            project_id=project_id,
            step_order=step_data["step_order"],
            step_name=step_data["step_name"],
            role_required="reviewer",  # kept for backward compat
            reviewer_id=step_data["reviewer_id"],
            status="pending",
        )
        db.add(workflow)

    # Advance project to stage 5
    project.current_stage = 5
    await db.flush()

    return {"project_id": project_id, "status": "submitted", "step_count": len(steps)}


async def approval_action(
    db: AsyncSession, project_id: UUID, workflow_id: UUID,
    reviewer_id: UUID, action: str, comment: str | None,
) -> dict:
    """Execute an approval action (approve/reject) on a workflow step."""
    from app.extensions.models import ApprovalWorkflow, ApprovalRecord, ReportProject

    workflow = await db.get(ApprovalWorkflow, workflow_id)
    if not workflow or workflow.project_id != project_id:
        raise HTTPException(status_code=404, detail="审核步骤不存在")

    if workflow.reviewer_id != reviewer_id:
        raise HTTPException(status_code=403, detail="您不是此步骤的指定审核人")

    if workflow.status != "pending":
        raise HTTPException(status_code=400, detail="此步骤已处理")

    # Record the action
    record = ApprovalRecord(
        workflow_id=workflow_id,
        project_id=project_id,
        action=action,
        reviewer_id=reviewer_id,
        comment=comment,
    )
    db.add(record)

    if action == "approve":
        workflow.status = "approved"
        # Check if all steps are approved
        all_steps = await db.execute(
            select(ApprovalWorkflow)
            .where(ApprovalWorkflow.project_id == project_id)
            .order_by(ApprovalWorkflow.step_order)
        )
        steps = all_steps.scalars().all()
        all_approved = all(s.status == "approved" for s in steps)

        if all_approved:
            project = await _get_project_or_404(db, project_id)
            project.current_stage = 6

    elif action == "reject":
        workflow.status = "rejected"
        # Roll back to stage 4
        project = await _get_project_or_404(db, project_id)
        project.current_stage = 4
        # Reset all subsequent steps to pending
        subsequent = await db.execute(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.project_id == project_id,
                ApprovalWorkflow.step_order > workflow.step_order,
            )
        )
        for s in subsequent.scalars().all():
            s.status = "pending"

    await db.flush()
    return {"workflow_id": workflow_id, "action": action, "new_stage": (await _get_project_or_404(db, project_id)).current_stage}


async def get_approval_status(db: AsyncSession, project_id: UUID) -> dict:
    """Get current approval status for a project."""
    from app.extensions.models import ApprovalWorkflow

    all_steps = await db.execute(
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.project_id == project_id)
        .order_by(ApprovalWorkflow.step_order)
    )
    steps = all_steps.scalars().all()

    current_step = None
    for s in steps:
        if s.status == "pending":
            current_step = s.step_order
            break

    return {
        "project_id": project_id,
        "current_step": current_step,
        "total_steps": len(steps),
        "steps": steps,
        "all_approved": len(steps) > 0 and all(s.status == "approved" for s in steps),
    }
```

注意：`service.py` 顶部需要 `from fastapi import HTTPException` 和 `from sqlalchemy import select`。检查文件顶部是否已有这些导入，若没有则添加。

- [ ] **Step 3: 修改 create_project 自动添加 manager 成员**

在 `service.py` 的 `create_project` 函数中（约第 270-294 行），在 `await db.flush()` 之后、`return` 之前，添加自动创建 manager 成员的逻辑：

```python
    # Auto-add creator as manager
    if created_by:
        member = ProjectMember(
            project_id=project.id,
            user_id=created_by,
            role="manager",
        )
        db.add(member)
        await db.flush()
```

确保 `ProjectMember` 已在文件顶部导入。

- [ ] **Step 4: 运行现有测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_writing_service.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd backend
git add app/extensions/project/service.py
git commit -m "feat(project): add permission query, approval workflow service functions"
```

---

### Task 5: Router 层 — 权限检查 + 新增端点

**Files:**
- Modify: `backend/app/extensions/project/routers.py`

- [ ] **Step 1: 添加权限相关导入和新增端点**

在 `routers.py` 顶部（约第 1-10 行区域），添加导入：

```python
from app.extensions.project.permissions import require_resource_permission
from app.extensions.project.schemas import (
    MyPermissionsResponse,
    ApprovalSubmitRequest,
    ApprovalStatusOut,
)
```

在文件末尾添加新端点：

```python
# --- Permission query ---


@router.get("/projects/{project_id}/my-permissions", response_model=MyPermissionsResponse)
async def get_my_permissions(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    from app.extensions.models import Role
    role_row = await db.get(Role, user.role_id) if user.role_id else None
    is_admin = role_row is not None and ("*" in (role_row.permissions or []) or role_row.is_system)
    return await service.get_my_permissions(db, project_id, user.id, is_admin=is_admin)


# --- Approval workflow ---


@router.post("/projects/{project_id}/submit-approval")
async def submit_approval(
    project_id: UUID,
    body: ApprovalSubmitRequest,
    _role: str = Depends(require_resource_permission("approval:submit")),
    db: AsyncSession = Depends(get_db),
    user: CurrentUserWithAccess = None,
):
    steps = [s.model_dump() for s in body.steps]
    return await service.submit_approval(db, project_id, user.id, steps)


@router.post("/projects/{project_id}/approval-action")
async def approval_action(
    project_id: UUID,
    body: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUserWithAccess = None,
):
    action = body.action
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    # Verify user is the designated reviewer for the current step
    return await service.approval_action(db, project_id, body.workflow_id, user.id, action, body.comment)


@router.get("/projects/{project_id}/approval-status", response_model=ApprovalStatusOut)
async def get_approval_status(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)


@router.get("/projects/{project_id}/approval-records")
async def get_approval_records(
    project_id: UUID,
    _role: str = Depends(require_resource_permission("approval:view")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_approval_status(db, project_id)
```

- [ ] **Step 2: 给现有端点添加权限检查**

逐个修改以下端点，添加 `Depends(require_resource_permission(...))`：

**`PATCH /projects/{project_id}`** (约第 87 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("project:edit"))`

**`DELETE /projects/{project_id}`** (约第 100 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("project:delete"))`

**`PUT /projects/{project_id}/outline`** (约第 123 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("outline:edit"))`

**`POST /projects/{project_id}/confirm-outline`** (约第 147 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("project:advance"))`

**`POST /projects/{project_id}/members`** (约第 162 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("member:add"))`

**`DELETE /projects/{project_id}/members/{user_id}`** (约第 174 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("member:remove"))`

**`POST /projects/{project_id}/start-writing`** (约第 192 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("ai:start_writing"))`

**`PATCH /projects/{project_id}/chapters/{chapter_id}`** (约第 133 行)：
在函数参数中添加 `_role: str = Depends(require_resource_permission("chapter:write_own"))`

注意：`chapter:write_own` 需要额外的所有权验证（当前用户是章节的 assigned_to 或者是 manager）。这个检查保留在 service 层处理，后续可增强。

- [ ] **Step 3: 运行全部后端测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v -k "project or permission"`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
cd backend
git add app/extensions/project/routers.py
git commit -m "feat(project): add resource-level permission checks to all endpoints"
```

---

### Task 6: 前端 — 类型 + API + Tab 注册表

**Files:**
- Modify: `frontend/src/extensions/project/types.ts`
- Modify: `frontend/src/extensions/project/api.ts`
- Create: `frontend/src/extensions/project/tabRegistry.ts`
- Create: `frontend/src/extensions/project/hooks/useProjectPermissions.ts`

- [ ] **Step 1: 更新 types.ts**

修改 `MemberRole` 枚举（第 25 行），去掉 `issuer`：

```typescript
export type MemberRole = "manager" | "editor" | "writer" | "reviewer" | "approver";
```

在文件末尾（约第 227 行之后）添加：

```typescript
// --- Permission types ---

export interface ProjectMembership {
  role: MemberRole | null;
  permissions: string[];
  defaultTab: string;
}

// --- Approval config types ---

export interface ApprovalStepConfig {
  stepOrder: number;
  stepName: string;
  reviewerId: string;
}

export interface ApprovalSubmitRequest {
  steps: ApprovalStepConfig[];
}

export interface ApprovalWorkflowWithRecords {
  id: string;
  stepOrder: number;
  stepName: string;
  reviewerId: string | null;
  roleRequired: string;
  status: string;
  records: ApprovalRecordOut[];
}

export interface ApprovalStatusResponse {
  projectId: string;
  currentStep: number | null;
  totalSteps: number;
  steps: ApprovalWorkflowWithRecords[];
  allApproved: boolean;
}
```

同时更新 `MEMBER_ROLE_LABELS`（约第 160 行区域），去掉 issuer 相关条目，确保 writer 标签存在：

```typescript
export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  manager: "经理",
  editor: "编辑",
  writer: "撰写人",
  reviewer: "审核人",
  approver: "批准人",
};
```

- [ ] **Step 2: 新增 API 函数**

在 `api.ts` 文件末尾（约第 134 行之后）添加：

```typescript
// --- Permissions ---

export async function getMyPermissions(projectId: string): Promise<ProjectMembership> {
  const data = await authFetch<{ role: string | null; permissions: string[]; default_tab: string }>(
    `${API_BASE}/projects/${projectId}/my-permissions`,
  );
  return toCamelCase<ProjectMembership>(data);
}

// --- Approval workflow ---

export async function submitApproval(
  projectId: string,
  steps: ApprovalStepConfig[],
): Promise<{ project_id: string; status: string; step_count: number }> {
  return authFetch(`${API_BASE}/projects/${projectId}/submit-approval`, {
    method: "POST",
    body: JSON.stringify(toSnakeCase({ steps })),
  });
}

export async function approvalAction(
  projectId: string,
  workflowId: string,
  action: "approve" | "reject",
  comment?: string,
): Promise<Record<string, unknown>> {
  return authFetch(`${API_BASE}/projects/${projectId}/approval-action`, {
    method: "POST",
    body: JSON.stringify(toSnakeCase({ workflowId, action, comment })),
  });
}

export async function getApprovalStatus(projectId: string): Promise<ApprovalStatusResponse> {
  const data = await authFetch(`${API_BASE}/projects/${projectId}/approval-status`);
  return toCamelCase<ApprovalStatusResponse>(data);
}
```

- [ ] **Step 3: 创建 tabRegistry.ts**

```typescript
// frontend/src/extensions/project/tabRegistry.ts

export interface TabConfig {
  id: string;
  label: string;
  icon: string;
  stages: number[];
  minPermission: string | null;
  defaultForRoles: string[];
}

export const TAB_REGISTRY: TabConfig[] = [
  {
    id: "my-workspace",
    label: "我的工作台",
    icon: "Target",
    stages: [3, 4, 5],
    minPermission: null,
    defaultForRoles: ["editor", "writer"],
  },
  {
    id: "dashboard",
    label: "仪表盘",
    icon: "BarChart3",
    stages: [2, 3, 4, 5, 6],
    minPermission: null,
    defaultForRoles: ["manager"],
  },
  {
    id: "kanban",
    label: "看板",
    icon: "Kanban",
    stages: [3, 4],
    minPermission: "chapter:view_all",
    defaultForRoles: ["reviewer", "approver"],
  },
  {
    id: "outline",
    label: "大纲",
    icon: "FileText",
    stages: [2, 3, 4],
    minPermission: "outline:view",
    defaultForRoles: [],
  },
  {
    id: "members",
    label: "成员",
    icon: "Users",
    stages: [2, 3, 4, 5, 6],
    minPermission: "member:list",
    defaultForRoles: [],
  },
  {
    id: "approval",
    label: "审核",
    icon: "CheckCircle",
    stages: [5],
    minPermission: "approval:view",
    defaultForRoles: [],
  },
  {
    id: "ai-tools",
    label: "AI工具",
    icon: "Bot",
    stages: [3, 4],
    minPermission: "ai:toolbox",
    defaultForRoles: [],
  },
];

export function getVisibleTabs(
  stage: number,
  permissions: string[],
  role: string | null,
): TabConfig[] {
  return TAB_REGISTRY.filter((tab) => {
    if (!tab.stages.includes(stage)) return false;
    if (tab.minPermission && !permissions.includes(tab.minPermission)) return false;
    return true;
  });
}

export function getDefaultTab(
  stage: number,
  permissions: string[],
  role: string | null,
): string {
  const visible = getVisibleTabs(stage, permissions, role);
  if (!role) return "dashboard";

  // Check if role's default tab is visible
  const roleDefault = TAB_REGISTRY.find((t) => t.defaultForRoles.includes(role));
  if (roleDefault && visible.find((t) => t.id === roleDefault.id)) {
    return roleDefault.id;
  }

  return visible[0]?.id ?? "dashboard";
}
```

- [ ] **Step 4: 创建 useProjectPermissions Hook**

```typescript
// frontend/src/extensions/project/hooks/useProjectPermissions.ts

import { useQuery } from "@tanstack/react-query";
import * as projectApi from "../api";
import { getVisibleTabs, getDefaultTab } from "../tabRegistry";
import type { TabConfig } from "../tabRegistry";

export function useProjectPermissions(projectId: string, stage: number) {
  const { data, isLoading } = useQuery({
    queryKey: ["project-permissions", projectId],
    queryFn: () => projectApi.getMyPermissions(projectId),
    staleTime: 5 * 60 * 1000,
    enabled: !!projectId,
  });

  const permissions = data?.permissions ?? [];
  const role = data?.role ?? null;
  const can = (action: string) => permissions.includes(action);

  const visibleTabs: TabConfig[] = getVisibleTabs(stage, permissions, role);
  const defaultTab = getDefaultTab(stage, permissions, role);

  return {
    role,
    permissions,
    can,
    defaultTab,
    visibleTabs,
    isLoading,
  };
}
```

- [ ] **Step 5: 运行前端类型检查**

Run: `cd frontend && pnpm typecheck`
Expected: 无类型错误

- [ ] **Step 6: 提交**

```bash
cd frontend
git add src/extensions/project/types.ts src/extensions/project/api.ts src/extensions/project/tabRegistry.ts src/extensions/project/hooks/useProjectPermissions.ts
git commit -m "feat(project): add permission types, API, tab registry, and useProjectPermissions hook"
```

---

### Task 7: 重构 ProjectWorkspace + WorkspaceTabs

**Files:**
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`
- Modify: `frontend/src/extensions/project/components/WorkspaceTabs.tsx`

- [ ] **Step 1: 重构 WorkspaceTabs 支持动态 Tab 列表**

将 `WorkspaceTabs.tsx` 重写为：

```typescript
"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { TabConfig } from "../tabRegistry";

export type WorkspaceTab = string;

interface WorkspaceTabsProps {
  projectId: string;
  currentTab: WorkspaceTab;
  tabs: TabConfig[];
}

const ICON_MAP: Record<string, string> = {
  Target: "🎯",
  BarChart3: "📊",
  Kanban: "📋",
  FileText: "📝",
  Users: "👥",
  CheckCircle: "✅",
  Bot: "🤖",
};

export function WorkspaceTabs({ projectId, currentTab, tabs }: WorkspaceTabsProps) {
  return (
    <nav className="flex gap-1 border-b">
      {tabs.map((tab) => (
        <Link
          key={tab.id}
          href={`/projects/${projectId}?tab=${tab.id}`}
          className={cn(
            "px-3 py-2 text-sm border-b-2 transition-colors",
            currentTab === tab.id
              ? "border-primary text-primary font-medium"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          {ICON_MAP[tab.icon] ?? ""} {tab.label}
        </Link>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: 重构 ProjectWorkspace 使用权限 Hook**

重写 `ProjectWorkspace.tsx` 核心逻辑。保留原有的项目加载和错误处理，替换 Tab 渲染逻辑：

关键变更点：
1. 导入 `useProjectPermissions` 和 `getDefaultTab`
2. 用 `useProjectPermissions(projectId, stage)` 获取权限
3. 用 `visibleTabs` 替代硬编码的 `BASE_TABS`
4. 默认 Tab 由权限决定，而非硬编码
5. 各 Tab 组件传入 `can()` 函数控制内部操作

```typescript
// ProjectWorkspace.tsx 关键变更（非完整文件，仅展示变更模式）

// 新增导入
import { useProjectPermissions } from "./hooks/useProjectPermissions";
import { getDefaultTab } from "./tabRegistry";

// 在组件内部（替换原有 Tab 逻辑）
const { role, can, visibleTabs, defaultTab, isLoading: permissionsLoading } =
  useProjectPermissions(projectId, project?.currentStage ?? 0);

// 默认 Tab 选择
const [activeTab, setActiveTab] = useState<string>("");

useEffect(() => {
  if (!permissionsLoading && visibleTabs.length > 0) {
    const urlTab = searchParams.get("tab");
    if (urlTab && visibleTabs.find((t) => t.id === urlTab)) {
      setActiveTab(urlTab);
    } else {
      setActiveTab(defaultTab);
    }
  }
}, [permissionsLoading, visibleTabs, defaultTab, searchParams]);

// Tab 渲染
<WorkspaceTabs
  projectId={projectId}
  currentTab={activeTab}
  tabs={visibleTabs}
/>

// 内容区域
{activeTab === "my-workspace" && <MemberWorkspace can={can} role={role} />}
{activeTab === "dashboard" && <DashboardTab />}
{activeTab === "kanban" && <KanbanBoard can={can} role={role} />}
{activeTab === "outline" && <OutlineTab readOnly={!can("outline:edit")} />}
{activeTab === "members" && <MembersTab canManage={can("member:add")} />}
{activeTab === "approval" && <ApprovalTab can={can} role={role} />}
{activeTab === "ai-tools" && <AiToolsTab can={can} />}
```

- [ ] **Step 3: 运行前端类型检查**

Run: `cd frontend && pnpm typecheck`
Expected: 无类型错误

- [ ] **Step 4: 提交**

```bash
cd frontend
git add src/extensions/project/ProjectWorkspace.tsx src/extensions/project/components/WorkspaceTabs.tsx
git commit -m "feat(project): refactor workspace to use permission-driven tab visibility"
```

---

### Task 8: 成员工作台 MemberWorkspace 重构

**Files:**
- Modify: `frontend/src/extensions/project/components/MemberWorkspace.tsx`

- [ ] **Step 1: 重构 MemberWorkspace 展示个人章节视图**

MemberWorkspace 应展示当前用户被分配的章节，按状态分组（待处理/进行中/已完成），每个章节带操作按钮（受权限控制）。

核心逻辑：
1. 从 project 对象中过滤 `assignedTo === currentUserId` 的章节
2. 按状态分组显示
3. 操作按钮根据 `can()` 控制显隐

```typescript
// MemberWorkspace.tsx 核心结构

interface MemberWorkspaceProps {
  can: (action: string) => boolean;
  role: string | null;
}

export function MemberWorkspace({ can, role }: MemberWorkspaceProps) {
  // 从 ProjectWorkspace 通过 Context 或 props 获取 project 和 currentUser
  // 过滤 assignedTo === currentUser.id 的章节
  // 按 status 分组：pending/rejected → "待处理", writing/editing/draft → "进行中", completed → "已完成"
  // 每个章节显示：标题、字数进度、状态、操作按钮
  // 操作按钮：can("ai:start_editing") → "编辑"按钮, can("ai:toolbox") → "AI辅助"按钮
}
```

具体实现根据现有 `MemberWorkspace.tsx` 的结构进行适配，保留已有样式，添加权限控制。

- [ ] **Step 2: 运行前端类型检查**

Run: `cd frontend && pnpm typecheck`

- [ ] **Step 3: 提交**

```bash
cd frontend
git add src/extensions/project/components/MemberWorkspace.tsx
git commit -m "feat(project): refactor MemberWorkspace with permission-controlled chapter view"
```

---

### Task 9: 审核流程前端 — ApprovalTab 重构

**Files:**
- Modify: `frontend/src/extensions/project/components/ApprovalTab.tsx`

- [ ] **Step 1: 重构 ApprovalTab**

审核 Tab 需要三种视图模式：

**经理视图**（`can("approval:submit")` 且 stage < 5）：
- 「提交审核」按钮 → 弹出对话框配置审核链
- 审核链配置：从成员列表中选择审核人，拖拽排序

**经理视图**（stage === 5）：
- 审核进度可视化
- 「撤回审核」按钮

**审核人/批准人视图**（当前步骤的指定人）：
- 审核进度可视化
- 章节内容预览
- 「通过」和「退回」按钮 + 意见输入框

**其他角色视图**：
- 只读审核进度可视化

使用 `getApprovalStatus` API 获取审核状态，`approvalAction` API 执行审核动作。

```typescript
// ApprovalTab.tsx 核心结构

interface ApprovalTabProps {
  can: (action: string) => boolean;
  role: string | null;
}

export function ApprovalTab({ can, role }: ApprovalTabProps) {
  const { projectId } = useParams();
  const { data: approvalStatus } = useQuery({
    queryKey: ["approval-status", projectId],
    queryFn: () => getApprovalStatus(projectId),
    enabled: !!projectId,
  });

  // 判断当前用户是否为某步骤的指定审核人
  const isDesignatedReviewer = (step: ApprovalWorkflowWithRecords) =>
    step.reviewerId === currentUserId && step.status === "pending";

  // 渲染逻辑：根据 can() 和 isDesignatedReviewer 决定显示内容
}
```

- [ ] **Step 2: 运行前端类型检查**

Run: `cd frontend && pnpm typecheck`

- [ ] **Step 3: 提交**

```bash
cd frontend
git add src/extensions/project/components/ApprovalTab.tsx
git commit -m "feat(project): refactor ApprovalTab with role-based approval UI"
```

---

### Task 10: 其他 Tab 权限控制 + 集成测试

**Files:**
- Modify: `frontend/src/extensions/project/components/MembersTab.tsx`
- Modify: `frontend/src/extensions/project/components/KanbanBoard.tsx`
- Modify: `frontend/src/extensions/project/components/AiToolsTab.tsx`

- [ ] **Step 1: MembersTab 权限控制**

修改 `MembersTab` 组件，接收 `canManage` prop，当 `canManage === false` 时隐藏「添加成员」和「移除成员」按钮。

- [ ] **Step 2: KanbanBoard 权限控制**

修改 `KanbanBoard` 组件，接收 `can` 和 `role` props：
- 只有 `can("chapter:status")` 的用户可以拖拽卡片改变状态（manager）
- 非 manager 只能看到自己被分配的卡片高亮，其他卡片可查看但不可拖拽

- [ ] **Step 3: AiToolsTab 权限控制**

AiToolsTab 本身已在 Tab 注册表中被 `ai:toolbox` 权限过滤（无权限的角色的看不到此 Tab）。内部无需额外权限控制。

- [ ] **Step 4: 运行完整前端类型检查和 lint**

Run: `cd frontend && pnpm typecheck && pnpm lint`

- [ ] **Step 5: 提交**

```bash
cd frontend
git add src/extensions/project/components/MembersTab.tsx src/extensions/project/components/KanbanBoard.tsx
git commit -m "feat(project): add permission controls to MembersTab and KanbanBoard"
```

---

### Task 11: 端到端手动测试

- [ ] **Step 1: 启动开发环境**

Run: `make dev` 或 `make docker-start`

- [ ] **Step 2: 测试权限矩阵**

1. 创建项目（自动成为 manager）
2. 添加成员（editor、writer、reviewer、approver 角色）
3. 以不同角色登录，验证：
   - manager 看到所有 Tab，默认进入仪表盘
   - editor/writer 默认进入「我的工作台」，只能操作自己被分配的章节
   - reviewer/approver 默认进入看板，只能查看
   - 无权限操作返回 403

- [ ] **Step 3: 测试审核流程**

1. 以 manager 身份提交审核，配置审核链（指定 reviewer 和 approver）
2. 以 reviewer 身份执行审核（通过/退回）
3. 验证退回时项目回到 Stage 4
4. 验证全部通过时项目进入 Stage 6

- [ ] **Step 4: 测试前端 Tab 可见性**

验证每个角色在各个 Stage 看到的 Tab 列表与设计一致。

- [ ] **Step 5: 修复发现的问题并提交**

```bash
git add -A
git commit -m "fix(project): address issues found during e2e testing"
```
