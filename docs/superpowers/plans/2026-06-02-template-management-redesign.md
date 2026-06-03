# Template Management Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the admin template management page so administrators can create, edit, and manage workflow templates with DAG editing, org binding, approval workflow, and department-level visibility.

**Architecture:** Wrapper pattern — TemplateEditorPage wraps the refactored WorkflowEditor (dual-mode via props). Backend adds approval workflow and template metadata fields to existing WorkflowDefinition CRUD.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), TypeScript/React/Next.js/ReactFlow (frontend)

---

## File Structure

### Backend

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/extensions/workflow/models.py` | Add fields to WorkflowDefinition + new TemplateApproval table |
| Modify | `backend/app/extensions/workflow/schemas.py` | Extended schemas for template metadata + approval |
| Modify | `backend/app/extensions/workflow/routers.py` | 4 new approval endpoints + enhanced list endpoint |
| Modify | `backend/app/extensions/workflow/service.py` | Approval service methods + create_definition update |
| Create | `backend/app/extensions/workflow/migration.py` | Alembic-style migration for new columns + table |
| Create | `backend/tests/test_workflow_template.py` | Tests for approval workflow, permissions, state transitions |

### Frontend

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/extensions/workflow/types.ts` | New types + extended interfaces |
| Modify | `frontend/src/extensions/workflow/api.ts` | 4 new API methods |
| Modify | `frontend/src/extensions/workflow/WorkflowEditor.tsx` | Extended props for standalone template mode |
| Modify | `frontend/src/app/admin/templates/page.tsx` | Rewritten template list with status/approval |
| Create | `frontend/src/app/admin/templates/[templateId]/page.tsx` | Template editor page |
| Create | `frontend/src/app/admin/templates/new/page.tsx` | New template page |
| Create | `frontend/src/app/admin/templates/components/ApprovalDialog.tsx` | Super-admin approval dialog |
| Create | `frontend/src/app/admin/templates/components/ApprovalHistoryPanel.tsx` | Approval timeline |
| Create | `frontend/src/app/admin/templates/components/SubmitApprovalDialog.tsx` | Submit approval confirmation |

---

## Task 1: Backend — Extend WorkflowDefinition Model

**Files:**
- Modify: `backend/app/extensions/workflow/models.py`
- Test: `backend/tests/test_workflow_template.py`

- [ ] **Step 1: Write failing tests for new model fields**

```python
# backend/tests/test_workflow_template.py
"""Tests for workflow template management — approval workflow, visibility, state transitions."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.extensions.workflow.models import WorkflowDefinition, TemplateApproval


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(WorkflowDefinition.metadata.create_all)
        await conn.run_sync(TemplateApproval.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_workflow_definition_has_template_fields(db: AsyncSession):
    """WorkflowDefinition supports description, template_status, visible_dept_ids, version."""
    wf = WorkflowDefinition(
        name="Test Template",
        graph_json={"nodes": [], "edges": []},
        is_template=True,
        description="A test template",
        template_status="draft",
        visible_dept_ids=["dept-1", "dept-2"],
        version=1,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    assert wf.description == "A test template"
    assert wf.template_status == "draft"
    assert wf.visible_dept_ids == ["dept-1", "dept-2"]
    assert wf.version == 1


async def test_workflow_definition_defaults(db: AsyncSession):
    """New WorkflowDefinition defaults to draft status and version 1."""
    wf = WorkflowDefinition(
        name="Defaults",
        graph_json={"nodes": [], "edges": []},
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    assert wf.template_status == "draft"
    assert wf.version == 1
    assert wf.visible_dept_ids is None
    assert wf.description is None


async def test_template_approval_creation(db: AsyncSession):
    """TemplateApproval records can be created and linked to a workflow."""
    user_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="Approval Test",
        graph_json={"nodes": [], "edges": []},
        created_by=user_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    approval = TemplateApproval(
        template_id=wf.id,
        requester_id=user_id,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    assert approval.status == "pending"
    assert approval.reviewer_id is None
    assert approval.comment is None
    assert approval.template_id == wf.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_template.py -v`
Expected: FAIL — `TemplateApproval` not found, new fields not on model

- [ ] **Step 3: Add new fields to WorkflowDefinition + create TemplateApproval table**

In `backend/app/extensions/workflow/models.py`, add these fields to the `WorkflowDefinition` class after `org_bindings`:

```python
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    visible_dept_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
```

Add the `TemplateApproval` class after `WorkflowDefinition`:

```python
class TemplateApproval(Base):
    """Approval record for template publishing — workflow-style approval chain."""

    __tablename__ = "template_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_template.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/models.py backend/tests/test_workflow_template.py
git commit -m "feat(workflow): add template metadata fields and TemplateApproval table"
```

---

## Task 2: Backend — Extend Schemas

**Files:**
- Modify: `backend/app/extensions/workflow/schemas.py`

- [ ] **Step 1: Add new fields to existing schemas + create new schemas**

In `schemas.py`, extend these existing schemas:

```python
class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict = Field(..., description="DAG nodes and edges from React Flow")
    is_template: bool = False
    org_bindings: dict | None = None
    description: str | None = None
    visible_dept_ids: list[str] | None = None


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict | None = None
    is_template: bool | None = None
    org_bindings: dict | None = None
    description: str | None = None
    template_status: str | None = None
    visible_dept_ids: list[str] | None = None


class WorkflowDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    graph_json: dict
    is_template: bool = False
    org_bindings: dict | None = None
    description: str | None = None
    template_status: str | None = None
    visible_dept_ids: list[str] | None = None
    version: int = 1
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowDefinitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    is_template: bool = False
    template_status: str | None = None
    description: str | None = None
    created_at: datetime | None = None
```

Add new schemas at the end of the file (before the `ReviewAssignmentCreate` section):

```python
# ── Template Approval ──


class TemplateApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    requester_id: UUID
    reviewer_id: UUID | None = None
    status: str
    comment: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None


class TemplateApprovalAction(BaseModel):
    action: str = Field(..., pattern=r"^(approved|rejected)$")
    comment: str | None = None
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/schemas.py
git commit -m "feat(workflow): extend schemas for template metadata and approval"
```

---

## Task 3: Backend — Service Layer for Approval Workflow

**Files:**
- Modify: `backend/app/extensions/workflow/service.py`
- Modify: `backend/tests/test_workflow_template.py`

- [ ] **Step 1: Write failing tests for approval service methods**

Append to `backend/tests/test_workflow_template.py`:

