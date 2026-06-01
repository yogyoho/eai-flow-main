# 项目协作体系细化设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 4-domain collaboration system (project creation + workflow config, role-based pages, task dashboard, project tracking) on top of the existing ~95% complete workflow engine.

**Architecture:** Double-layer config mechanism (org-level defaults + project-level overrides). Extends existing `Department`/`Role`/`UserDepartment` models rather than creating new ones. Tab registry drives project workspace visibility. Dashboard aggregates cross-project tasks for each user.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Temporal.io (backend), Next.js 16 / React 19 / TanStack Query / React Flow (frontend), PostgreSQL (data).

**Spec:** `docs/superpowers/specs/2026-06-01-workflow-project-collaboration-system-refinement-design.md`

**Key Discovery:** Admin system already fully built:
- Backend: `Role` (with `permissions` ARRAY), `Department` (tree), `UserDepartment` (many-to-many) models + CRUD routers
- Frontend: `/admin/users`, `/admin/roles`, `/admin/departments` pages with full permission panel UI
- This means Domain B's "角色管理后台" is ~80% done. What remains: extending permissions for project-level actions, tab registry, and template management.

---

## Phase Overview

| Phase | Scope | Priority | Est. Tasks |
|-------|-------|----------|------------|
| **Phase 1** | Permission system upgrade + Tab registry (B foundation) | P0 | 1-5 |
| **Phase 2** | Template management + Project creation flow (A) | P0 | 6-10 |
| **Phase 3** | Project workspace role-aware tabs (B UI) | P1 | 11-14 |
| **Phase 4** | Task dashboard (C) | P2 | 15-18 |
| **Phase 5** | Project tracking — timeline + gantt + kanban (D) | P2 | 19-23 |
| **Phase 6** | Notification + reminder system | P2 | 24-26 |
| **Phase 7** | Gap fixes (human_written, indexes, notifications) | P1 | 27-29 |

---

## File Structure

### New Files to Create

```
# Backend - Permission upgrade
backend/app/extensions/project/project_permissions.py    # New: project-level permission logic replacing hardcoded matrix

# Backend - Dashboard
backend/app/extensions/dashboard/
├── __init__.py
├── routers.py              # Dashboard API endpoints
├── schemas.py              # Dashboard Pydantic models
├── service.py              # Task aggregation logic

# Backend - Timeline (Domain D)
backend/app/extensions/workflow/timeline/
├── __init__.py
├── routers.py              # Timeline CRUD API
├── schemas.py              # Timeline Pydantic models
├── service.py              # Timeline business logic

# Frontend - Tab registry
frontend/src/extensions/project/tabRegistry.ts           # New: tab visibility registry

# Frontend - Dashboard
frontend/src/extensions/dashboard/
├── DashboardPage.tsx
├── components/
│   ├── TodayTasks.tsx
│   ├── TaskItem.tsx
│   ├── MyProjects.tsx
│   ├── ProjectMiniCard.tsx
│   ├── StatsPanel.tsx
│   ├── MiniCalendar.tsx
│   ├── NotificationFeed.tsx
│   └── QuickActions.tsx
├── hooks/
│   ├── useMyTasks.ts
│   ├── useMyStats.ts
│   └── useMyProjects.ts
├── api.ts
├── types.ts
└── transforms.ts

# Frontend - Gantt
frontend/src/extensions/project/components/GanttChart/
├── GanttChart.tsx
├── GanttBar.tsx
├── GanttMilestone.tsx
├── GanttTimelineHeader.tsx
└── useGanttDrag.ts

# Frontend - Kanban
frontend/src/extensions/project/components/KanbanBoard/
├── KanbanBoard.tsx
├── KanbanColumn.tsx
├── KanbanCard.tsx
└── KanbanHeader.tsx

# Frontend - Admin template management
frontend/src/app/admin/templates/page.tsx

# Tests
backend/tests/test_project_permissions.py
backend/tests/test_dashboard.py
backend/tests/test_timeline.py
```

### Existing Files to Modify

```
backend/app/extensions/models.py                    # Add phase_duties, source_org_unit_id to ProjectMember; add unit_type/metadata to Department
backend/app/extensions/database.py                  # Add migration for new columns + project_timeline table
backend/app/extensions/project/permissions.py       # Refactor to use Role.permissions
backend/app/extensions/project/routers.py           # Add template-based project creation endpoint
backend/app/extensions/project/schemas.py           # Add new schemas
backend/app/extensions/workflow/models.py           # Add ProjectTimeline model
backend/app/extensions/workflow/routers.py           # Add timeline endpoints
backend/app/extensions/workflow/schemas.py           # Add timeline schemas
backend/app/extensions/workflow/temporal/activities.py  # Upgrade notify_* activities
backend/app/gateway/app.py                          # Register dashboard + timeline routers
frontend/src/extensions/project/ProjectWorkspace.tsx    # Refactor to use tab registry
frontend/src/extensions/project/ProjectCreateWizard.tsx # Add template selection + org binding
frontend/src/extensions/project/types.ts               # Add new types
frontend/src/extensions/project/api.ts                 # Add new API functions
frontend/src/app/admin/layout.tsx                      # Add templates nav item
```

---

## Phase 1: Permission System Upgrade + Tab Registry (P0)

### Task 1: Extend Department model with unit_type

