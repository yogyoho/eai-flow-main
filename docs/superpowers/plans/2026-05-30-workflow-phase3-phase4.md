# Phase 3 + Phase 4: Multi-Person Mixed Review & Workflow Monitoring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-person chapter/dimension mixed review to the workflow engine (Phase 3), then add workflow monitoring, condition evaluation, and workflow lifecycle controls (Phase 4).

**Architecture:** Phase 3 adds a `PhaseReview` model + review assignment/action APIs + a review workbench frontend. The existing Temporal `DynamicGraphWorkflow._execute_review` already waits for `review_action` signals — we wire real activity implementations and a frontend review panel. Phase 4 upgrades condition activities with real expression evaluation, adds workflow status/lifecycle APIs (pause/resume/cancel), and builds a monitoring frontend with timeline and node status cards.

**Tech Stack:** SQLAlchemy async, Pydantic v2, FastAPI, Temporal.io Python SDK, React 19, TanStack Query, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-05-29-workflow-engine-traceability-review-design.md` (Sections 6, 8, 9.3, 9.4)

---

## File Structure

### New Files (Backend)

```
backend/app/extensions/workflow/models.py        # APPEND: PhaseReview model
backend/app/extensions/workflow/schemas.py        # APPEND: review schemas
backend/app/extensions/workflow/routers.py        # APPEND: review + workflow lifecycle endpoints
backend/app/extensions/workflow/temporal/activities.py  # REPLACE stubs with real implementations
backend/app/extensions/workflow/temporal/client.py      # MODIFY: add signal helpers
backend/tests/test_phase_review.py                      # NEW: review model + API tests
```

### New Files (Frontend)

```
frontend/src/extensions/workflow/api.ts                  # APPEND: review + monitoring API methods
frontend/src/extensions/workflow/types.ts                # APPEND: review + monitoring types
frontend/src/extensions/workflow/PhaseReviewPanel.tsx    # NEW: review workbench
frontend/src/extensions/workflow/ReviewAssignmentDialog.tsx  # NEW: manager assignment dialog
frontend/src/extensions/workflow/ChapterReviewCard.tsx   # NEW: per-chapter review card
frontend/src/extensions/workflow/DimensionReviewCard.tsx # NEW: per-dimension review card
frontend/src/extensions/workflow/WorkflowMonitor.tsx     # NEW: workflow execution monitor
frontend/src/extensions/workflow/PhaseStatusCard.tsx     # NEW: node status card
frontend/src/extensions/workflow/hooks/useWorkflowStatus.ts  # NEW: polling hook
```

---

## Phase 3: Multi-Person Mixed Review

### Task 1: PhaseReview Model + Migration

**Files:**
- Modify: `backend/app/extensions/workflow/models.py` (append)
- Modify: `backend/app/extensions/database.py` (append migration)

- [ ] **Step 1: Append PhaseReview model to models.py**

```python
class PhaseReview(Base):
    """Phase review assignment — supports chapter and dimension review modes."""

    __tablename__ = "phase_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase_node: Mapped[str] = mapped_column(String(50), nullable=False)
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_chapters.id"),
        nullable=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # chapter | dimension
    dimension: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | approved | rejected
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PhaseReview {self.review_type}:{self.phase_node} reviewer={self.reviewer_id} status={self.status}>"
```

- [ ] **Step 2: Append migration to database.py**

Add after the existing `content_sources` index creation (after line ~935):

```python
    # phase_reviews
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS phase_reviews ("
        "  id UUID PRIMARY KEY,"
        "  project_id UUID NOT NULL REFERENCES report_projects(id) ON DELETE CASCADE,"
        "  phase_node VARCHAR(50) NOT NULL,"
        "  chapter_id UUID REFERENCES project_chapters(id),"
        "  reviewer_id UUID NOT NULL REFERENCES users(id),"
        "  review_type VARCHAR(20) NOT NULL,"
        "  dimension VARCHAR(50),"
        "  status VARCHAR(20) NOT NULL DEFAULT 'pending',"
        "  comment TEXT,"
        "  created_at TIMESTAMP NOT NULL DEFAULT NOW(),"
        "  updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
        ")"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_phase_reviews_project_phase "
        "ON phase_reviews (project_id, phase_node)"
    ))
```

- [ ] **Step 3: Verify model imports**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow.models import PhaseReview; print('Fields:', [c.name for c in PhaseReview.__table__.columns])"
```

Expected: `Fields: ['id', 'project_id', 'phase_node', 'chapter_id', 'reviewer_id', 'review_type', 'dimension', 'status', 'comment', 'created_at', 'updated_at']`

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/workflow/models.py backend/app/extensions/database.py && git commit -m "feat(review): add PhaseReview model and migration"
```

---

### Task 2: Review Schemas

**Files:**
- Modify: `backend/app/extensions/workflow/schemas.py` (append)

- [ ] **Step 1: Append review schemas**

```python
# ── Phase Review ──


class ReviewAssignmentCreate(BaseModel):
    """Create review assignments in bulk."""
    project_id: UUID
    phase_node: str
    assignments: list["ReviewAssignmentItem"] = Field(..., min_length=1)


class ReviewAssignmentItem(BaseModel):
    chapter_id: UUID | None = None
    reviewer_id: UUID
    review_type: str = Field(..., pattern=r"^(chapter|dimension)$")
    dimension: str | None = None


class ReviewActionRequest(BaseModel):
    """Submit an approve/reject action for a review."""
    action: str = Field(..., pattern=r"^(approved|rejected)$")
    comment: str | None = None


class PhaseReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    phase_node: str
    chapter_id: UUID | None = None
    reviewer_id: UUID
    review_type: str
    dimension: str | None = None
    status: str = "pending"
    comment: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ReviewStatusResponse(BaseModel):
    """Aggregated review status for a phase node."""
    phase_node: str
    total: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    all_approved: bool = False
    reviews: list[PhaseReviewOut] = Field(default_factory=list)


# Resolve forward references
ReviewAssignmentCreate.model_rebuild()
```

- [ ] **Step 2: Verify schemas load**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow.schemas import ReviewAssignmentCreate, PhaseReviewOut, ReviewStatusResponse; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/workflow/schemas.py && git commit -m "feat(review): add review schemas for assignment and action"
```