```python
from app.extensions.workflow.service import (
    submit_for_approval,
    review_approval,
    withdraw_approval,
    list_approvals,
)


async def test_submit_for_approval(db: AsyncSession):
    """Submitting a draft template creates a pending approval record."""
    user_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="Submit Test",
        graph_json={"nodes": [{"id": "a", "type": "phase", "position": {"x": 0, "y": 0}, "data": {"label": "P1"}}], "edges": []},
        is_template=True,
        template_status="draft",
        created_by=user_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    approval = await submit_for_approval(db, wf.id, user_id)
    assert approval is not None
    assert approval.status == "pending"
    assert approval.template_id == wf.id

    await db.refresh(wf)
    assert wf.template_status == "pending_approval"


async def test_review_approval_approve(db: AsyncSession):
    """Super-admin approving a template sets status to published."""
    requester_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="Review Test",
        graph_json={"nodes": [], "edges": []},
        is_template=True,
        template_status="pending_approval",
        created_by=requester_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    approval = TemplateApproval(
        template_id=wf.id,
        requester_id=requester_id,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    result = await review_approval(db, approval.id, reviewer_id, "approved", "Looks good")
    assert result.status == "approved"
    assert result.reviewer_id == reviewer_id

    await db.refresh(wf)
    assert wf.template_status == "published"
    assert wf.is_template is True


async def test_review_approval_reject(db: AsyncSession):
    """Super-admin rejecting a template sets status to rejected."""
    requester_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="Reject Test",
        graph_json={"nodes": [], "edges": []},
        is_template=True,
        template_status="pending_approval",
        created_by=requester_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    approval = TemplateApproval(
        template_id=wf.id,
        requester_id=requester_id,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)

    result = await review_approval(db, approval.id, reviewer_id, "rejected", "Missing review node")
    assert result.status == "rejected"

    await db.refresh(wf)
    assert wf.template_status == "rejected"


async def test_withdraw_approval(db: AsyncSession):
    """Requester can withdraw a pending approval."""
    user_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="Withdraw Test",
        graph_json={"nodes": [], "edges": []},
        is_template=True,
        template_status="pending_approval",
        created_by=user_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    approval = TemplateApproval(
        template_id=wf.id,
        requester_id=user_id,
        status="pending",
    )
    db.add(approval)
    await db.commit()

    result = await withdraw_approval(db, wf.id, user_id)
    assert result is True

    await db.refresh(wf)
    assert wf.template_status == "draft"


async def test_list_approvals(db: AsyncSession):
    """List approval records for a template in chronological order."""
    user_id = uuid.uuid4()
    wf = WorkflowDefinition(
        name="List Test",
        graph_json={"nodes": [], "edges": []},
        created_by=user_id,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    a1 = TemplateApproval(template_id=wf.id, requester_id=user_id, status="pending")
    db.add(a1)
    await db.commit()

    approvals = await list_approvals(db, wf.id)
    assert len(approvals) == 1
    assert approvals[0].status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_template.py -v`
Expected: FAIL — `submit_for_approval` etc. not defined

- [ ] **Step 3: Implement approval service methods**

Add to `backend/app/extensions/workflow/service.py` after the `publish_as_template` function:

```python
from .models import TemplateApproval


async def submit_for_approval(
    db: AsyncSession,
    template_id: UUID,
    requester_id: UUID,
) -> TemplateApproval:
    """Submit a draft template for approval. Sets status to pending_approval."""
    definition = await db.get(WorkflowDefinition, template_id)
    if not definition:
        raise ValueError("Template not found")
    if definition.template_status not in ("draft", "rejected"):
        raise ValueError(f"Cannot submit template in status '{definition.template_status}'")

    definition.template_status = "pending_approval"
    approval = TemplateApproval(
        template_id=template_id,
        requester_id=requester_id,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def review_approval(
    db: AsyncSession,
    approval_id: UUID,
    reviewer_id: UUID,
    action: str,
    comment: str | None = None,
) -> TemplateApproval:
    """Approve or reject a pending approval. Updates template status accordingly."""
    approval = await db.get(TemplateApproval, approval_id)
    if not approval:
        raise ValueError("Approval not found")
    if approval.status != "pending":
        raise ValueError(f"Approval already {approval.status}")

    approval.status = action
    approval.reviewer_id = reviewer_id
    approval.comment = comment
    approval.reviewed_at = datetime.now()

    definition = await db.get(WorkflowDefinition, approval.template_id)
    if definition:
        if action == "approved":
            definition.template_status = "published"
            definition.is_template = True
        elif action == "rejected":
            definition.template_status = "rejected"

    await db.commit()
    await db.refresh(approval)
    return approval


async def withdraw_approval(
    db: AsyncSession,
    template_id: UUID,
    requester_id: UUID,
) -> bool:
    """Withdraw a pending approval. Sets template back to draft."""
    stmt = (
        select(TemplateApproval)
        .where(TemplateApproval.template_id == template_id)
        .where(TemplateApproval.status == "pending")
    )
    result = await db.execute(stmt)
    pending = result.scalars().first()
    if not pending:
        return False

    pending.status = "withdrawn"
    definition = await db.get(WorkflowDefinition, template_id)
    if definition:
        definition.template_status = "draft"

    await db.commit()
    return True


async def list_approvals(
    db: AsyncSession,
    template_id: UUID,
) -> list[TemplateApproval]:
    """List all approval records for a template, ordered by creation time."""
    stmt = (
        select(TemplateApproval)
        .where(TemplateApproval.template_id == template_id)
        .order_by(TemplateApproval.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
```

Also add `datetime` to the imports at the top of `service.py`:

```python
from datetime import datetime
```

And update the `create_definition` function to accept and pass through the new fields:

```python
async def create_definition(
    db: AsyncSession,
    name: str,
    graph_json: dict,
    created_by: UUID,
    report_type: str | None = None,
    is_template: bool = False,
    description: str | None = None,
    visible_dept_ids: list[str] | None = None,
) -> WorkflowDefinition:
    """Create a new workflow definition."""
    definition = WorkflowDefinition(
        name=name,
        report_type=report_type,
        graph_json=graph_json,
        is_template=is_template,
        created_by=created_by,
        description=description,
        visible_dept_ids=visible_dept_ids,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return definition
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_template.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/service.py backend/tests/test_workflow_template.py
git commit -m "feat(workflow): add approval service methods for template publishing"
```

---

## Task 4: Backend — API Endpoints for Approval