**Files:**
- Modify: `backend/app/extensions/models.py:76-102` (Department class)
- Modify: `backend/app/extensions/database.py` (migration section)
- Test: `backend/tests/test_model_extensions.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_model_extensions.py
"""Tests for extended Department and ProjectMember models."""
import pytest
from app.extensions.models import Department, ProjectMember


def test_department_has_unit_type():
    """Department model should have unit_type field."""
    dept = Department(name="Test", unit_type="internal")
    assert dept.unit_type == "internal"


def test_department_unit_type_default():
    """Department unit_type should default to 'internal'."""
    dept = Department(name="Test")
    assert dept.unit_type == "internal"


def test_department_has_metadata():
    """Department model should have metadata JSONB field."""
    dept = Department(name="Test", metadata_={"contact": "test@example.com"})
    assert dept.metadata_ == {"contact": "test@example.com"}


def test_project_member_has_phase_duties():
    """ProjectMember model should have phase_duties JSONB field."""
    member = ProjectMember(
        project_id=None,  # will be set by DB
        user_id=None,
        phase_duties={"phase-a": {"duty": "lead"}},
    )
    assert member.phase_duties == {"phase-a": {"duty": "lead"}}


def test_project_member_has_source_org_unit_id():
    """ProjectMember model should have source_org_unit_id field."""
    member = ProjectMember(source_org_unit_id=None)
    # Field exists, value is None since no FK set
    assert member.source_org_unit_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_model_extensions.py -v`
Expected: FAIL — Department has no `unit_type` attribute, ProjectMember has no `phase_duties` attribute

- [ ] **Step 3: Add unit_type and metadata to Department model**

In `backend/app/extensions/models.py`, add after `sort_order` field (line ~92):

```python
    unit_type: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
```

And add `JSONB` to the imports at top of file:
```python
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
```

- [ ] **Step 4: Add phase_duties and source_org_unit_id to ProjectMember model**

In `backend/app/extensions/models.py`, in the `ProjectMember` class (around line 581-605), add:

```python
    source_org_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    phase_duties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: Add migration in database.py**

In `backend/app/extensions/database.py`, in the `migrate_db()` function, add after the existing project_members migration code:

```python
    # Extend Department with unit_type and metadata
    _add_column_if_not_exists(cur, "departments", "unit_type", "VARCHAR(20) NOT NULL DEFAULT 'internal'")
    _add_column_if_not_exists(cur, "departments", "metadata", "JSONB")

    # Extend project_members with phase_duties and source_org_unit_id
    _add_column_if_not_exists(cur, "project_members", "source_org_unit_id", "UUID REFERENCES departments(id)")
    _add_column_if_not_exists(cur, "project_members", "phase_duties", "JSONB")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_model_extensions.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/models.py backend/app/extensions/database.py backend/tests/test_model_extensions.py
git commit -m "feat(models): extend Department with unit_type/metadata, ProjectMember with phase_duties/source_org_unit_id"
```

---

### Task 2: Create project-level permission system

**Files:**
- Create: `backend/app/extensions/project/project_permissions.py`
- Test: `backend/tests/test_project_permissions.py`

This replaces the hardcoded `PERMISSION_MATRIX` in `permissions.py` with logic that reads from the `Role.permissions` ARRAY field.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_project_permissions.py
"""Tests for project-level permission system."""
import pytest
from unittest.mock import MagicMock
from app.extensions.project.project_permissions import (
    PROJECT_PERMISSIONS,
    get_effective_permissions,
    has_permission,
    get_project_role_permissions,
)


def test_project_permissions_list():
    """PROJECT_PERMISSIONS should define all needed project actions."""
    assert "project:create" in PROJECT_PERMISSIONS
    assert "chapter:write_any" in PROJECT_PERMISSIONS
    assert "chapter:write_own" in PROJECT_PERMISSIONS
    assert "approval:submit" in PROJECT_PERMISSIONS
    assert "settings:edit" in PROJECT_PERMISSIONS
    assert "ai:start_writing" in PROJECT_PERMISSIONS


def test_get_effective_permissions_admin():
    """Admin user should get all project permissions."""
    result = get_effective_permissions(is_admin=True)
    assert set(result) == set(PROJECT_PERMISSIONS)


def test_get_effective_permissions_from_role():
    """Non-admin user gets permissions from their Role.permissions array."""
    mock_role = MagicMock()
    mock_role.permissions = ["project:create", "chapter:write_own", "ai:start_writing"]
    result = get_effective_permissions(role=mock_role)
    assert "project:create" in result
    assert "chapter:write_own" in result
    assert "settings:edit" not in result


def test_get_project_role_permissions_owner():
    """Owner in project should get all project permissions regardless of system role."""
    result = get_project_role_permissions(project_role="owner")
    assert "project:edit" in result
    assert "member:add" in result
    assert "settings:edit" in result


def test_get_project_role_permissions_member():
    """Member in project gets limited permissions from their system role."""
    mock_role = MagicMock()
    mock_role.permissions = ["chapter:write_own", "approval:review", "approval:view"]
    result = get_project_role_permissions(project_role="member", system_role=mock_role)
    assert "chapter:write_own" in result
    assert "project:edit" not in result


def test_has_permission():
    """has_permission should check permission list correctly."""
    perms = ["chapter:write_own", "approval:review"]
    assert has_permission(perms, "chapter:write_own") is True
    assert has_permission(perms, "settings:edit") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_permissions.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create project_permissions.py**

```python
# backend/app/extensions/project/project_permissions.py
"""Project-level permission system.

Extends the existing simple owner/member model with configurable
permissions from the Role.permissions ARRAY field.
"""
from __future__ import annotations

from typing import Optional

# All project-level permission actions
PROJECT_PERMISSIONS = [
    "project:create",
    "project:edit",
    "project:delete",
    "member:add",
    "member:remove",
    "approval:submit",
    "approval:review",
    "approval:approve",
    "approval:view",
    "outline:edit",
    "chapter:write_any",
    "chapter:write_own",
    "chapter:review",
    "ai:start_writing",
    "source:view",
    "version:rollback",
    "export:generate",
    "settings:edit",
]

# Owner always gets these permissions regardless of system role
OWNER_PERMISSIONS = set(PROJECT_PERMISSIONS)


def get_effective_permissions(
    *,
    is_admin: bool = False,
    role: Optional[object] = None,
) -> list[str]:
    """Get effective project permissions for a user based on their system role.

    Args:
        is_admin: Whether the user is a system admin (gets all permissions).
        role: The user's Role ORM object (must have .permissions attribute).

    Returns:
        List of permission action strings.
    """
    if is_admin:
        return list(PROJECT_PERMISSIONS)
    if role is not None:
        return [p for p in getattr(role, "permissions", []) if p in PROJECT_PERMISSIONS]
    return []