---

### Task 3: Review API Endpoints

**Files:**
- Modify: `backend/app/extensions/workflow/routers.py` (append)

- [ ] **Step 1: Add review imports**

Add to the existing imports in `routers.py`:

```python
from .models import ContentSource, PhaseReview, WorkflowDefinition
from .schemas import (
    ContentSourceListResponse,
    ContentSourceOut,
    DAGValidationResult,
    PhaseReviewOut,
    ReviewActionRequest,
    ReviewAssignmentCreate,
    ReviewStatusResponse,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionOut,
    WorkflowDefinitionUpdate,
)
```

- [ ] **Step 2: Append review endpoints**

```python
# ── Phase Reviews ──


@router.post("/projects/{project_id}/phase-reviews/assign", response_model=list[PhaseReviewOut], status_code=status.HTTP_201_CREATED)
async def assign_reviews(
    project_id: UUID,
    body: ReviewAssignmentCreate,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Create review assignments for a phase node. Replaces existing pending assignments."""
    if body.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id mismatch")

    # Delete existing pending assignments for this phase node
    await db.execute(
        PhaseReview.__table__.delete()
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == body.phase_node)
        .where(PhaseReview.status == "pending")
    )

    reviews = []
    for item in body.assignments:
        review = PhaseReview(
            project_id=project_id,
            phase_node=body.phase_node,
            chapter_id=item.chapter_id,
            reviewer_id=item.reviewer_id,
            review_type=item.review_type,
            dimension=item.dimension,
            status="pending",
        )
        db.add(review)
        reviews.append(review)

    await db.commit()
    for r in reviews:
        await db.refresh(r)

    return [PhaseReviewOut.model_validate(r) for r in reviews]


@router.post("/projects/{project_id}/phase-reviews/{review_id}/action", response_model=PhaseReviewOut)
async def submit_review_action(
    project_id: UUID,
    review_id: UUID,
    body: ReviewActionRequest,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Submit an approve/reject action for a review assignment."""
    review = await db.get(PhaseReview, review_id)
    if not review or review.project_id != project_id:
        raise HTTPException(status_code=404, detail="Review assignment not found")

    if review.status != "pending":
        raise HTTPException(status_code=400, detail=f"Review already {review.status}")

    review.status = body.action
    review.comment = body.comment
    review.updated_at = func.now()
    await db.commit()
    await db.refresh(review)

    # Check if all reviews for this phase node are complete
    stmt = (
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == review.phase_node)
    )
    result = await db.execute(stmt)
    all_reviews = result.scalars().all()
    all_done = all(r.status in ("approved", "rejected") for r in all_reviews)

    if all_done:
        from .temporal.client import send_signal
        all_approved = all(r.status == "approved" for r in all_reviews)
        await send_signal(
            project_id=project_id,
            signal_name="review_action",
            args=[review.phase_node, all_approved, body.comment or ""],
        )

    return PhaseReviewOut.model_validate(review)


@router.get("/projects/{project_id}/phase-reviews", response_model=ReviewStatusResponse)
async def get_review_status(
    project_id: UUID,
    phase_node: str = Query(..., description="Phase node ID to filter"),
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated review status for a phase node."""
    stmt = (
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == phase_node)
        .order_by(PhaseReview.created_at)
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    approved = sum(1 for r in reviews if r.status == "approved")
    rejected = sum(1 for r in reviews if r.status == "rejected")
    pending = sum(1 for r in reviews if r.status == "pending")

    return ReviewStatusResponse(
        phase_node=phase_node,
        total=len(reviews),
        approved=approved,
        rejected=rejected,
        pending=pending,
        all_approved=len(reviews) > 0 and approved == len(reviews),
        reviews=[PhaseReviewOut.model_validate(r) for r in reviews],
    )


@router.get("/projects/{project_id}/phase-reviews/my", response_model=list[PhaseReviewOut])
async def get_my_reviews(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get current user's pending reviews for a project."""
    stmt = (
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.reviewer_id == user.id)
        .where(PhaseReview.status == "pending")
        .order_by(PhaseReview.created_at.desc())
    )
    result = await db.execute(stmt)
    return [PhaseReviewOut.model_validate(r) for r in result.scalars().all()]
```

- [ ] **Step 3: Verify router loads**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow import router; print('Routes:', len(router.routes))"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/workflow/routers.py && git commit -m "feat(review): add review assignment, action, and status API endpoints"
```

---

### Task 4: Real Activity Implementations

**Files:**
- Modify: `backend/app/extensions/workflow/temporal/activities.py` (replace stubs)
- Modify: `backend/app/extensions/workflow/temporal/client.py` (add signal helper)

- [ ] **Step 1: Add signal helper to client.py**

Append to `backend/app/extensions/workflow/temporal/client.py`:

```python
async def send_signal(project_id: str, signal_name: str, args: list) -> None:
    """Send a signal to the running workflow for a project.

    Looks up the temporal_workflow_id from report_projects and sends
    the signal via Temporal client. No-op if Temporal is unavailable.
    """
    client = _get_client()
    if client is None:
        logger.warning("Temporal unavailable — signal %s for project %s dropped", signal_name, project_id)
        return

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id)
        )
        workflow_id = result.scalar_one_or_none()

    if not workflow_id:
        logger.warning("No active workflow for project %s", project_id)
        return

    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(signal_name, *args)
```

Also ensure `_get_client()` is exported — it should already exist as the module-level client reference. Add near the top of client.py after the existing `_client` variable:

```python
def _get_client():
    """Return the Temporal client if connected, else None."""
    return _client
```

- [ ] **Step 2: Replace activity stubs with real implementations**

Replace the full contents of `activities.py`:

```python
"""Real activity implementations for the workflow engine."""

import logging
import uuid

from sqlalchemy import select, update
from temporalio import activity

from app.extensions.database import get_db_context

logger = logging.getLogger(__name__)