**Files:**
- Modify: `backend/app/extensions/workflow/routers.py`

- [ ] **Step 1: Update create_definition endpoint to pass new fields**

In `routers.py`, update the `create_definition` endpoint to pass `description` and `visible_dept_ids`:

```python
@router.post("/definitions", response_model=WorkflowDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_definition(
    body: WorkflowDefinitionCreate,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    definition = await _create_definition_svc(
        db,
        name=body.name,
        report_type=body.report_type,
        graph_json=body.graph_json,
        is_template=body.is_template,
        created_by=user.id,
        description=body.description,
        visible_dept_ids=body.visible_dept_ids,
    )
    return WorkflowDefinitionOut.model_validate(definition)
```

- [ ] **Step 2: Add approval endpoints**

Add these imports at the top of `routers.py`:

```python
from .schemas import (
    # ... existing imports ...
    TemplateApprovalAction,
    TemplateApprovalOut,
)
from .service import (
    # ... existing imports ...
    submit_for_approval as _submit_approval_svc,
    review_approval as _review_approval_svc,
    withdraw_approval as _withdraw_approval_svc,
    list_approvals as _list_approvals_svc,
)
```

Add these endpoints after the `publish_template` endpoint:

```python
@router.post("/definitions/{definition_id}/submit-approval", response_model=TemplateApprovalOut)
async def submit_template_approval(
    definition_id: UUID,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Submit a draft template for approval (department admin)."""
    approval = await _submit_approval_svc(db, definition_id, user.id)
    return TemplateApprovalOut.model_validate(approval)


@router.post("/definitions/{definition_id}/review-approval", response_model=TemplateApprovalOut)
async def review_template_approval(
    definition_id: UUID,
    body: TemplateApprovalAction,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a pending template approval (super admin)."""
    from .service import list_approvals as _list_approvals

    approvals = await _list_approvals(db, definition_id)
    pending = next((a for a in approvals if a.status == "pending"), None)
    if not pending:
        raise HTTPException(status_code=400, detail="No pending approval for this template")

    result = await _review_approval_svc(db, pending.id, user.id, body.action, body.comment)
    return TemplateApprovalOut.model_validate(result)


@router.get("/definitions/{definition_id}/approvals", response_model=list[TemplateApprovalOut])
async def get_template_approvals(
    definition_id: UUID,
    _user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
):
    """Get approval history for a template."""
    approvals = await _list_approvals_svc(db, definition_id)
    return [TemplateApprovalOut.model_validate(a) for a in approvals]


@router.post("/definitions/{definition_id}/withdraw-approval")
async def withdraw_template_approval(
    definition_id: UUID,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Withdraw a pending approval request."""
    success = await _withdraw_approval_svc(db, definition_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="No pending approval to withdraw")
    return {"status": "withdrawn"}
```

- [ ] **Step 3: Update publish_template endpoint to set template_status**

Replace the existing `publish_template` endpoint:

```python
@router.post("/definitions/{definition_id}/publish-template", response_model=WorkflowDefinitionOut)
async def publish_template(
    definition_id: UUID,
    _user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Publish a workflow definition as a reusable template (super admin direct publish)."""
    definition = await _get_definition_svc(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")

    definition.is_template = True
    definition.template_status = "published"
    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionOut.model_validate(definition)
```

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/routers.py
git commit -m "feat(workflow): add approval API endpoints for template publishing"
```

---

## Task 5: Backend — Database Migration

**Files:**
- Create: `backend/app/extensions/workflow/migration.py`

- [ ] **Step 1: Create migration script**

```python
"""Migration: add template metadata fields and template_approvals table.

Run: docker exec deer-flow-gateway python -m app.extensions.workflow.migration
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.extensions.database import get_database_url

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- Add new columns to workflow_definitions
ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS template_status VARCHAR(20) NOT NULL DEFAULT 'draft';
ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS visible_dept_ids JSONB;
ALTER TABLE workflow_definitions ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- Create template_approvals table
CREATE TABLE IF NOT EXISTS template_approvals (
    id UUID PRIMARY KEY,
    template_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES users(id),
    reviewer_id UUID REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    comment TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_template_approvals_template_id ON template_approvals(template_id);
"""


async def run_migration():
    engine = create_async_engine(get_database_url())
    async with engine.begin() as conn:
        await conn.execute(text(MIGRATION_SQL))
    await engine.dispose()
    logger.info("Migration complete: template metadata + approval table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migration())
```

- [ ] **Step 2: Run migration against Docker database**

Run: `docker exec deer-flow-gateway python -m app.extensions.workflow.migration`

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/migration.py
git commit -m "feat(workflow): add migration for template metadata and approvals"
```

---

## Task 6: Frontend — Types and API Client

**Files:**
- Modify: `frontend/src/extensions/workflow/types.ts`
- Modify: `frontend/src/extensions/workflow/api.ts`

- [ ] **Step 1: Extend TypeScript types**

In `types.ts`, update `WorkflowDefinition` interface:

```typescript
export interface WorkflowDefinition {
  id: string;
  name: string;
  reportType: string | null;
  graphJson: WorkflowGraph;
  isTemplate: boolean;
  orgBindings: Record<string, { deptCode?: string; departmentCode?: string }> | null;
  description: string | null;
  templateStatus: string | null;
  visibleDeptIds: string[] | null;
  version: number;
  createdBy: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}
```

Update `WorkflowDefinitionListItem` interface:

```typescript
export interface WorkflowDefinitionListItem {
  id: string;
  name: string;
  reportType: string | null;
  isTemplate: boolean;
  templateStatus: string | null;
  description: string | null;
  createdAt: string | null;
}
```

Update `CreateWorkflowRequest` interface:

```typescript
export interface CreateWorkflowRequest {
  name: string;
  reportType?: string | null;
  graphJson: WorkflowGraph;
  isTemplate?: boolean;
  orgBindings?: Record<string, { deptCode?: string }> | null;
  description?: string | null;
  visibleDeptIds?: string[] | null;
}
```

Update `UpdateWorkflowRequest` interface:

```typescript
export interface UpdateWorkflowRequest {
  name?: string | null;
  reportType?: string | null;
  graphJson?: WorkflowGraph;
  isTemplate?: boolean;
  orgBindings?: Record<string, { deptCode?: string }> | null;
  description?: string | null;
  templateStatus?: string | null;
  visibleDeptIds?: string[] | null;
}
```

Add new types at the end of the file:

```typescript
// ── Template Approval ──

export interface TemplateApproval {
  id: string;
  templateId: string;
  requesterId: string;
  reviewerId: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  comment: string | null;
  createdAt: string | null;
  reviewedAt: string | null;
}
```

- [ ] **Step 2: Add API methods**

In `api.ts`, add these methods to `workflowApi` before the closing `}`:

```typescript
  // ── Template Approval ──

  submitApproval: async (id: string): Promise<TemplateApproval> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}/submit-approval`, {
      method: "POST",
    });
    return toCamelCase<TemplateApproval>(data);
  },

  reviewApproval: async (id: string, action: "approved" | "rejected", comment?: string): Promise<TemplateApproval> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/definitions/${id}/review-approval`, {
      method: "POST",
      body: JSON.stringify({ action, comment }),
    });
    return toCamelCase<TemplateApproval>(data);
  },

  getApprovals: async (id: string): Promise<TemplateApproval[]> => {
    const data = await authFetch<Record<string, unknown>[]>(`${API_BASE}/definitions/${id}/approvals`);
    return data.map((d) => toCamelCase<TemplateApproval>(d));
  },

  withdrawApproval: async (id: string): Promise<{ status: string }> => {
    return authFetch<{ status: string }>(`${API_BASE}/definitions/${id}/withdraw-approval`, {
      method: "POST",
    });
  },
```