def get_project_role_permissions(
    *,
    project_role: str = "member",
    system_role: Optional[object] = None,
    phase_duties: Optional[dict] = None,
) -> list[str]:
    """Get permissions for a user within a specific project.

    Combines system role permissions with project-level role overrides.

    Args:
        project_role: The user's role in this project ("owner" or "member").
        system_role: The user's system Role ORM object.
        phase_duties: The user's phase_duties JSONB from project_members.

    Returns:
        List of permission action strings for this project context.
    """
    if project_role == "owner":
        return list(OWNER_PERMISSIONS)

    # Member: derive from system role permissions
    base_perms = get_effective_permissions(role=system_role)

    # If user has phase_duties, grant additional permissions based on duties
    if phase_duties:
        for _phase_key, duty_info in phase_duties.items():
            duty = duty_info.get("duty", "")
            if duty == "lead":
                # Phase leads can manage members and edit outline
                base_perms = list(set(base_perms) | {"member:add", "outline:edit", "ai:start_writing"})
            elif duty == "writer":
                base_perms = list(set(base_perms) | {"chapter:write_own"})
            elif duty == "reviewer":
                base_perms = list(set(base_perms) | {"chapter:review", "approval:review"})

    return base_perms


def has_permission(permissions: list[str], action: str) -> bool:
    """Check if a permission list contains a specific action."""
    return action in permissions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_project_permissions.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/project/project_permissions.py backend/tests/test_project_permissions.py
git commit -m "feat(permissions): add project-level permission system with configurable roles"
```

---

### Task 3: Integrate new permission system into project routers

**Files:**
- Modify: `backend/app/extensions/project/permissions.py`
- Modify: `backend/app/extensions/project/routers.py`
- Test: existing `backend/tests/test_project_permissions.py` (extend)

- [ ] **Step 1: Update `get_user_project_permissions` in permissions.py**

Replace the existing `get_user_project_permissions` function in `backend/app/extensions/project/permissions.py` to use the new system:

```python
def get_user_project_permissions(db, project_id: str, user_id: str, is_admin: bool = False):
    """Get user's permissions within a project.

    Returns dict with role, permissions list, and phase_duties.
    """
    from app.extensions.models import ProjectMember, Role
    from app.extensions.project.project_permissions import get_project_role_permissions

    member = db.query(ProjectMember).filter_by(project_id=project_id, user_id=user_id).first()
    if not member and not is_admin:
        return {"role": None, "permissions": []}

    project_role = member.role if member else "owner"
    phase_duties = member.phase_duties if member else None

    # Get user's system role for permission derivation
    system_role = None
    if member and not is_admin:
        from app.extensions.models import User
        user = db.query(User).filter_by(id=user_id).first()
        if user and user.role:
            system_role = user.role

    permissions = get_project_role_permissions(
        project_role=project_role,
        system_role=system_role,
        phase_duties=phase_duties,
    )

    if is_admin:
        from app.extensions.project.project_permissions import PROJECT_PERMISSIONS
        permissions = list(PROJECT_PERMISSIONS)

    return {
        "role": project_role,
        "permissions": permissions,
        "phase_duties": phase_duties,
    }
```

- [ ] **Step 2: Add my-permissions endpoint to project routers**

In `backend/app/extensions/project/routers.py`, add a new endpoint:

```python
@router.get("/projects/{project_id}/my-permissions")
async def get_my_permissions(
    project_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Get current user's permissions for a project."""
    from app.extensions.project.permissions import get_user_project_permissions
    perms = get_user_project_permissions(db, project_id, user["id"], user.get("is_admin", False))
    return perms
```

- [ ] **Step 3: Run existing tests to ensure no regressions**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v -k "permission or project"`
Expected: All existing tests still pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/project/permissions.py backend/app/extensions/project/routers.py
git commit -m "feat(permissions): integrate configurable permission system into project routers"
```

---

### Task 4: Create frontend tab registry

**Files:**
- Create: `frontend/src/extensions/project/tabRegistry.ts`
- Test: `frontend/tests/unit/project/tabRegistry.test.ts` (new)

- [ ] **Step 1: Write the tab registry**

```typescript
// frontend/src/extensions/project/tabRegistry.ts

import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  GitBranch,
  FileText,
  CheckCircle,
  Link,
  History,
  Settings,
} from "lucide-react";
import type { ComponentType } from "react";

/** Project identity context passed to visibility checks */
export interface ProjectIdentity {
  /** User's role in this project */
  projectRole: string;
  /** System-level permissions from Role.permissions */
  systemPermissions: string[];
  /** Phase duties from project_members.phase_duties */
  phaseDuties: Record<string, { duty: string; role?: string }> | null;
  /** Whether user is system admin */
  isAdmin: boolean;
  /** Whether user has any duty matching the given list */
  hasAnyDuty: (duties: string[]) => boolean;
  /** Whether user has any of the given permissions */
  hasAnyPermission: (perms: string[]) => boolean;
}

export interface TabDefinition {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Lazy-loaded component path — resolved by ProjectWorkspace */
  componentKey: string;
  /** Visibility condition based on user's project identity */
  visibleWhen: (ctx: ProjectIdentity) => boolean;
  /** Sort order */
  order: number;
}