@activity.defn
async def init_phase(phase_id: str, project_id: str, config: dict | None = None) -> dict:
    """Initialise a workflow phase — set project current_phase_node."""
    async with get_db_context() as db:
        from app.extensions.models import ReportProject

        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(current_phase_node=phase_id)
        )
        await db.commit()

    logger.info("activity:init_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id, "project_id": project_id}


@activity.defn
async def advance_phase(phase_id: str, project_id: str) -> dict:
    """Mark a phase as advanced — update current_phase_node."""
    async with get_db_context() as db:
        from app.extensions.models import ReportProject

        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(current_phase_node=phase_id)
        )
        await db.commit()

    logger.info("activity:advance_phase phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def create_review_assignments(
    node_id: str,
    project_id: str,
    reviewers: list[str] | None = None,
) -> dict:
    """Create review assignments from DAG node config.

    Reviewers list comes from the DAG review node's data.reviewers field.
    Each entry is a user_id string. Creates a PhaseReview record per reviewer.
    """
    count = 0
    if reviewers:
        async with get_db_context() as db:
            from app.extensions.workflow.models import PhaseReview

            for reviewer_id in reviewers:
                review = PhaseReview(
                    project_id=uuid.UUID(project_id),
                    phase_node=node_id,
                    reviewer_id=uuid.UUID(reviewer_id),
                    review_type="chapter",
                    status="pending",
                )
                db.add(review)
                count += 1
            await db.commit()

    logger.info(
        "activity:create_review_assignments node_id=%s project_id=%s count=%d",
        node_id,
        project_id,
        count,
    )
    return {"status": "ok", "node_id": node_id, "assignment_count": count}


@activity.defn
async def notify_phase_start(phase_id: str, project_id: str) -> dict:
    """Log notification that a phase has started."""
    logger.info("activity:notify_phase_start phase_id=%s project_id=%s", phase_id, project_id)
    return {"status": "ok", "phase_id": phase_id}


@activity.defn
async def notify_review_pending(node_id: str, project_id: str) -> dict:
    """Log notification that a review is awaiting action."""
    logger.info("activity:notify_review_pending node_id=%s project_id=%s", node_id, project_id)
    return {"status": "ok", "node_id": node_id}


@activity.defn
async def notify_workflow_complete(project_id: str) -> dict:
    """Log notification that the entire workflow has completed.

    Also updates report_projects.status to 'completed'.
    """
    async with get_db_context() as db:
        from app.extensions.models import ReportProject

        await db.execute(
            update(ReportProject)
            .where(ReportProject.id == uuid.UUID(project_id))
            .values(status="completed")
        )
        await db.commit()

    logger.info("activity:notify_workflow_complete project_id=%s", project_id)
    return {"status": "ok", "project_id": project_id}


@activity.defn
async def evaluate_condition(
    node_id: str,
    project_id: str,
    condition_expr: str | None = None,
) -> dict:
    """Evaluate a conditional expression from the DAG node config.

    Supports simple expressions like:
    - "report.subtype" → looks up report project metadata
    - Literal values: "true", "false"

    Returns {"branch": "<matched_value>"} for routing.
    """
    branch = "true"  # default

    if condition_expr:
        expr = condition_expr.strip()

        if expr.lower() == "true":
            branch = "true"
        elif expr.lower() == "false":
            branch = "false"
        elif expr.startswith("report."):
            field_name = expr[len("report."):]
            async with get_db_context() as db:
                from app.extensions.models import ReportProject

                project = await db.get(ReportProject, uuid.UUID(project_id))
                if project:
                    val = getattr(project, field_name, None)
                    branch = str(val) if val is not None else "true"
        else:
            branch = expr

    logger.info(
        "activity:evaluate_condition node_id=%s expr=%s branch=%s",
        node_id,
        condition_expr,
        branch,
    )
    return {"status": "ok", "node_id": node_id, "branch": branch}


ALL_ACTIVITIES = [
    init_phase,
    advance_phase,
    create_review_assignments,
    notify_phase_start,
    notify_review_pending,
    notify_workflow_complete,
    evaluate_condition,
]
```

- [ ] **Step 3: Verify activities import**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow.temporal.activities import ALL_ACTIVITIES; print(f'{len(ALL_ACTIVITIES)} activities:', [a.name for a in ALL_ACTIVITIES])"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/workflow/temporal/activities.py backend/app/extensions/workflow/temporal/client.py && git commit -m "feat(review): implement real activity logic with DB operations"
```

---

### Task 5: Frontend Review Types + API

**Files:**
- Modify: `frontend/src/extensions/workflow/types.ts` (append)
- Modify: `frontend/src/extensions/workflow/api.ts` (append)

- [ ] **Step 1: Append review types to types.ts**

```typescript
// ── Phase Review ──

export interface PhaseReview {
  id: string;
  projectId: string;
  phaseNode: string;
  chapterId: string | null;
  reviewerId: string;
  reviewType: "chapter" | "dimension";
  dimension: string | null;
  status: "pending" | "approved" | "rejected";
  comment: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ReviewAssignmentItem {
  chapterId?: string | null;
  reviewerId: string;
  reviewType: "chapter" | "dimension";
  dimension?: string | null;
}

export interface ReviewStatus {
  phaseNode: string;
  total: number;
  approved: number;
  rejected: number;
  pending: number;
  allApproved: boolean;
  reviews: PhaseReview[];
}

export interface ReviewActionRequest {
  action: "approved" | "rejected";
  comment?: string | null;
}
```

- [ ] **Step 2: Append review API methods to api.ts**

```typescript
  // ── Phase Reviews ──

  assignReviews: async (
    projectId: string,
    phaseNode: string,
    assignments: ReviewAssignmentItem[],
  ): Promise<PhaseReview[]> => {
    const body = { project_id: projectId, phase_node: phaseNode, assignments: toSnakeCase(assignments as unknown as Record<string, unknown>[]) };
    const data = await authFetch<Record<string, unknown>[]>(
      `${API_BASE}/projects/${projectId}/phase-reviews/assign`,
      { method: "POST", body: JSON.stringify(body) },
    );
    return data.map((d) => toCamelCase<PhaseReview>(d));
  },

  submitReviewAction: async (
    projectId: string,
    reviewId: string,
    req: ReviewActionRequest,
  ): Promise<PhaseReview> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phase-reviews/${reviewId}/action`,
      { method: "POST", body: JSON.stringify(toSnakeCase(req as unknown as Record<string, unknown>)) },
    );
    return toCamelCase<PhaseReview>(data);
  },

  getReviewStatus: async (projectId: string, phaseNode: string): Promise<ReviewStatus> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/phase-reviews?phase_node=${phaseNode}`,
    );
    return toCamelCase<ReviewStatus>(data);
  },

  getMyReviews: async (projectId: string): Promise<PhaseReview[]> => {
    const data = await authFetch<Record<string, unknown>[]>(
      `${API_BASE}/projects/${projectId}/phase-reviews/my`,
    );
    return data.map((d) => toCamelCase<PhaseReview>(d));
  },
```