Add `TemplateApproval` to the import from `./types`:

```typescript
import type {
  // ... existing imports ...
  TemplateApproval,
} from "./types";
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/workflow/types.ts frontend/src/extensions/workflow/api.ts
git commit -m "feat(workflow): extend frontend types and API for template approval"
```

---

## Task 7: Frontend — Refactor WorkflowEditor for Dual Mode

**Files:**
- Modify: `frontend/src/extensions/workflow/WorkflowEditor.tsx`

- [ ] **Step 1: Refactor WorkflowEditor props and behavior**

Replace the entire `WorkflowEditor` component in `WorkflowEditor.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, type NodeTypes, type EdgeTypes } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AIGenerateNode } from "./nodes/AIGenerateNode";
import { ConditionNode } from "./nodes/ConditionNode";
import { MergeNode } from "./nodes/MergeNode";
import { PhaseNode } from "./nodes/PhaseNode";
import { ReviewNode } from "./nodes/ReviewNode";
import { SubWorkflowNode } from "./nodes/SubWorkflowNode";
import { ConditionEdge } from "./edges/ConditionEdge";
import { NodePalette } from "./panels/NodePalette";
import { PhaseConfigPanel } from "./panels/PhaseConfigPanel";
import { ReviewConfigPanel } from "./panels/ReviewConfigPanel";
import { useValidation } from "./hooks/useValidation";
import { useWorkflowDAG } from "./hooks/useWorkflowDAG";
import { workflowApi } from "./api";
import type { DAGNode, DAGNodeData, WorkflowGraph } from "./types";

const nodeTypes: NodeTypes = {
  phase: PhaseNode,
  review: ReviewNode,
  condition: ConditionNode,
  ai_generate: AIGenerateNode,
  merge: MergeNode,
  sub_workflow: SubWorkflowNode,
};

const edgeTypes: EdgeTypes = {
  condition: ConditionEdge,
};

export interface WorkflowEditorProps {
  /** Project context (existing usage) */
  projectId?: string;
  /** Load an existing graph into the editor */
  initialGraphJson?: WorkflowGraph;
  /** Initial workflow name */
  initialName?: string;
  /** Custom save handler — replaces default workflowApi.create behavior */
  onSave?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  /** Custom save-as-template handler */
  onSaveTemplate?: (name: string, graphJson: WorkflowGraph) => Promise<void>;
  /** Org binding change callback — passed through to PhaseConfigPanel */
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
  /** Current org bindings map (nodeId → deptCode) */
  orgBindings?: Record<string, { deptCode?: string }>;
}

export function WorkflowEditor({
  projectId,
  initialGraphJson,
  initialName,
  onSave: onSaveProp,
  onSaveTemplate: onSaveTemplateProp,
  onOrgBindingChange,
  orgBindings,
}: WorkflowEditorProps) {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, updateNodeData, toGraphJson, fromGraphJson } = useWorkflowDAG();
  const { result: validationResult, isValidating, validate } = useValidation();
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(initialName || "新工作流");
  const [selectedNode, setSelectedNode] = useState<DAGNode | null>(null);

  // Load initial graph when provided
  useEffect(() => {
    if (initialGraphJson) {
      fromGraphJson(initialGraphJson);
    }
  }, [initialGraphJson, fromGraphJson]);

  const handleValidate = useCallback(async () => {
    await validate(toGraphJson());
  }, [validate, toGraphJson]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const json = toGraphJson();
      if (onSaveProp) {
        await onSaveProp(name, json);
      } else {
        await workflowApi.create({ name, graphJson: json });
      }
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson, onSaveProp]);

  const handleSaveTemplate = useCallback(async () => {
    setSaving(true);
    try {
      const json = toGraphJson();
      if (onSaveTemplateProp) {
        await onSaveTemplateProp(name, json);
      } else {
        await workflowApi.create({ name: name + " (模板)", graphJson: json, isTemplate: true });
      }
    } finally {
      setSaving(false);
    }
  }, [name, toGraphJson, onSaveTemplateProp]);

  // Resolve org binding for a specific node
  const getOrgDeptCode = useCallback(
    (nodeId: string): string | undefined => {
      if (!orgBindings || !orgBindings[nodeId]) return undefined;
      return orgBindings[nodeId].deptCode;
    },
    [orgBindings],
  );

  return (
    <ReactFlowProvider>
    <div className="relative flex h-full border rounded-lg overflow-hidden">
      {/* Left: Node Palette */}
      <div className="w-48 shrink-0 border-r bg-muted/30 p-3">
        <div className="text-sm font-semibold mb-3">节点面板</div>
        <NodePalette />
      </div>

      {/* Center: React Flow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_event, node) => {
            const dagNode: DAGNode = {
              id: node.id,
              type: node.type as DAGNode["type"],
              position: node.position,
              data: node.data as DAGNodeData,
            };
            setSelectedNode(dagNode);
          }}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      {/* Right: Config Panel */}
      <div className="w-72 shrink-0 border-l bg-card overflow-y-auto">
        {selectedNode ? (
          <div className="p-4 space-y-3">
            <div className="text-sm font-semibold">
              {selectedNode.data.label || selectedNode.id} 属性
            </div>
            {selectedNode.type === "phase" && (
              <PhaseConfigPanel
                data={selectedNode.data}
                nodeId={selectedNode.id}
                onUpdate={(partial) => updateNodeData(selectedNode.id, partial)}
                orgDeptCode={getOrgDeptCode(selectedNode.id)}
                onOrgBindingChange={onOrgBindingChange}
              />
            )}
            {selectedNode.type === "review" && (
              <ReviewConfigPanel
                data={selectedNode.data}
                onUpdate={(partial) => updateNodeData(selectedNode.id, partial)}
              />
            )}
            {selectedNode.type !== "phase" && selectedNode.type !== "review" && (
              <div className="text-xs text-muted-foreground">
                {selectedNode.type} 节点暂无可配置属性
              </div>
            )}
          </div>
        ) : (
          <div className="p-4 text-sm text-muted-foreground">
            选择节点查看属性
          </div>
        )}
      </div>

      {/* Top toolbar */}
      <div className="absolute top-2 right-2 z-10 flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="px-2 py-1 text-sm border rounded bg-white"
          placeholder="工作流名称"
        />
        <button
          onClick={handleValidate}
          disabled={isValidating}
          className="px-3 py-1 text-sm bg-secondary rounded hover:bg-secondary/80"
        >
          {isValidating ? "校验中..." : "校验"}
        </button>
        {!onSaveTemplateProp && (
          <button
            onClick={handleSaveTemplate}
            disabled={saving}
            className="px-3 py-1 text-sm bg-muted rounded hover:bg-muted/80"
          >
            存为模板
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90"
        >
          {saving ? "保存中..." : "保存"}
        </button>
      </div>

      {/* Validation result overlay */}
      {validationResult && (
        <div
          className={`absolute bottom-2 right-2 z-10 p-3 rounded-lg border text-sm max-w-xs ${
            validationResult.valid ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"
          }`}
        >
          <div className="font-semibold">
            {validationResult.valid ? "校验通过" : "校验失败"}
          </div>
          {validationResult.errors.map((e, i) => (
            <div key={i} className="text-red-600">
              {e}
            </div>
          ))}
          {validationResult.warnings.map((w, i) => (
            <div key={i} className="text-amber-600">
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
    </ReactFlowProvider>
  );
}
```