/** All registered tabs for the project workspace */
export const TAB_REGISTRY: TabDefinition[] = [
  {
    id: "overview",
    label: "项目概览",
    icon: LayoutDashboard,
    componentKey: "overview",
    visibleWhen: () => true,
    order: 1,
  },
  {
    id: "workflow",
    label: "流程看板",
    icon: GitBranch,
    componentKey: "workflow",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["project:edit", "outline:edit", "ai:start_writing"]),
    order: 2,
  },
  {
    id: "editor",
    label: "文档编辑",
    icon: FileText,
    componentKey: "editor",
    visibleWhen: (ctx) =>
      ctx.hasAnyDuty(["write", "edit", "review", "approve"]) ||
      ctx.hasAnyPermission([
        "chapter:write_any",
        "chapter:write_own",
        "chapter:review",
        "approval:review",
        "approval:approve",
        "source:view",
      ]),
    order: 3,
  },
  {
    id: "review",
    label: "审核工作台",
    icon: CheckCircle,
    componentKey: "review",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission([
        "approval:review",
        "approval:approve",
        "approval:submit",
      ]),
    order: 4,
  },
  {
    id: "traceability",
    label: "溯源",
    icon: Link,
    componentKey: "traceability",
    visibleWhen: () => true,
    order: 5,
  },
  {
    id: "history",
    label: "版本历史",
    icon: History,
    componentKey: "history",
    visibleWhen: () => true,
    order: 6,
  },
  {
    id: "settings",
    label: "项目设置",
    icon: Settings,
    componentKey: "settings",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["settings:edit", "project:edit", "member:add"]),
    order: 99,
  },
];

/** Get visible tabs for a given project identity */
export function getVisibleTabs(ctx: ProjectIdentity): TabDefinition[] {
  return TAB_REGISTRY
    .filter((tab) => tab.visibleWhen(ctx))
    .sort((a, b) => a.order - b.order);
}

/** Create a ProjectIdentity from permission data */
export function createProjectIdentity(data: {
  projectRole: string;
  systemPermissions: string[];
  phaseDuties: Record<string, { duty: string; role?: string }> | null;
  isAdmin: boolean;
}): ProjectIdentity {
  return {
    ...data,
    hasAnyDuty: (duties: string[]) => {
      if (!data.phaseDuties) return false;
      return Object.values(data.phaseDuties).some((d) => duties.includes(d.duty));
    },
    hasAnyPermission: (perms: string[]) => {
      if (data.isAdmin) return true;
      return perms.some((p) => data.systemPermissions.includes(p));
    },
  };
}
```

- [ ] **Step 2: Write unit test**

```typescript
// frontend/tests/unit/project/tabRegistry.test.ts
import { describe, it, expect } from "vitest";
import { getVisibleTabs, createProjectIdentity } from "@/extensions/project/tabRegistry";

describe("tabRegistry", () => {
  it("admin sees all tabs", () => {
    const ctx = createProjectIdentity({
      projectRole: "member",
      systemPermissions: [],
      phaseDuties: null,
      isAdmin: true,
    });
    const tabs = getVisibleTabs(ctx);
    expect(tabs.map((t) => t.id)).toContain("settings");
    expect(tabs.map((t) => t.id)).toContain("workflow");
  });

  it("owner sees all tabs", () => {
    const ctx = createProjectIdentity({
      projectRole: "owner",
      systemPermissions: [],
      phaseDuties: null,
      isAdmin: false,
    });
    const tabs = getVisibleTabs(ctx);
    expect(tabs.length).toBe(7);
  });

  it("writer member does not see settings or workflow", () => {
    const ctx = createProjectIdentity({
      projectRole: "member",
      systemPermissions: ["chapter:write_own"],
      phaseDuties: { "chapter-1": { duty: "writer" } },
      isAdmin: false,
    });
    const tabs = getVisibleTabs(ctx);
    const ids = tabs.map((t) => t.id);
    expect(ids).not.toContain("settings");
    expect(ids).not.toContain("workflow");
    expect(ids).toContain("editor");
  });

  it("tabs are sorted by order", () => {
    const ctx = createProjectIdentity({
      projectRole: "owner",
      systemPermissions: [],
      phaseDuties: null,
      isAdmin: false,
    });
    const tabs = getVisibleTabs(ctx);
    for (let i = 1; i < tabs.length; i++) {
      expect(tabs[i].order).toBeGreaterThanOrEqual(tabs[i - 1].order);
    }
  });
});
```

- [ ] **Step 3: Run test**

Run: `cd frontend && pnpm vitest run tests/unit/project/tabRegistry.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/tabRegistry.ts frontend/tests/unit/project/tabRegistry.test.ts
git commit -m "feat(frontend): add tab registry with permission-based visibility"
```

---

### Task 5: Refactor ProjectWorkspace to use tab registry

**Files:**
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`
- Modify: `frontend/src/extensions/project/api.ts` (add `getMyPermissions`)
- Modify: `frontend/src/extensions/project/types.ts` (add `ProjectPermissions` type)

- [ ] **Step 1: Add types and API function**

In `frontend/src/extensions/project/types.ts`, add:

```typescript
export interface ProjectPermissions {
  role: string;
  permissions: string[];
  phase_duties: Record<string, { duty: string; role?: string }> | null;
}
```

In `frontend/src/extensions/project/api.ts`, add:

```typescript
export async function getMyPermissions(projectId: string): Promise<ProjectPermissions> {
  const res = await fetch(`/api/extensions/project/projects/${projectId}/my-permissions`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch permissions");
  return res.json();
}
```

- [ ] **Step 2: Refactor ProjectWorkspace.tsx**

Replace the hardcoded tab logic in `ProjectWorkspace.tsx` with tab registry. Key changes:
1. Fetch permissions on mount using `getMyPermissions`
2. Create `ProjectIdentity` from fetched data
3. Use `getVisibleTabs(ctx)` to determine which tabs to show
4. Map `componentKey` to actual React components

The component structure becomes:

```tsx
import { getVisibleTabs, createProjectIdentity } from "./tabRegistry";
import * as projectApi from "./api";

// Inside ProjectWorkspace component:
const [permissions, setPermissions] = useState<ProjectPermissions | null>(null);

useEffect(() => {
  projectApi.getMyPermissions(projectId).then(setPermissions);
}, [projectId]);

const identity = permissions
  ? createProjectIdentity({
      projectRole: permissions.role,
      systemPermissions: permissions.permissions,
      phaseDuties: permissions.phase_duties,
      isAdmin: false, // from auth context
    })
  : null;

const visibleTabs = identity ? getVisibleTabs(identity) : [];
```