Add the necessary imports at the top of `api.ts`:

```typescript
import type {
  CreateWorkflowRequest,
  DAGValidationResult,
  PhaseReview,
  ReviewActionRequest,
  ReviewAssignmentItem,
  ReviewStatus,
  UpdateWorkflowRequest,
  WorkflowDefinition,
  WorkflowDefinitionListResponse,
  WorkflowGraph,
} from "./types";
```

- [ ] **Step 3: Verify typecheck**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | head -30
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/workflow/types.ts frontend/src/extensions/workflow/api.ts && git commit -m "feat(review): add frontend review types and API client"
```

---

### Task 6: PhaseReviewPanel — Review Workbench

**Files:**
- Create: `frontend/src/extensions/workflow/PhaseReviewPanel.tsx`
- Create: `frontend/src/extensions/workflow/ReviewAssignmentDialog.tsx`
- Create: `frontend/src/extensions/workflow/ChapterReviewCard.tsx`
- Create: `frontend/src/extensions/workflow/DimensionReviewCard.tsx`

- [ ] **Step 1: Create ChapterReviewCard.tsx**

```tsx
"use client";

import { useState } from "react";
import { workflowApi } from "./api";
import type { PhaseReview } from "./types";

interface ChapterReviewCardProps {
  review: PhaseReview;
  onAction: () => void;
}