Key changes:
- Props extended with `initialGraphJson`, `initialName`, `onSave`, `onSaveTemplate`, `onOrgBindingChange`, `orgBindings`
- `useEffect` loads `initialGraphJson` via `fromGraphJson`
- Save handlers delegate to custom callbacks when provided
- PhaseConfigPanel receives `orgDeptCode` and `onOrgBindingChange`
- "存为模板" button hidden when `onSaveTemplateProp` is provided (template editor has its own publish flow)
- Existing `interface WorkflowEditorProps` replaced with `export interface` for use in template page

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/workflow/WorkflowEditor.tsx
git commit -m "refactor(workflow): extend WorkflowEditor props for standalone template mode"
```

---

## Task 8: Frontend — Template Editor Page

**Files:**
- Create: `frontend/src/app/admin/templates/new/page.tsx`
- Create: `frontend/src/app/admin/templates/[templateId]/page.tsx`

- [ ] **Step 1: Create the new template page**

```tsx
// frontend/src/app/admin/templates/new/page.tsx
"use client";

import { TemplateEditorPage } from "../components/TemplateEditorPage";

export default function NewTemplatePage() {
  return <TemplateEditorPage />;
}
```

- [ ] **Step 2: Create the edit template page**

```tsx
// frontend/src/app/admin/templates/[templateId]/page.tsx
"use client";

import { use } from "react";

import { TemplateEditorPage } from "../components/TemplateEditorPage";