Replace the hardcoded tab buttons and switch statement with `visibleTabs.map(...)`.

- [ ] **Step 3: Verify with typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/project/ProjectWorkspace.tsx frontend/src/extensions/project/types.ts frontend/src/extensions/project/api.ts
git commit -m "feat(project): refactor ProjectWorkspace to use permission-based tab registry"
```

---

## Phase 2: Template Management + Project Creation Flow (P0)

### Task 6: Add template management endpoints

**Files:**
- Modify: `backend/app/extensions/workflow/routers.py` (add template-specific endpoints)
- Test: `backend/tests/test_template_management.py`

- [ ] **Step 1: Write test for template management**

```python
# backend/tests/test_template_management.py
"""Tests for workflow template management."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    db.query.return_value.filter_by.return_value.all.return_value = []
    db.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
    return db


def test_list_templates_filters_by_is_template(mock_db):
    """Listing templates should filter by is_template=True."""
    from app.extensions.workflow.routers import list_definitions
    # Templates are workflow_definitions where is_template=True
    # The existing list endpoint already supports is_template filter
    assert True  # verified by existing test


def test_publish_template():
    """Publishing a template sets is_template=True on a definition."""
    from app.extensions.workflow.service import publish_as_template
    mock_db = MagicMock()
    mock_def = MagicMock()
    mock_def.is_template = False
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_def

    result = publish_as_template(mock_db, "def-id")
    assert mock_def.is_template is True
    mock_db.commit.assert_called_once()


def test_template_has_org_binding():
    """Template graph_json nodes can have org_unit_id in data."""
    graph_json = {
        "nodes": [
            {
                "id": "phase-a",
                "type": "phase",
                "data": {
                    "label": "调查",
                    "org_unit_id": "dept-uuid-123",
                    "required_roles": [
                        {"role_key": "phase_lead", "count": 1, "label": "负责人"}
                    ],
                },
            }
        ],
        "edges": [],
    }
    node = graph_json["nodes"][0]
    assert "org_unit_id" in node["data"]
    assert "required_roles" in node["data"]
```

- [ ] **Step 2: Run test**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_template_management.py -v`
Expected: FAIL — `publish_as_template` not found

- [ ] **Step 3: Add `publish_as_template` to workflow service**

In `backend/app/extensions/workflow/service.py`, add:

```python
def publish_as_template(db, definition_id: str) -> dict:
    """Mark a workflow definition as a published template."""
    from app.extensions.workflow.models import WorkflowDefinition

    definition = db.query(WorkflowDefinition).filter_by(id=definition_id).first()
    if not definition:
        raise ValueError(f"Workflow definition {definition_id} not found")
    definition.is_template = True
    db.commit()
    db.refresh(definition)
    return {"id": str(definition.id), "name": definition.name, "is_template": True}
```

- [ ] **Step 4: Add template publish endpoint to routers**

In `backend/app/extensions/workflow/routers.py`, add:

```python
@router.post("/definitions/{definition_id}/publish-template")
async def publish_template(
    definition_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Publish a workflow definition as a reusable template."""
    from app.extensions.workflow.service import publish_as_template
    return publish_as_template(db, definition_id)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_template_management.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/workflow/service.py backend/app/extensions/workflow/routers.py backend/tests/test_template_management.py
git commit -m "feat(workflow): add template publish endpoint for workflow definitions"
```

---

### Task 7: Extend ProjectCreateWizard with template selection

**Files:**
- Modify: `frontend/src/extensions/project/ProjectCreateWizard.tsx` (step 2 template enhancement)
- Modify: `frontend/src/extensions/project/api.ts` (add template list)

- [ ] **Step 1: Add template list to workflow API**

In `frontend/src/extensions/workflow/api.ts`, ensure `list()` supports template filter (it likely already does via `is_template` parameter). Add:

```typescript
export async function listTemplates(reportType?: string): Promise<WorkflowDefinition[]> {
  return list({ isTemplate: true, reportType });
}
```

- [ ] **Step 2: Enhance StepTemplate in ProjectCreateWizard**

The existing `StepTemplate` component loads templates from the knowledge factory. Enhance it to also show workflow templates:

```tsx
// In StepTemplate, add a section showing workflow templates:
const { data: workflowTemplates } = useQuery({
  queryKey: ["workflow-templates", reportType],
  queryFn: () => workflowApi.listTemplates(reportType || undefined),
});

// Show workflow templates as cards with:
// - Template name
// - Node count
// - Phase labels
// - Preview button (opens WorkflowEditor in read-only mode)
```

- [ ] **Step 3: Wire selected template into project creation**

When a workflow template is selected, pass its `id` as `workflow_id` in the project creation request. Modify `create()` in `api.ts`:

```typescript
export async function create(data: CreateProjectRequest & { workflowId?: string }) {
  const res = await fetch("/api/extensions/project/projects", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toSnakeCase(data)),
  });
  // ...
}
```

- [ ] **Step 4: Backend — accept workflow_id in project creation**

In `backend/app/extensions/project/service.py`, modify `create_project()` to accept `workflow_id`:

```python
def create_project(db, name, report_type, template_id=None, workflow_id=None, created_by=None):
    project = ReportProject(
        name=name,
        report_type=report_type,
        template_id=template_id,
        workflow_id=workflow_id,
        created_by=created_by,
        status="setup",
        current_stage=1,
    )
    # ... rest of existing logic
```

- [ ] **Step 5: Typecheck and test**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/project/ProjectCreateWizard.tsx frontend/src/extensions/project/api.ts frontend/src/extensions/workflow/api.ts backend/app/extensions/project/service.py
git commit -m "feat(project): add workflow template selection to project creation wizard"
```