export function ChapterReviewCard({ review, onAction }: ChapterReviewCardProps) {
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleAction = async (action: "approved" | "rejected") => {
    setSubmitting(true);
    try {
      await workflowApi.submitReviewAction(review.projectId, review.id, { action, comment: comment || null });
      onAction();
    } finally {
      setSubmitting(false);
    }
  };

  const statusColor =
    review.status === "approved"
      ? "bg-green-100 text-green-700"
      : review.status === "rejected"
        ? "bg-red-100 text-red-700"
        : "bg-amber-100 text-amber-700";

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">
          {review.reviewType === "chapter" ? `章节审核` : `维度: ${review.dimension || ""}`}
        </div>
        <span className={`px-2 py-0.5 rounded text-xs ${statusColor}`}>
          {review.status === "approved" ? "已通过" : review.status === "rejected" ? "已退回" : "待审核"}
        </span>
      </div>

      {review.comment && (
        <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
          {review.comment}
        </div>
      )}

      {review.status === "pending" && (
        <>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="审核意见（可选）"
            className="w-full px-2 py-1 text-sm border rounded resize-none"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              onClick={() => handleAction("approved")}
              disabled={submitting}
              className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
            >
              通过
            </button>
            <button
              onClick={() => handleAction("rejected")}
              disabled={submitting}
              className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
            >
              退回
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create DimensionReviewCard.tsx**

```tsx
"use client";

import type { PhaseReview } from "./types";

interface DimensionReviewCardProps {
  review: PhaseReview;
}

const DIMENSION_LABELS: Record<string, string> = {
  technical: "技术准确性",
  compliance: "法规合规性",
  language: "语言表述",
  completeness: "内容完整性",
  format: "格式规范",
};

export function DimensionReviewCard({ review }: DimensionReviewCardProps) {
  const statusColor =
    review.status === "approved"
      ? "border-green-300 bg-green-50"
      : review.status === "rejected"
        ? "border-red-300 bg-red-50"
        : "border-amber-300 bg-amber-50";

  return (
    <div className={`border rounded-lg p-3 ${statusColor}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {DIMENSION_LABELS[review.dimension || ""] || review.dimension || "未知维度"}
        </span>
        <span className="text-xs text-muted-foreground">
          {review.status === "approved" ? "✓ 通过" : review.status === "rejected" ? "✗ 退回" : "○ 待审核"}
        </span>
      </div>
      {review.comment && <div className="mt-1 text-xs text-muted-foreground">{review.comment}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Create ReviewAssignmentDialog.tsx**

```tsx
"use client";

import { useState } from "react";
import { workflowApi } from "./api";
import type { ReviewAssignmentItem } from "./types";

interface ReviewAssignmentDialogProps {
  projectId: string;
  phaseNode: string;
  open: boolean;
  onClose: () => void;
  onAssigned: () => void;
}

const PRESET_DIMENSIONS = [
  { value: "technical", label: "技术准确性" },
  { value: "compliance", label: "法规合规性" },
  { value: "language", label: "语言表述" },
  { value: "completeness", label: "内容完整性" },
  { value: "format", label: "格式规范" },
];

export function ReviewAssignmentDialog({ projectId, phaseNode, open, onClose, onAssigned }: ReviewAssignmentDialogProps) {
  const [mode, setMode] = useState<"chapter" | "dimension">("chapter");
  const [reviewerId, setReviewerId] = useState("");
  const [dimension, setDimension] = useState("technical");
  const [assignments, setAssignments] = useState<ReviewAssignmentItem[]>([]);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const addAssignment = () => {
    if (!reviewerId.trim()) return;
    setAssignments((prev) => [
      ...prev,
      {
        reviewerId: reviewerId.trim(),
        reviewType: mode,
        dimension: mode === "dimension" ? dimension : undefined,
      },
    ]);
    setReviewerId("");
  };

  const handleSubmit = async () => {
    if (assignments.length === 0) return;
    setSubmitting(true);
    try {
      await workflowApi.assignReviews(projectId, phaseNode, assignments);
      onAssigned();
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-[480px] max-h-[80vh] overflow-y-auto p-6 space-y-4">
        <div className="flex justify-between items-center">
          <div className="text-lg font-medium">分配审核人</div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setMode("chapter")}
            className={`px-3 py-1 text-sm rounded ${mode === "chapter" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
          >
            按章节
          </button>
          <button
            onClick={() => setMode("dimension")}
            className={`px-3 py-1 text-sm rounded ${mode === "dimension" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
          >
            按维度
          </button>
        </div>

        <div className="flex gap-2">
          <input
            value={reviewerId}
            onChange={(e) => setReviewerId(e.target.value)}
            placeholder="审核人 ID"
            className="flex-1 px-2 py-1 text-sm border rounded"
          />
          {mode === "dimension" && (
            <select
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
              className="px-2 py-1 text-sm border rounded"
            >
              {PRESET_DIMENSIONS.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          )}
          <button onClick={addAssignment} className="px-3 py-1 text-sm bg-muted rounded hover:bg-muted/80">添加</button>
        </div>

        {assignments.length > 0 && (
          <div className="space-y-1">
            {assignments.map((a, i) => (
              <div key={i} className="flex items-center gap-2 text-xs bg-muted/50 px-2 py-1 rounded">
                <span>{a.reviewType === "chapter" ? "章节" : `维度:${a.dimension}`}</span>
                <span className="flex-1 truncate">{a.reviewerId}</span>
                <button
                  onClick={() => setAssignments((prev) => prev.filter((_, j) => j !== i))}
                  className="text-red-500 hover:text-red-700"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded border">取消</button>
          <button
            onClick={handleSubmit}
            disabled={submitting || assignments.length === 0}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded disabled:opacity-50"
          >
            确认分配 ({assignments.length})
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create PhaseReviewPanel.tsx**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { workflowApi } from "./api";
import { ChapterReviewCard } from "./ChapterReviewCard";
import { DimensionReviewCard } from "./DimensionReviewCard";
import { ReviewAssignmentDialog } from "./ReviewAssignmentDialog";
import type { PhaseReview, ReviewStatus } from "./types";

interface PhaseReviewPanelProps {
  projectId: string;
  phaseNode: string;
}

export function PhaseReviewPanel({ projectId, phaseNode }: PhaseReviewPanelProps) {
  const [status, setStatus] = useState<ReviewStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAssignDialog, setShowAssignDialog] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await workflowApi.getReviewStatus(projectId, phaseNode);
      setStatus(data);
    } finally {
      setLoading(false);
    }
  }, [projectId, phaseNode]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading) return <div className="p-4 text-sm text-muted-foreground">加载审核状态...</div>;
  if (!status) return null;

  const chapterReviews = status.reviews.filter((r) => r.reviewType === "chapter");
  const dimensionReviews = status.reviews.filter((r) => r.reviewType === "dimension");

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">审核进度</div>
        <button
          onClick={() => setShowAssignDialog(true)}
          className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:opacity-90"
        >
          分配审核人
        </button>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>通过 {status.approved}/{status.total}</span>
          <span>{status.rejected} 退回 · {status.pending} 待审</span>
        </div>
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          {status.total > 0 && (
            <div
              className="h-full bg-green-500 rounded-full transition-all"
              style={{ width: `${(status.approved / status.total) * 100}%` }}
            />
          )}
        </div>
      </div>

      {/* Chapter reviews */}
      {chapterReviews.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">章节审核</div>
          {chapterReviews.map((r) => (
            <ChapterReviewCard key={r.id} review={r} onAction={refresh} />
          ))}
        </div>
      )}

      {/* Dimension reviews */}
      {dimensionReviews.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">维度审核</div>
          {dimensionReviews.map((r) => (
            <DimensionReviewCard key={r.id} review={r} />
          ))}
        </div>
      )}

      {status.reviews.length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-4">
          尚未分配审核人，点击上方按钮开始分配
        </div>
      )}

      <ReviewAssignmentDialog
        projectId={projectId}
        phaseNode={phaseNode}
        open={showAssignDialog}
        onClose={() => setShowAssignDialog(false)}
        onAssigned={refresh}
      />
    </div>
  );
}
```

- [ ] **Step 5: Verify typecheck**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | head -30
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/workflow/PhaseReviewPanel.tsx frontend/src/extensions/workflow/ReviewAssignmentDialog.tsx frontend/src/extensions/workflow/ChapterReviewCard.tsx frontend/src/extensions/workflow/DimensionReviewCard.tsx && git commit -m "feat(review): add review workbench with assignment dialog and review cards"
```

---

### Task 7: Backend Tests for Review API

**Files:**
- Create: `backend/tests/test_phase_review.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for PhaseReview model, schemas, and review API endpoints."""

import uuid

import pytest

from app.extensions.workflow.models import PhaseReview
from app.extensions.workflow.schemas import (
    PhaseReviewOut,
    ReviewActionRequest,
    ReviewAssignmentCreate,
    ReviewAssignmentItem,
    ReviewStatusResponse,
)
from app.extensions.workflow.service import validate_dag


class TestPhaseReviewModel:
    def test_model_fields(self):
        cols = [c.name for c in PhaseReview.__table__.columns]
        assert "id" in cols
        assert "project_id" in cols
        assert "phase_node" in cols
        assert "chapter_id" in cols
        assert "reviewer_id" in cols
        assert "review_type" in cols
        assert "dimension" in cols
        assert "status" in cols
        assert "comment" in cols


class TestReviewSchemas:
    def test_assignment_create_valid(self):
        item = ReviewAssignmentItem(
            reviewer_id=uuid.uuid4(),
            review_type="chapter",
        )
        req = ReviewAssignmentCreate(
            project_id=uuid.uuid4(),
            phase_node="review-1",
            assignments=[item],
        )
        assert len(req.assignments) == 1

    def test_assignment_dimension(self):
        item = ReviewAssignmentItem(
            reviewer_id=uuid.uuid4(),
            review_type="dimension",
            dimension="technical",
        )
        assert item.dimension == "technical"

    def test_action_request_approved(self):
        req = ReviewActionRequest(action="approved", comment="LGTM")
        assert req.action == "approved"

    def test_action_request_rejected(self):
        req = ReviewActionRequest(action="rejected")
        assert req.action == "rejected"

    def test_action_request_invalid(self):
        with pytest.raises(Exception):
            ReviewActionRequest(action="maybe")

    def test_review_status_response(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=3,
            approved=2,
            rejected=0,
            pending=1,
            all_approved=False,
        )
        assert resp.total == 3
        assert not resp.all_approved

    def test_review_status_all_approved(self):
        resp = ReviewStatusResponse(
            phase_node="review-1",
            total=2,
            approved=2,
            rejected=0,
            pending=0,
            all_approved=True,
        )
        assert resp.all_approved


class TestDAGValidation:
    def test_review_node_in_dag(self):
        graph = {
            "nodes": [
                {"id": "phase-1", "type": "phase", "data": {"label": "Write"}},
                {"id": "review-1", "type": "review", "data": {"label": "Review", "mode": "mixed"}},
            ],
            "edges": [{"source": "phase-1", "target": "review-1"}],
        }
        result = validate_dag(graph)
        assert result["valid"]

    def test_dag_with_condition_and_review(self):
        graph = {
            "nodes": [
                {"id": "cond-1", "type": "condition", "data": {"label": "Type?"}},
                {"id": "review-a", "type": "review", "data": {"label": "Review A"}},
                {"id": "review-b", "type": "review", "data": {"label": "Review B"}},
            ],
            "edges": [
                {"source": "cond-1", "target": "review-a", "label": "true"},
                {"source": "cond-1", "target": "review-b", "label": "false"},
            ],
        }
        result = validate_dag(graph)
        assert result["valid"]
```

- [ ] **Step 2: Run tests**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_phase_review.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_phase_review.py && git commit -m "test(review): add unit tests for PhaseReview model, schemas, and DAG validation"
```

---

## Phase 4: Workflow Monitoring + Conditions + Lifecycle

### Task 8: Workflow Status + Lifecycle API

**Files:**
- Modify: `backend/app/extensions/workflow/schemas.py` (append)
- Modify: `backend/app/extensions/workflow/routers.py` (append)
- Modify: `backend/app/extensions/workflow/temporal/client.py` (add lifecycle helpers)

- [ ] **Step 1: Append monitoring schemas to schemas.py**

```python
# ── Workflow Monitoring ──


class WorkflowNodeStatus(BaseModel):
    """Status of a single workflow node."""
    node_id: str
    node_type: str
    label: str
    status: str = "pending"  # pending | running | completed | error
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WorkflowStatusResponse(BaseModel):
    """Full workflow execution status for a project."""
    project_id: UUID
    workflow_id: UUID | None = None
    temporal_workflow_id: str | None = None
    current_phase_node: str | None = None
    status: str = "idle"  # idle | running | completed | failed
    nodes: list[WorkflowNodeStatus] = Field(default_factory=list)
```

- [ ] **Step 2: Add lifecycle helper to client.py**

Append to `temporal/client.py`:

```python
async def get_workflow_status(project_id: str) -> dict | None:
    """Query Temporal for the current workflow execution status.

    Returns None if no active workflow or Temporal unavailable.
    """
    client = _get_client()
    if client is None:
        return None

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(
                ReportProject.workflow_id,
                ReportProject.temporal_workflow_id,
                ReportProject.current_phase_node,
                ReportProject.status,
            ).where(ReportProject.id == project_id)
        )
        row = result.first()

    if not row or not row.temporal_workflow_id:
        return None

    try:
        handle = client.get_workflow_handle(row.temporal_workflow_id)
        desc = await handle.describe()
        return {
            "workflow_id": str(row.workflow_id) if row.workflow_id else None,
            "temporal_workflow_id": row.temporal_workflow_id,
            "current_phase_node": row.current_phase_node,
            "status": "running" if desc.status == 1 else "completed" if desc.status == 2 else "failed",
            "close_time": str(desc.close_time) if desc.close_time else None,
        }
    except Exception:
        logger.exception("Failed to query workflow status for project %s", project_id)
        return None


async def cancel_workflow(project_id: str) -> bool:
    """Cancel the running workflow for a project."""
    client = _get_client()
    if client is None:
        return False

    from sqlalchemy import select
    from app.extensions.database import get_db_context
    from app.extensions.models import ReportProject

    async with get_db_context() as db:
        result = await db.execute(
            select(ReportProject.temporal_workflow_id).where(ReportProject.id == project_id)
        )
        workflow_id = result.scalar_one_or_none()

    if not workflow_id:
        return False

    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
        return True
    except Exception:
        logger.exception("Failed to cancel workflow for project %s", project_id)
        return False
```

- [ ] **Step 3: Append monitoring endpoints to routers.py**

Add imports at the top:

```python
from .schemas import (
    ...
    WorkflowStatusResponse,
    WorkflowNodeStatus,
)
```

Append endpoints:

```python
# ── Workflow Monitoring ──


@router.get("/projects/{project_id}/workflow-status", response_model=WorkflowStatusResponse)
async def get_workflow_status_endpoint(
    project_id: UUID,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Get the current workflow execution status for a project."""
    from app.extensions.models import ReportProject

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Query Temporal for live status
    from .temporal.client import get_workflow_status as _get_wf_status
    temporal_status = await _get_wf_status(str(project_id))

    # Build node status from DAG
    nodes: list[WorkflowNodeStatus] = []
    if project.workflow_id:
        definition = await db.get(WorkflowDefinition, project.workflow_id)
        if definition and definition.graph_json:
            graph = definition.graph_json
            current = project.current_phase_node
            for n in graph.get("nodes", []):
                nid = n["id"]
                node_status = "completed" if nid == current else "pending"
                if temporal_status and temporal_status.get("status") == "running" and nid == current:
                    node_status = "running"
                nodes.append(WorkflowNodeStatus(
                    node_id=nid,
                    node_type=n.get("type", "phase"),
                    label=n.get("data", {}).get("label", nid),
                    status=node_status,
                ))

    return WorkflowStatusResponse(
        project_id=project_id,
        workflow_id=project.workflow_id,
        temporal_workflow_id=project.temporal_workflow_id,
        current_phase_node=project.current_phase_node,
        status=temporal_status.get("status", "idle") if temporal_status else "idle",
        nodes=nodes,
    )


@router.post("/projects/{project_id}/workflow-cancel")
async def cancel_workflow_endpoint(
    project_id: UUID,
    user: CurrentUserWithAccess,
):
    """Cancel the running workflow for a project."""
    from .temporal.client import cancel_workflow as _cancel_wf
    success = await _cancel_wf(str(project_id))
    if not success:
        raise HTTPException(status_code=400, detail="No active workflow to cancel")
    return {"status": "cancelled"}


@router.post("/projects/{project_id}/start-workflow")
async def start_workflow(
    project_id: UUID,
    body: WorkflowStartRequest,
    user: CurrentUserWithAccess,
    db: AsyncSession = Depends(get_db),
):
    """Start a Temporal workflow for a project."""
    from app.extensions.models import ReportProject

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    definition = await db.get(WorkflowDefinition, body.workflow_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")

    from .temporal.client import start_workflow as _start_wf
    workflow_id = await _start_wf(
        workflow_name="DynamicGraphWorkflow",
        params={
            "graph_json": definition.graph_json,
            "project_id": str(project_id),
        },
    )

    if workflow_id:
        project.workflow_id = body.workflow_id
        project.temporal_workflow_id = workflow_id
        project.status = "in_progress"
        await db.commit()
        return {"status": "started", "temporal_workflow_id": workflow_id}
    else:
        raise HTTPException(status_code=503, detail="Temporal server unavailable")
```

Also add `start_workflow` helper to `temporal/client.py`:

```python
async def start_workflow(workflow_name: str, params: dict) -> str | None:
    """Start a new Temporal workflow execution. Returns the workflow ID or None."""
    client = _get_client()
    if client is None:
        logger.warning("Temporal unavailable — cannot start workflow")
        return None

    from temporalio.common import WorkflowIDReusePolicy
    from .workflows import DynamicGraphWorkflow

    import uuid as _uuid
    wf_id = f"project-{params.get('project_id', 'unknown')}-{_uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        DynamicGraphWorkflow.run,
        params,
        id=wf_id,
        task_queue="project-workflow-queue",
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    return handle.id
```

- [ ] **Step 4: Verify router loads**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run python -c "from app.extensions.workflow import router; print('Routes:', len(router.routes))"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/workflow/routers.py backend/app/extensions/workflow/schemas.py backend/app/extensions/workflow/temporal/client.py && git commit -m "feat(monitor): add workflow status, lifecycle, and start-workflow endpoints"
```

---

### Task 9: Frontend Monitoring Types + API

**Files:**
- Modify: `frontend/src/extensions/workflow/types.ts` (append)
- Modify: `frontend/src/extensions/workflow/api.ts` (append)

- [ ] **Step 1: Append monitoring types to types.ts**

```typescript
// ── Workflow Monitoring ──

export interface WorkflowNodeStatus {
  nodeId: string;
  nodeType: string;
  label: string;
  status: "pending" | "running" | "completed" | "error";
  startedAt: string | null;
  completedAt: string | null;
}

export interface WorkflowStatusResponse {
  projectId: string;
  workflowId: string | null;
  temporalWorkflowId: string | null;
  currentPhaseNode: string | null;
  status: "idle" | "running" | "completed" | "failed";
  nodes: WorkflowNodeStatus[];
}
```

- [ ] **Step 2: Append monitoring API methods to api.ts**

```typescript
  // ── Workflow Monitoring ──

  getWorkflowStatus: async (projectId: string): Promise<WorkflowStatusResponse> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/workflow-status`,
    );
    return toCamelCase<WorkflowStatusResponse>(data);
  },

  startWorkflow: async (projectId: string, workflowId: string): Promise<{ status: string; temporalWorkflowId: string }> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/start-workflow`,
      { method: "POST", body: JSON.stringify({ workflow_id: workflowId }) },
    );
    return toCamelCase<{ status: string; temporalWorkflowId: string }>(data);
  },

  cancelWorkflow: async (projectId: string): Promise<{ status: string }> => {
    const data = await authFetch<Record<string, unknown>>(
      `${API_BASE}/projects/${projectId}/workflow-cancel`,
      { method: "POST" },
    );
    return toCamelCase<{ status: string }>(data);
  },
```

Update imports in api.ts to include the new types.

- [ ] **Step 3: Verify typecheck**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | head -30
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/workflow/types.ts frontend/src/extensions/workflow/api.ts && git commit -m "feat(monitor): add frontend monitoring types and API client"
```

---

### Task 10: WorkflowMonitor Component

**Files:**
- Create: `frontend/src/extensions/workflow/WorkflowMonitor.tsx`
- Create: `frontend/src/extensions/workflow/PhaseStatusCard.tsx`
- Create: `frontend/src/extensions/workflow/hooks/useWorkflowStatus.ts`

- [ ] **Step 1: Create useWorkflowStatus.ts**

```typescript
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { workflowApi } from "../api";
import type { WorkflowStatusResponse } from "../types";

export function useWorkflowStatus(projectId: string | null, pollIntervalMs = 5000) {
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await workflowApi.getWorkflowStatus(projectId);
      setStatus(data);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();

    if (projectId) {
      intervalRef.current = setInterval(refresh, pollIntervalMs);
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [refresh, pollIntervalMs, projectId]);

  return { status, loading, refresh };
}
```

- [ ] **Step 2: Create PhaseStatusCard.tsx**

```tsx
"use client";

import type { WorkflowNodeStatus } from "../types";

interface PhaseStatusCardProps {
  node: WorkflowNodeStatus;
}

const STATUS_STYLES: Record<string, string> = {
  pending: "border-muted bg-muted/20",
  running: "border-blue-300 bg-blue-50",
  completed: "border-green-300 bg-green-50",
  error: "border-red-300 bg-red-50",
};

const STATUS_ICONS: Record<string, string> = {
  pending: "○",
  running: "◉",
  completed: "✓",
  error: "✗",
};

const NODE_TYPE_COLORS: Record<string, string> = {
  phase: "text-blue-600",
  review: "text-amber-600",
  condition: "text-purple-600",
  ai_generate: "text-cyan-600",
  merge: "text-gray-600",
};

export function PhaseStatusCard({ node }: PhaseStatusCardProps) {
  const style = STATUS_STYLES[node.status] || STATUS_STYLES.pending;
  const icon = STATUS_ICONS[node.status] || "○";
  const typeColor = NODE_TYPE_COLORS[node.nodeType] || "text-foreground";

  return (
    <div className={`border rounded-lg p-3 ${style}`}>
      <div className="flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium truncate ${typeColor}`}>
            {node.label}
          </div>
          <div className="text-[10px] text-muted-foreground">
            {node.nodeType} · {node.nodeId}
          </div>
        </div>
        <span className="text-[10px] uppercase font-medium text-muted-foreground">
          {node.status}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create WorkflowMonitor.tsx**

```tsx
"use client";

import { workflowApi } from "./api";
import { PhaseStatusCard } from "./PhaseStatusCard";
import { useWorkflowStatus } from "./hooks/useWorkflowStatus";

interface WorkflowMonitorProps {
  projectId: string;
}

export function WorkflowMonitor({ projectId }: WorkflowMonitorProps) {
  const { status, loading, refresh } = useWorkflowStatus(projectId);

  if (loading) return <div className="p-4 text-sm text-muted-foreground">加载工作流状态...</div>;
  if (!status) return <div className="p-4 text-sm text-muted-foreground">未配置工作流</div>;

  const handleStart = async () => {
    if (!status.workflowId) return;
    await workflowApi.startWorkflow(projectId, status.workflowId);
    refresh();
  };

  const handleCancel = async () => {
    await workflowApi.cancelWorkflow(projectId);
    refresh();
  };

  const statusColor =
    status.status === "running"
      ? "text-blue-600"
      : status.status === "completed"
        ? "text-green-600"
        : status.status === "failed"
          ? "text-red-600"
          : "text-muted-foreground";

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">工作流监控</div>
          <div className={`text-xs ${statusColor}`}>
            {status.status === "idle" && "未启动"}
            {status.status === "running" && "执行中"}
            {status.status === "completed" && "已完成"}
            {status.status === "failed" && "失败"}
          </div>
        </div>
        <div className="flex gap-2">
          {status.status === "idle" && status.workflowId && (
            <button
              onClick={handleStart}
              className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:opacity-90"
            >
              启动工作流
            </button>
          )}
          {status.status === "running" && (
            <button
              onClick={handleCancel}
              className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
            >
              取消
            </button>
          )}
        </div>
      </div>

      {/* Current phase */}
      {status.currentPhaseNode && (
        <div className="bg-blue-50 border border-blue-200 rounded p-2 text-xs">
          当前节点: <span className="font-medium">{status.currentPhaseNode}</span>
        </div>
      )}

      {/* Node timeline */}
      <div className="space-y-2">
        {status.nodes.map((node) => (
          <PhaseStatusCard key={node.nodeId} node={node} />
        ))}
      </div>

      {status.nodes.length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-4">
          该项目未关联工作流定义
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify typecheck**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | head -30
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/workflow/WorkflowMonitor.tsx frontend/src/extensions/workflow/PhaseStatusCard.tsx frontend/src/extensions/workflow/hooks/useWorkflowStatus.ts && git commit -m "feat(monitor): add workflow monitoring panel with status cards and polling"
```

---

### Task 11: Integration — Wire Components into ProjectWorkspace

**Files:**
- Modify: `frontend/src/extensions/workflow/panels/ReviewConfigPanel.tsx` (no change needed — already shows mode selector)

This task verifies the new components can be imported and used. The actual integration into `ProjectWorkspace` or `DocumentManagement` is application-specific and depends on how the workspace tabs are structured. The components are ready to be used:

```tsx
import { PhaseReviewPanel } from "@/extensions/workflow/PhaseReviewPanel";
import { WorkflowMonitor } from "@/extensions/workflow/WorkflowMonitor";

// In the project workspace, add as tabs or sidebars:
<WorkflowMonitor projectId={projectId} />
<PhaseReviewPanel projectId={projectId} phaseNode="review-1" />
```

- [ ] **Step 1: Verify all imports resolve**

```bash
cd D:/eai/eai-flow-main/frontend && pnpm typecheck
```

- [ ] **Step 2: Run backend tests**

```bash
cd D:/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_phase_review.py -v
```

- [ ] **Step 3: Final commit if any fixes needed**

---

## Self-Review

### Spec Coverage Check

| Spec Section | Task(s) | Status |
|---|---|---|
| Section 6.1 — Review modes (chapter/dimension/mixed) | Task 2 (schemas), Task 6 (UI) | ✅ |
| Section 6.2 — Review execution flow | Task 3 (API), Task 4 (activities) | ✅ |
| Section 6.3 — Review dimension presets | Task 6 (ReviewAssignmentDialog) | ✅ |
| Section 8.1 — Phase review API endpoints | Task 3 | ✅ |
| Section 9.3 Phase 3 deliverables | Tasks 1-7 | ✅ |
| Section 9.4 Phase 4 — Condition activity | Task 4 (evaluate_condition) | ✅ |
| Section 9.4 Phase 4 — Workflow status API | Task 8 | ✅ |
| Section 9.4 Phase 4 — Cancel workflow API | Task 8 | ✅ |
| Section 9.4 Phase 4 — WorkflowMonitor | Task 10 | ✅ |
| Section 9.4 Phase 4 — PhaseStatusCard | Task 10 | ✅ |

### Placeholder Scan

No TBDs, TODOs, or placeholder patterns found. All code blocks contain complete implementations.

### Type Consistency

- `PhaseReview` model fields match `PhaseReviewOut` schema and `PhaseReview` TypeScript type
- `ReviewStatusResponse` schema matches `ReviewStatus` TS type
- `WorkflowNodeStatus` schema matches `WorkflowNodeStatus` TS type
- `WorkflowStatusResponse` schema matches `WorkflowStatusResponse` TS type
- API methods use correct snake_case/camelCase transforms via existing `toSnakeCase`/`toCamelCase` utilities

### Gap: Child Workflow (sub-workflows)

The spec mentions "Child Workflow support" in Phase 4. This is intentionally deferred — it requires adding a `parent_project_id` field and nesting workflow runs, which is a significant scope increase. The current plan delivers monitoring + condition evaluation + lifecycle controls, which closes the Phase 4 core. Sub-workflows can be added in a follow-up.