export default function EditTemplatePage({ params }: { params: Promise<{ templateId: string }> }) {
  const { templateId } = use(params);
  return <TemplateEditorPage templateId={templateId} />;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/templates/new/page.tsx "frontend/src/app/admin/templates/[templateId]/page.tsx"
git commit -m "feat(admin): add template editor route pages"
```

---

## Task 9: Frontend — TemplateEditorPage Component

**Files:**
- Create: `frontend/src/app/admin/templates/components/TemplateEditorPage.tsx`

- [ ] **Step 1: Create TemplateEditorPage component**

```tsx
// frontend/src/app/admin/templates/components/TemplateEditorPage.tsx
"use client";

import { ArrowLeft, ChevronDown, ChevronUp, Loader2, Save, Send, CheckCircle2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { deptApi } from "@/extensions/api/index";
import { workflowApi } from "@/extensions/workflow/api";
import { WorkflowEditor } from "@/extensions/workflow/WorkflowEditor";
import type { WorkflowGraph } from "@/extensions/workflow/types";
import { REPORT_TYPE_LABELS } from "@/extensions/project/types";
import type { ReportType } from "@/extensions/project/types";
import { useAuth } from "@/extensions/hooks/useAuth";

interface DeptItem {
  id: string;
  name: string;
  code: string | null;
}

interface TemplateEditorPageProps {
  templateId?: string;
}

export function TemplateEditorPage({ templateId }: TemplateEditorPageProps) {
  const router = useRouter();
  const { user } = useAuth();
  const isSuperAdmin = user?.role_name === "Super Admin";

  // Template metadata
  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<string>("");
  const [description, setDescription] = useState("");
  const [visibleDeptIds, setVisibleDeptIds] = useState<string[]>([]);
  const [templateStatus, setTemplateStatus] = useState<string>("draft");
  const [orgBindings, setOrgBindings] = useState<Record<string, { deptCode?: string }>>({});

  // Editor state
  const [initialGraphJson, setInitialGraphJson] = useState<WorkflowGraph | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(!!templateId);
  const [saving, setSaving] = useState(false);
  const [bottomOpen, setBottomOpen] = useState(true);

  // Departments for visibility selector
  const [departments, setDepartments] = useState<DeptItem[]>([]);
  useEffect(() => {
    deptApi.list({ limit: 100 }).then((res: { items?: DeptItem[] }) => {
      setDepartments(res.items || []);
    }).catch(() => {});
  }, []);

  // Load existing template
  useEffect(() => {
    if (!templateId) return;
    setIsLoading(true);
    workflowApi
      .get(templateId)
      .then((def) => {
        setName(def.name);
        setReportType(def.reportType || "");
        setDescription(def.description || "");
        setVisibleDeptIds(def.visibleDeptIds || []);
        setTemplateStatus(def.templateStatus || "draft");
        setOrgBindings(def.orgBindings || {});
        if (def.graphJson) {
          setInitialGraphJson(def.graphJson);
        }
      })
      .catch((err) => {
        console.error(err);
        toast.error("加载模板失败");
      })
      .finally(() => setIsLoading(false));
  }, [templateId]);

  // Org binding change handler
  const handleOrgBindingChange = useCallback((nodeId: string, deptCode: string | null) => {
    setOrgBindings((prev) => {
      const next = { ...prev };
      if (deptCode) {
        next[nodeId] = { deptCode };
      } else {
        delete next[nodeId];
      }
      return next;
    });
  }, []);

  // Save handler passed to WorkflowEditor
  const handleSave = useCallback(
    async (_name: string, graphJson: WorkflowGraph) => {
      setSaving(true);
      try {
        if (templateId) {
          await workflowApi.update(templateId, {
            name: _name || name,
            graphJson,
            orgBindings,
            description,
            visibleDeptIds: visibleDeptIds.length > 0 ? visibleDeptIds : null,
          });
          toast.success("模板已保存");
        } else {
          const created = await workflowApi.create({
            name: _name || name || "新工作流模板",
            graphJson,
            isTemplate: true,
            orgBindings,
            description,
            visibleDeptIds: visibleDeptIds.length > 0 ? visibleDeptIds : null,
            reportType: reportType || null,
          });
          toast.success("模板已创建");
          router.replace(`/admin/templates/${created.id}`);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "保存失败");
      } finally {
        setSaving(false);
      }
    },
    [templateId, name, orgBindings, description, visibleDeptIds, reportType, router],
  );

  // Publish / Submit approval
  const handlePublish = useCallback(async () => {
    if (!templateId) return;
    setSaving(true);
    try {
      if (isSuperAdmin) {
        await workflowApi.publishTemplate(templateId);
        toast.success("模板已发布");
        setTemplateStatus("published");
      } else {
        await workflowApi.submitApproval(templateId);
        toast.success("已提交审批");
        setTemplateStatus("pending_approval");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setSaving(false);
    }
  }, [templateId, isSuperAdmin]);

  // Unpublish
  const handleUnpublish = useCallback(async () => {
    if (!templateId) return;
    setSaving(true);
    try {
      await workflowApi.update(templateId, {
        isTemplate: false,
        templateStatus: "draft",
      });
      toast.success("已撤回发布");
      setTemplateStatus("draft");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setSaving(false);
    }
  }, [templateId]);

  if (isLoading) {
    return <PageLoadingOverlay text="加载模板" />;
  }

  const statusLabel: Record<string, { text: string; color: string }> = {
    draft: { text: "草稿", color: "bg-gray-100 text-gray-600 border-gray-200" },
    pending_approval: { text: "待审批", color: "bg-amber-50 text-amber-600 border-amber-200" },
    published: { text: "已发布", color: "bg-green-50 text-green-600 border-green-200" },
    rejected: { text: "已拒绝", color: "bg-red-50 text-red-600 border-red-200" },
  };
  const st = statusLabel[templateStatus] || statusLabel.draft;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Top toolbar */}
      <div className="shrink-0 border-b bg-card px-6 py-3 flex items-center gap-4">
        <Link
          href="/admin/templates"
          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="模板名称"
          className="px-3 py-1.5 text-sm font-medium border rounded-lg bg-background w-64"
        />

        <select
          value={reportType}
          onChange={(e) => setReportType(e.target.value)}
          className="px-3 py-1.5 text-sm border rounded-lg bg-background"
        >
          <option value="">选择报告类型</option>
          {Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${st.color}`}>
          {st.text}
        </span>

        <div className="flex-1" />

        <button
          onClick={handlePublish}
          disabled={saving || templateStatus === "published" || templateStatus === "pending_approval"}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSuperAdmin ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />}
          {templateStatus === "published" ? "已发布" : isSuperAdmin ? "发布" : "提交审批"}
        </button>
      </div>

      {/* Workflow Editor */}
      <div className="flex-1 min-h-0">
        <WorkflowEditor
          initialGraphJson={initialGraphJson}
          initialName={name}
          onSave={handleSave}
          onOrgBindingChange={handleOrgBindingChange}
          orgBindings={orgBindings}
        />
      </div>

      {/* Bottom settings panel */}
      <div className="shrink-0 border-t bg-card">
        <button
          onClick={() => setBottomOpen(!bottomOpen)}
          className="w-full flex items-center justify-between px-6 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>模板设置</span>
          {bottomOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </button>
        {bottomOpen && (
          <div className="px-6 pb-4 flex items-start gap-6">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground block mb-1">模板描述</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="描述此模板的用途和适用场景..."
                rows={2}
                className="w-full px-3 py-1.5 text-sm border rounded-lg bg-background resize-none"
              />
            </div>
            <div className="w-64">
              <label className="text-xs text-muted-foreground block mb-1">
                可见部门（留空 = 全部可见）
              </label>
              <div className="max-h-24 overflow-y-auto border rounded-lg bg-background p-2 space-y-1">
                {departments.map((dept) => (
                  <label key={dept.id} className="flex items-center gap-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={visibleDeptIds.includes(dept.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setVisibleDeptIds((prev) => [...prev, dept.id]);
                        } else {
                          setVisibleDeptIds((prev) => prev.filter((id) => id !== dept.id));
                        }
                      }}
                      className="rounded"
                    />
                    {dept.name}
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/templates/components/TemplateEditorPage.tsx
git commit -m "feat(admin): add TemplateEditorPage component with org binding and visibility"
```

---

## Task 10: Frontend — Rewrite Template List Page

**Files:**
- Rewrite: `frontend/src/app/admin/templates/page.tsx`

- [ ] **Step 1: Rewrite the template list page**

```tsx
// frontend/src/app/admin/templates/page.tsx
"use client";

import {
  Search,
  Plus,
  FileText,
  Loader2,
  Globe,
  GlobeLock,
  Trash2,
  Pencil,
  Send,
  CheckCircle2,
  Clock,
  XCircle,
  Undo2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import Link from "next/link";

import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowDefinitionListItem } from "@/extensions/workflow/types";
import { REPORT_TYPE_LABELS } from "@/extensions/project/types";
import type { ReportType } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/extensions/hooks/useAuth";

const REPORT_TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "全部类型" },
  ...Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

function formatDate(s: string | null): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return s;
  }
}

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  draft: { label: "草稿", icon: GlobeLock, color: "bg-gray-50 text-gray-400 border-gray-200" },
  pending_approval: { label: "待审批", icon: Clock, color: "bg-amber-50 text-amber-600 border-amber-200" },
  published: { label: "已发布", icon: Globe, color: "bg-green-50 text-green-600 border-green-200" },
  rejected: { label: "已拒绝", icon: XCircle, color: "bg-red-50 text-red-600 border-red-200" },
};

export default function AdminTemplatesPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role_name === "Super Admin";

  const [templates, setTemplates] = useState<WorkflowDefinitionListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [reportTypeFilter, setReportTypeFilter] = useState("");
  const [actioningId, setActioningId] = useState<string | null>(null);

  const loadTemplates = async () => {
    setIsLoading(true);
    try {
      const res = await workflowApi.list({
        isTemplate: true,
        reportType: reportTypeFilter || undefined,
      });
      setTemplates(res.items);
    } catch (err) {
      console.error(err);
      toast.error("加载模板列表失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, [reportTypeFilter]);

  const filteredTemplates = searchQuery
    ? templates.filter((t) => t.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : templates;

  const handlePublish = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.publishTemplate(t.id);
      toast.success("模板已发布");
      loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发布失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleUnpublish = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.update(t.id, { isTemplate: false, templateStatus: "draft" });
      toast.success("已撤回发布");
      loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleSubmitApproval = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.submitApproval(t.id);
      toast.success("已提交审批");
      loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleWithdrawApproval = async (t: WorkflowDefinitionListItem) => {
    setActioningId(t.id);
    try {
      await workflowApi.withdrawApproval(t.id);
      toast.success("已撤回审批");
      loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "撤回失败");
    } finally {
      setActioningId(null);
    }
  };

  const handleDelete = async (t: WorkflowDefinitionListItem) => {
    if (!confirm(`确定要删除模板"${t.name}"吗？`)) return;
    setActioningId(t.id);
    try {
      await workflowApi.delete(t.id);
      toast.success("模板已删除");
      loadTemplates();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setActioningId(null);
    }
  };

  if (isLoading) {
    return <PageLoadingOverlay text="加载中" />;
  }

  return (
    <main className="h-full flex flex-col overflow-hidden max-w-[1200px] w-full mx-auto bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border bg-card px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <FileText className="w-4 h-4" />
              <span>模板管理</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">
              工作流模板
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              管理、编辑和发布可复用的工作流模板
            </p>
          </div>
          <Link
            href="/admin/templates/new"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            新建模板
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="shrink-0 px-8 py-4 border-b border-border bg-muted/30 flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索模板..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-secondary border-transparent focus:bg-background focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-lg text-sm transition-all outline-none"
          />
        </div>
        <div className="flex items-center gap-1.5">
          {REPORT_TYPE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setReportTypeFilter(f.value)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
                reportTypeFilter === f.value
                  ? "bg-primary text-white"
                  : "bg-secondary text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Template Grid */}
      <div className="flex-1 overflow-y-auto p-8">
        {filteredTemplates.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4 text-muted-foreground">
                <FileText className="w-8 h-8" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-2">
                {searchQuery || reportTypeFilter ? "没有匹配的模板" : "暂无模板"}
              </h3>
              <p className="text-muted-foreground text-sm mb-6">
                {searchQuery || reportTypeFilter
                  ? "请尝试调整筛选条件"
                  : "创建一个工作流模板，用于快速初始化新项目"}
              </p>
              {!searchQuery && !reportTypeFilter && (
                <Link
                  href="/admin/templates/new"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  新建模板
                </Link>
              )}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredTemplates.map((t) => {
              const status = t.templateStatus || "draft";
              const sc = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
              const StatusIcon = sc.icon;

              return (
                <div
                  key={t.id}
                  className="rounded-xl border border-border bg-card hover:shadow-sm transition-all overflow-hidden"
                >
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-sm font-semibold text-foreground truncate">
                            {t.name}
                          </h3>
                          <div className="flex items-center gap-2 mt-1">
                            {t.reportType && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
                                {REPORT_TYPE_LABELS[t.reportType as ReportType] ?? t.reportType}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <span className={cn("flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 border", sc.color)}>
                        <StatusIcon className="w-3 h-3" />
                        {sc.label}
                      </span>
                    </div>
                    {t.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2 mt-2">
                        {t.description}
                      </p>
                    )}
                  </div>

                  <div className="px-5 py-3 border-t border-border bg-muted/30 flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">
                      {formatDate(t.createdAt)}
                    </span>
                    <div className="flex items-center gap-1">
                      {/* Edit — always available */}
                      <Link
                        href={`/admin/templates/${t.id}`}
                        title="编辑模板"
                        className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Link>

                      {/* Status-dependent actions */}
                      {status === "draft" && isSuperAdmin && (
                        <button
                          type="button"
                          title="直接发布"
                          disabled={actioningId === t.id}
                          onClick={() => handlePublish(t)}
                          className="p-1.5 text-muted-foreground hover:text-green-600 hover:bg-green-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {status === "draft" && !isSuperAdmin && (
                        <button
                          type="button"
                          title="提交审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleSubmitApproval(t)}
                          className="p-1.5 text-muted-foreground hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {status === "pending_approval" && (
                        <button
                          type="button"
                          title="撤回审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleWithdrawApproval(t)}
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Undo2 className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {status === "published" && (
                        <button
                          type="button"
                          title="撤回发布"
                          disabled={actioningId === t.id}
                          onClick={() => handleUnpublish(t)}
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Undo2 className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {status === "rejected" && isSuperAdmin && (
                        <button
                          type="button"
                          title="直接发布"
                          disabled={actioningId === t.id}
                          onClick={() => handlePublish(t)}
                          className="p-1.5 text-muted-foreground hover:text-green-600 hover:bg-green-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                        </button>
                      )}
                      {status === "rejected" && !isSuperAdmin && (
                        <button
                          type="button"
                          title="重新提交审批"
                          disabled={actioningId === t.id}
                          onClick={() => handleSubmitApproval(t)}
                          className="p-1.5 text-muted-foreground hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        </button>
                      )}

                      {/* Delete */}
                      <button
                        type="button"
                        title="删除"
                        disabled={actioningId === t.id}
                        onClick={() => handleDelete(t)}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                      >
                        {actioningId === t.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
```

Key changes from the old page:
- "新建模板" → `/admin/templates/new` (was `/projects/new`)
- Card "edit" → `/admin/templates/${t.id}` (was `/projects/new?workflowId=`)
- Status-aware action buttons per the state machine
- Description display on cards
- `useAuth` to detect super admin vs department admin

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/admin/templates/page.tsx
git commit -m "feat(admin): rewrite template list page with status, approval, and correct navigation"
```

---

## Task 11: Frontend — Approval UI Components

**Files:**
- Create: `frontend/src/app/admin/templates/components/ApprovalDialog.tsx`
- Create: `frontend/src/app/admin/templates/components/ApprovalHistoryPanel.tsx`
- Create: `frontend/src/app/admin/templates/components/SubmitApprovalDialog.tsx`

- [ ] **Step 1: Create ApprovalHistoryPanel**

```tsx
// frontend/src/app/admin/templates/components/ApprovalHistoryPanel.tsx
"use client";

import { CheckCircle2, XCircle, Clock, Undo2, Send } from "lucide-react";

import type { TemplateApproval } from "@/extensions/workflow/types";

interface ApprovalHistoryPanelProps {
  approvals: TemplateApproval[];
}

const ACTION_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  pending: { label: "提交审批", icon: Send, color: "text-amber-600" },
  approved: { label: "审批通过", icon: CheckCircle2, color: "text-green-600" },
  rejected: { label: "审批拒绝", icon: XCircle, color: "text-red-600" },
  withdrawn: { label: "撤回审批", icon: Undo2, color: "text-gray-500" },
};

function formatTime(s: string | null): string {
  if (!s) return "";
  try {
    const d = new Date(s);
    return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  } catch {
    return "";
  }
}

export function ApprovalHistoryPanel({ approvals }: ApprovalHistoryPanelProps) {
  if (approvals.length === 0) {
    return <div className="text-xs text-muted-foreground py-2">暂无审批记录</div>;
  }

  return (
    <div className="space-y-2">
      {approvals.map((a) => {
        const config = ACTION_CONFIG[a.status] || ACTION_CONFIG.pending;
        const Icon = config.icon;
        return (
          <div key={a.id} className="flex items-start gap-2 text-xs">
            <Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${config.color}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{config.label}</span>
                <span className="text-muted-foreground">{formatTime(a.createdAt)}</span>
              </div>
              {a.comment && (
                <p className="text-muted-foreground mt-0.5">{a.comment}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create ApprovalDialog**

```tsx
// frontend/src/app/admin/templates/components/ApprovalDialog.tsx
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { workflowApi } from "@/extensions/workflow/api";
import type { TemplateApproval } from "@/extensions/workflow/types";
import { ApprovalHistoryPanel } from "./ApprovalHistoryPanel";

interface ApprovalDialogProps {
  templateId: string;
  templateName: string;
  approvals: TemplateApproval[];
  onAction: () => void;
  onClose: () => void;
}

export function ApprovalDialog({
  templateId,
  templateName,
  approvals,
  onAction,
  onClose,
}: ApprovalDialogProps) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: "approved" | "rejected") => {
    setLoading(true);
    try {
      await workflowApi.reviewApproval(templateId, action, comment || undefined);
      toast.success(action === "approved" ? "已通过并发布" : "已拒绝");
      onAction();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card rounded-xl border shadow-lg w-full max-w-lg mx-4 overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h3 className="text-base font-semibold">模板审批</h3>
          <p className="text-sm text-muted-foreground mt-1">{templateName}</p>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Approval history */}
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">审批记录</div>
            <ApprovalHistoryPanel approvals={approvals} />
          </div>

          {/* Comment */}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">审批意见</label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm border rounded-lg bg-background resize-none"
              placeholder="输入审批意见（可选）"
            />
          </div>
        </div>

        <div className="px-6 py-4 border-t flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => handleAction("rejected")}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "拒绝"}
          </button>
          <button
            onClick={() => handleAction("approved")}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "通过并发布"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create SubmitApprovalDialog**

```tsx
// frontend/src/app/admin/templates/components/SubmitApprovalDialog.tsx
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { workflowApi } from "@/extensions/workflow/api";

interface SubmitApprovalDialogProps {
  templateId: string;
  templateName: string;
  onSubmit: () => void;
  onClose: () => void;
}

export function SubmitApprovalDialog({
  templateId,
  templateName,
  onSubmit,
  onClose,
}: SubmitApprovalDialogProps) {
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await workflowApi.submitApproval(templateId);
      toast.success("已提交审批，等待超级管理员审核");
      onSubmit();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-card rounded-xl border shadow-lg w-full max-w-sm mx-4 overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h3 className="text-base font-semibold">提交审批确认</h3>
        </div>
        <div className="px-6 py-4">
          <p className="text-sm text-muted-foreground">
            确认将「{templateName}」提交发布审批？
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            提交后模板状态将变为"待审批"，超级管理员审批通过后自动发布。
          </p>
        </div>
        <div className="px-6 py-4 border-t flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "确认提交"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/templates/components/ApprovalDialog.tsx frontend/src/app/admin/templates/components/ApprovalHistoryPanel.tsx frontend/src/app/admin/templates/components/SubmitApprovalDialog.tsx
git commit -m "feat(admin): add approval UI components — dialog, history panel, submit confirmation"
```

---

## Task 12: Integration — Restart Services and Verify

- [ ] **Step 1: Run backend tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_workflow_template.py -v`
Expected: All template tests PASS

- [ ] **Step 2: Restart backend container**

Run: `docker compose -p eai-docker restart gateway`

- [ ] **Step 3: Run database migration**

Run: `docker exec deer-flow-gateway python -m app.extensions.workflow.migration`

- [ ] **Step 4: Restart frontend container**

Run: `docker compose -p eai-docker restart frontend`

- [ ] **Step 5: Manual verification checklist**

Browse to `http://localhost:2026/admin/templates` and verify:

1. Template list loads with status badges (draft/published)
2. "新建模板" navigates to `/admin/templates/new` (NOT `/projects/new`)
3. New template page shows WorkflowEditor with empty canvas
4. Can add nodes, connect them, set node properties
5. Can set org binding on phase nodes (department dropdown)
6. Can fill template description and select visible departments
7. "保存" creates the template and updates URL to `/admin/templates/[id]`
8. Clicking "编辑" on a template card opens the editor with loaded DAG
9. "发布" (super admin) publishes directly
10. List page shows updated status after publish
11. "删除" removes the template

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat(admin): complete template management redesign — editor, approval, visibility"
```