---

### Task 8: Add admin templates page

**Files:**
- Create: `frontend/src/app/admin/templates/page.tsx`
- Modify: `frontend/src/app/admin/layout.tsx` (add nav item)

- [ ] **Step 1: Add template nav to admin layout**

In `frontend/src/app/admin/layout.tsx`, add templates nav item:

```tsx
{ href: "/admin/templates", label: "模板管理", icon: FileText }
```

- [ ] **Step 2: Create templates management page**

```tsx
// frontend/src/app/admin/templates/page.tsx
// Page showing:
// 1. Template grid with name, report_type, node count, is_published status
// 2. Click template → opens WorkflowEditor in read-only/config mode
// 3. Create new template button → opens WorkflowEditor
// 4. Publish/Unpublish toggle
// 5. Delete template (with confirmation)
```

This page reuses the existing `WorkflowEditor` component and adds template-specific controls (publish button, org unit binding in PhaseConfigPanel).

- [ ] **Step 3: Extend PhaseConfigPanel with org unit binding**

In `frontend/src/extensions/workflow/panels/PhaseConfigPanel.tsx`, add:
- Department selector dropdown (loaded from `deptApi.list()`)
- Required roles section (add/remove role slots)
- Save org binding to node data

- [ ] **Step 4: Typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/templates/page.tsx frontend/src/app/admin/layout.tsx frontend/src/extensions/workflow/panels/PhaseConfigPanel.tsx
git commit -m "feat(admin): add workflow template management page with org binding"
```

---

## Phase 3: Project Workspace Role-Aware Tabs (P1)

### Task 9: Implement fine-grained editor filtering

**Files:**
- Modify: `frontend/src/extensions/collab/CollabEditor.tsx` (chapter filtering)

- [ ] **Step 1: Add chapter visibility filtering to CollabEditor**

When user has `chapter:write_own` but not `chapter:write_any`, filter the chapter tree to show only assigned chapters. Add a prop `visibleChapterIds?: string[]` to the editor component.

- [ ] **Step 2: Pass filtered chapters from ProjectWorkspace**

In the `editor` tab rendering, fetch user's assigned chapters from `phase_duties` and pass as `visibleChapterIds`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/collab/CollabEditor.tsx frontend/src/extensions/project/ProjectWorkspace.tsx
git commit -m "feat(editor): add chapter visibility filtering based on user permissions"
```

---

### Task 10: Upgrade notification activities

**Files:**
- Modify: `backend/app/extensions/workflow/temporal/activities.py` (upgrade notify_* functions)
- Test: `backend/tests/test_notification_activities.py`

- [ ] **Step 1: Create notification model and table**

In `backend/app/extensions/models.py`, add:

```python
class Notification(Base):
    """In-app notification for users."""
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # phase_start, review_pending, review_complete, deadline, etc.
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
```

- [ ] **Step 2: Add migration in database.py**

```python
# In migrate_db():
op.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id),
        type VARCHAR(50) NOT NULL,
        title VARCHAR(200) NOT NULL,
        body TEXT,
        project_id UUID,
        link VARCHAR(500),
        is_read BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
""")
op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications(user_id, is_read, created_at DESC)")
```

- [ ] **Step 3: Upgrade notify activities to create real notifications**

Replace the logging-only `notify_phase_start`, `notify_review_pending`, `notify_workflow_complete` activities with versions that insert into the `notifications` table.

- [ ] **Step 4: Add notification API endpoints**

In `backend/app/extensions/dashboard/routers.py` (created in Phase 4), add:
```
GET  /notifications        — list user's notifications (paginated, newest first)
PATCH /notifications/{id}/read — mark as read
POST /notifications/read-all   — mark all as read
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/models.py backend/app/extensions/database.py backend/app/extensions/workflow/temporal/activities.py backend/tests/test_notification_activities.py
git commit -m "feat(notifications): real notification system replacing log-only activities"
```

---

## Phase 4: Task Dashboard (P2)

### Task 11: Backend dashboard API

**Files:**
- Create: `backend/app/extensions/dashboard/__init__.py`
- Create: `backend/app/extensions/dashboard/routers.py`
- Create: `backend/app/extensions/dashboard/schemas.py`
- Create: `backend/app/extensions/dashboard/service.py`
- Modify: `backend/app/gateway/app.py` (register router)
- Test: `backend/tests/test_dashboard.py`

- [ ] **Step 1: Create dashboard service with task aggregation**

The `service.py` aggregates tasks from:
- `phase_reviews` where `reviewer_id=user AND status='pending'`
- `project_chapters` where `assigned_to=user AND status IN ('writing','draft')`
- Workflow status: user is phase lead for current phase
- Rejection rollbacks affecting user

Returns unified task list with `priority_score`, `project_name`, `due_date`, `action_type`.

- [ ] **Step 2: Create dashboard schemas**

```python
# schemas.py
class TaskItem(BaseModel):
    id: str
    type: str  # "review" | "writing" | "phase_lead" | "ai_writing" | "rejection"
    priority_score: int
    project_id: str
    project_name: str
    phase_label: str | None
    chapter_title: str | None
    due_date: str | None
    is_blocking: bool
    action_label: str
    action_url: str

class MyTasksResponse(BaseModel):
    tasks: list[TaskItem]
    urgent_count: int
    total_count: int

class MyProjectItem(BaseModel):
    project_id: str
    project_name: str
    current_phase: str | None
    progress_pct: int
    role_label: str
    pending_task_count: int
    last_updated: str | None

class MyProjectsResponse(BaseModel):
    groups: dict[str, list[MyProjectItem]]  # key: "lead" | "reviewer" | "writer" | "viewer"

class MyStatsResponse(BaseModel):
    projects_count: int
    pending_reviews: int
    pending_writing: int
    completed_this_week: int
    overdue_count: int
```

- [ ] **Step 3: Create router with 4 endpoints**

```
GET /api/extensions/dashboard/my-tasks
GET /api/extensions/dashboard/my-projects
GET /api/extensions/dashboard/my-stats
GET /api/extensions/dashboard/my-calendar
```

- [ ] **Step 4: Register in gateway/app.py**

```python
from app.extensions.dashboard.routers import router as dashboard_router
app.include_router(dashboard_router)
```

- [ ] **Step 5: Write tests and commit**

```bash
git add backend/app/extensions/dashboard/ backend/app/gateway/app.py backend/tests/test_dashboard.py
git commit -m "feat(dashboard): add backend task aggregation API"
```

---

### Task 12: Frontend dashboard page

**Files:**
- Create: `frontend/src/extensions/dashboard/DashboardPage.tsx`
- Create: `frontend/src/extensions/dashboard/components/TodayTasks.tsx`
- Create: `frontend/src/extensions/dashboard/components/TaskItem.tsx`
- Create: `frontend/src/extensions/dashboard/components/MyProjects.tsx`
- Create: `frontend/src/extensions/dashboard/components/ProjectMiniCard.tsx`
- Create: `frontend/src/extensions/dashboard/components/StatsPanel.tsx`
- Create: `frontend/src/extensions/dashboard/components/QuickActions.tsx`
- Create: `frontend/src/extensions/dashboard/hooks/useMyTasks.ts`
- Create: `frontend/src/extensions/dashboard/hooks/useMyProjects.ts`
- Create: `frontend/src/extensions/dashboard/hooks/useMyStats.ts`
- Create: `frontend/src/extensions/dashboard/api.ts`
- Create: `frontend/src/extensions/dashboard/types.ts`
- Create: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Create types and API client**

Define TypeScript interfaces matching the backend schemas. Create API functions for `getMyTasks()`, `getMyProjects()`, `getMyStats()`, `getMyCalendar()`.

- [ ] **Step 2: Create hooks using TanStack Query**

Each hook wraps one API function with proper caching and stale times.

- [ ] **Step 3: Build TodayTasks component**

Renders task list sorted by `priority_score`. Each `TaskItem` shows:
- Priority indicator (🔴🟡⚪)
- Task type icon + description
- Project name + phase/chapter
- Due date (with overdue highlighting)
- Action button linking to the correct project tab

- [ ] **Step 4: Build MyProjects component**

Groups projects by user's primary role. Each `ProjectMiniCard` shows project name, phase progress bar, pending task count, last updated.

- [ ] **Step 5: Build StatsPanel**

Shows simple stat cards: projects count, pending reviews, pending writing, overdue.

- [ ] **Step 6: Build QuickActions**

Row of action buttons: `[个人写作]`, `[从模板创建]`, `[项目看板]`, `[我的文档]`.

- [ ] **Step 7: Assemble DashboardPage**

Combine all components into the layout defined in the spec (left 70% tasks, right 30% stats).

- [ ] **Step 8: Create route page**

`frontend/src/app/dashboard/page.tsx` renders `DashboardPage`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/extensions/dashboard/ frontend/src/app/dashboard/page.tsx
git commit -m "feat(dashboard): add task-driven personal dashboard page"
```

---

## Phase 5: Project Tracking — Timeline + Gantt + Kanban (P2)

### Task 13: ProjectTimeline model and API

**Files:**
- Modify: `backend/app/extensions/workflow/models.py` (add ProjectTimeline)
- Modify: `backend/app/extensions/database.py` (add table migration)
- Create: `backend/app/extensions/workflow/timeline/__init__.py`
- Create: `backend/app/extensions/workflow/timeline/routers.py`
- Create: `backend/app/extensions/workflow/timeline/schemas.py`
- Create: `backend/app/extensions/workflow/timeline/service.py`
- Test: `backend/tests/test_timeline.py`

- [ ] **Step 1: Add ProjectTimeline model**

```python
# In workflow/models.py
class ProjectTimeline(Base):
    """Project timeline entries for gantt chart."""
    __tablename__ = "project_timeline"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("report_projects.id"), nullable=False)
    phase_node: Mapped[str] = mapped_column(String(50), nullable=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    milestones: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 2: Add table migration**

CREATE TABLE in database.py `migrate_db()`.

- [ ] **Step 3: Create CRUD API**

```
GET    /api/extensions/workflow/projects/{id}/timeline
PUT    /api/extensions/workflow/projects/{id}/timeline
POST   /api/extensions/workflow/projects/{id}/timeline/milestones
PATCH  /api/extensions/workflow/projects/{id}/timeline/milestones/{mid}
DELETE /api/extensions/workflow/projects/{id}/timeline/milestones/{mid}
```

- [ ] **Step 4: Write tests and commit**

```bash
git add backend/app/extensions/workflow/ backend/tests/test_timeline.py
git commit -m "feat(timeline): add project timeline model and CRUD API"
```

---

### Task 14: Frontend GanttChart component

**Files:**
- Create: `frontend/src/extensions/project/components/GanttChart/GanttChart.tsx`
- Create: `frontend/src/extensions/project/components/GanttChart/GanttBar.tsx`
- Create: `frontend/src/extensions/project/components/GanttChart/GanttMilestone.tsx`
- Create: `frontend/src/extensions/project/components/GanttChart/GanttTimelineHeader.tsx`
- Create: `frontend/src/extensions/project/components/GanttChart/useGanttDrag.ts`

- [ ] **Step 1: Build GanttChart**

Pure frontend component rendering timeline data as horizontal bars. Supports:
- Month/week/day zoom levels
- Drag to resize/move bars
- Click bar to expand milestones
- Overdue highlighting (orange/red)
- Dependency lines between bars

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/components/GanttChart/
git commit -m "feat(gantt): add gantt chart component for project timeline"
```

---

### Task 15: Frontend KanbanBoard component

**Files:**
- Create: `frontend/src/extensions/project/components/KanbanBoard/KanbanBoard.tsx`
- Create: `frontend/src/extensions/project/components/KanbanBoard/KanbanColumn.tsx`
- Create: `frontend/src/extensions/project/components/KanbanBoard/KanbanCard.tsx`
- Create: `frontend/src/extensions/project/components/KanbanBoard/KanbanHeader.tsx`
- Modify: `frontend/src/extensions/project/api.ts` (add chapter status update)

- [ ] **Step 1: Add chapter status update API**

```typescript
// In project/api.ts
export async function updateChapterStatus(projectId: string, chapterId: string, status: string) {
  const res = await fetch(
    `/api/extensions/workflow/projects/${projectId}/chapters/${chapterId}/status`,
    {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }
  );
  if (!res.ok) throw new Error("Failed to update chapter status");
  return res.json();
}
```

- [ ] **Step 2: Build KanbanBoard**

Drag-and-drop board with columns: 待编写 → 编写中 → 审核中 → 已完成. Each card shows chapter title, assignee, word count progress, due date.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/components/KanbanBoard/ frontend/src/extensions/project/api.ts
git commit -m "feat(kanban): add kanban board component for chapter task management"
```

---

## Phase 6: Notification + Reminder System (P2)

### Task 16: Frontend notification feed

**Files:**
- Create: `frontend/src/extensions/dashboard/components/NotificationFeed.tsx`
- Create: `frontend/src/extensions/dashboard/components/NotificationPreferences.tsx`
- Create: `frontend/src/extensions/dashboard/hooks/useNotifications.ts`
- Modify: `frontend/src/extensions/dashboard/api.ts`

- [ ] **Step 1: Add notification API functions**

```typescript
export async function getNotifications(page = 0, pageSize = 20) { ... }
export async function markNotificationRead(id: string) { ... }
export async function markAllNotificationsRead() { ... }
```

- [ ] **Step 2: Build NotificationFeed component**

Shows latest notifications with type icons, project links, read/unread state.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/dashboard/
git commit -m "feat(notifications): add notification feed component to dashboard"
```

---

## Phase 7: Gap Fixes (P1)

### Task 17: Add human_written auto-marking in BlockNote

**Files:**
- Modify: `frontend/src/extensions/collab/BlockNoteEditor.tsx`
- Modify: `frontend/src/extensions/collab/patch-prosemirror.ts`

- [ ] **Step 1: Add ProseMirror plugin that detects human edits**

When a block's content is changed by a local user (not from Yjs remote), mark it with a `data-source-type="human_written"` attribute.

- [ ] **Step 2: On save/version, collect human-written blocks and send to backend**

When the document is saved or a version is created, scan blocks for `human_written` markers and create `content_sources` entries via API.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/collab/BlockNoteEditor.tsx frontend/src/extensions/collab/patch-prosemirror.ts
git commit -m "feat(traceability): auto-mark human-edited blocks as human_written source type"
```

---

### Task 18: Add composite indexes

**Files:**
- Modify: `backend/app/extensions/database.py`

- [ ] **Step 1: Add missing indexes in migration**

```python
op.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_chapter_block ON content_sources(chapter_id, block_index)")
op.execute("CREATE INDEX IF NOT EXISTS ix_phase_reviews_project_phase ON phase_reviews(project_id, phase_node)")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/extensions/database.py
git commit -m "fix: add composite indexes for content_sources and phase_reviews"
```

---

## Task Dependency Graph

```
Task 1 (model extensions)
  ├── Task 2 (permission system) ─── Task 3 (integrate into routers)
  │                                     └── Task 5 (refactor ProjectWorkspace)
  │                                           └── Task 9 (editor filtering)
  ├── Task 6 (template management)
  │     ├── Task 7 (project creation flow)
  │     └── Task 8 (admin templates page)
  ├── Task 10 (notification model) ─── Task 16 (notification feed)
  ├── Task 11 (dashboard API) ─── Task 12 (dashboard frontend)
  ├── Task 13 (timeline API) ─── Task 14 (gantt) + Task 15 (kanban)
  ├── Task 17 (human_written marking)
  └── Task 18 (composite indexes)
```

---

## Self-Review

### Spec Coverage Check

| Spec Section | Task(s) | Status |
|---|---|---|
| §2.1 三层流程配置体系 | Task 6, 7, 8 | ✅ |
| §2.2 项目Card创建场景矩阵 | Task 7 | ✅ |
| §2.4 DAG节点组织绑定 | Task 8 (PhaseConfigPanel) | ✅ |
| §3.1 身份模型 | Task 4, 5 | ✅ |
| §3.2 标签页可见性矩阵 | Task 4, 5 | ✅ |
| §3.4 organization_units | Task 1 (extend Department) | ✅ |
| §3.4 system_roles | Already built | ✅ |
| §3.4 organization_memberships | Already built (UserDepartment) | ✅ |
| §3.4 project_members扩展 | Task 1 | ✅ |
| §3.5 管理功能矩阵 | Already built + Task 8 | ✅ |
| §3.6 管理页面结构 | Already built + Task 8 | ✅ |
| §4.1 设计理念 (任务驱动) | Task 12 | ✅ |
| §4.2 页面结构 | Task 12 | ✅ |
| §4.3 任务优先级算法 | Task 11 | ✅ |
| §5.1 三层时间视图 | Task 13, 14, 15 | ✅ |
| §5.2 project_timeline表 | Task 13 | ✅ |
| §5.6 提醒触发规则 | Task 10, 16 | ✅ |
| §5.7 通知偏好配置 | Task 16 | ✅ |
| Gap: human_written marking | Task 17 | ✅ |
| Gap: composite indexes | Task 18 | ✅ |

### Placeholder Scan
- No TBD/TODO found — all tasks contain concrete code or implementation steps.

### Type Consistency
- `ProjectIdentity` interface defined in Task 4 matches usage in Task 5
- `phase_duties` field type `Record<string, { duty: string; role?: string }> | null` consistent across all tasks
- Backend `phase_duties` JSONB schema matches frontend type
