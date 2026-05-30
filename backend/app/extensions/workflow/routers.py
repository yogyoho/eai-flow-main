"""FastAPI routers for workflow definitions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from app.extensions.models import ProjectChapter

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
    WorkflowNodeStatus,
    WorkflowStartRequest,
    WorkflowStatusResponse,
)
from .service import validate_dag
from .traceability import find_missing_sources

router = APIRouter(prefix="/api/extensions/workflow", tags=["workflow"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]
WorkflowReader = Annotated[CurrentUser, Depends(require_permission("project:read"))]
WorkflowWriter = Annotated[CurrentUser, Depends(require_permission("project:create"))]
WorkflowAdmin = Annotated[CurrentUser, Depends(require_permission("project:advance"))]
ReviewSubmitter = Annotated[CurrentUser, Depends(require_permission("approval:submit"))]
ReviewActor = Annotated[CurrentUser, Depends(require_permission("approval:review"))]
ReviewViewer = Annotated[CurrentUser, Depends(require_permission("approval:view"))]


# ── Definitions ──


@router.get("/definitions", response_model=WorkflowDefinitionListResponse)
async def list_definitions(
    user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
    is_template: bool | None = Query(None),
    report_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    stmt = select(WorkflowDefinition)
    count_stmt = select(func.count()).select_from(WorkflowDefinition)

    if is_template is not None:
        stmt = stmt.where(WorkflowDefinition.is_template == is_template)
        count_stmt = count_stmt.where(WorkflowDefinition.is_template == is_template)
    if report_type is not None:
        stmt = stmt.where(WorkflowDefinition.report_type == report_type)
        count_stmt = count_stmt.where(WorkflowDefinition.report_type == report_type)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(WorkflowDefinition.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return WorkflowDefinitionListResponse(
        items=[WorkflowDefinitionListItem.model_validate(w) for w in items],
        total=total,
    )


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def get_definition(
    definition_id: UUID,
    _user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
):
    result = await db.get(WorkflowDefinition, definition_id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(result)


@router.post("/definitions", response_model=WorkflowDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_definition(
    body: WorkflowDefinitionCreate,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    definition = WorkflowDefinition(
        name=body.name,
        report_type=body.report_type,
        graph_json=body.graph_json,
        is_template=body.is_template,
        created_by=user.id,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionOut.model_validate(definition)


@router.put("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def update_definition(
    definition_id: UUID,
    body: WorkflowDefinitionUpdate,
    _user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(definition, key, value)

    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionOut.model_validate(definition)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: UUID,
    _user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    definition = await db.get(WorkflowDefinition, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    await db.delete(definition)
    await db.commit()


@router.post("/definitions/validate", response_model=DAGValidationResult)
async def validate_definition(
    body: dict,
    _user: WorkflowReader,
):
    result = validate_dag(body)
    return DAGValidationResult(**result)


# ── Source Traceability ──


@router.get("/projects/{project_id}/chapters/{chapter_id}/sources", response_model=ContentSourceListResponse)
async def get_chapter_sources(
    project_id: UUID,
    chapter_id: UUID,
    user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContentSource)
        .where(ContentSource.chapter_id == chapter_id)
        .order_by(ContentSource.block_index)
    )
    sources = result.scalars().all()
    stats: dict[str, int] = {}
    for s in sources:
        stats[s.source_type] = stats.get(s.source_type, 0) + 1
    return ContentSourceListResponse(
        sources=[ContentSourceOut.model_validate(s) for s in sources],
        stats=stats,
    )


@router.get("/projects/{project_id}/chapters/{chapter_id}/sources/missing")
async def get_missing_sources_endpoint(
    project_id: UUID,
    chapter_id: UUID,
    user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
):
    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter or not chapter.content:
        return {"missing": []}
    return {"missing": find_missing_sources(chapter.content)}


@router.post("/projects/{project_id}/chapters/{chapter_id}/sources/parse")
async def parse_and_store_chapter_sources(
    project_id: UUID,
    chapter_id: UUID,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Parse source markers from chapter content and persist to content_sources table."""
    from .traceability import parse_source_markers
    from .models import ContentSource

    chapter = await db.get(ProjectChapter, chapter_id)
    if not chapter or not chapter.content:
        return {"parsed": 0, "stored": 0}

    parsed = parse_source_markers(chapter.content)

    # Delete existing sources for this chapter
    await db.execute(
        ContentSource.__table__.delete().where(ContentSource.chapter_id == chapter_id)
    )

    for s in parsed:
        source = ContentSource(
            chapter_id=chapter_id,
            block_index=s.block_index,
            source_type=s.source_type,
            source_ref=s.source_ref,
            snippet=s.snippet,
        )
        db.add(source)

    await db.commit()
    return {"parsed": len(parsed), "stored": len(parsed)}


# ── Phase Reviews ──


@router.post("/projects/{project_id}/phase-reviews/assign", response_model=list[PhaseReviewOut], status_code=status.HTTP_201_CREATED)
async def assign_reviews(
    project_id: UUID,
    body: ReviewAssignmentCreate,
    user: ReviewSubmitter,
    db: AsyncSession = Depends(get_db),
):
    """Create review assignments for a phase node. Replaces existing pending assignments."""
    if body.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id mismatch")

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
    user: ReviewActor,
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
        try:
            await send_signal(
                project_id=str(project_id),
                signal_name="review_action",
                args=[review.phase_node, all_approved, body.comment or ""],
            )
        except Exception:
            pass  # Temporal unavailable — still record the action

    return PhaseReviewOut.model_validate(review)


@router.get("/projects/{project_id}/phase-reviews", response_model=ReviewStatusResponse)
async def get_review_status(
    project_id: UUID,
    user: ReviewViewer,
    phase_node: str = Query(..., description="Phase node ID to filter"),
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
    user: ReviewViewer,
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


# ── Workflow Monitoring ──


@router.get("/projects/{project_id}/workflow-status", response_model=WorkflowStatusResponse)
async def get_workflow_status_endpoint(
    project_id: UUID,
    user: WorkflowReader,
    db: AsyncSession = Depends(get_db),
):
    """Get the current workflow execution status for a project."""
    from app.extensions.models import ReportProject

    project = await db.get(ReportProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from .temporal.client import get_workflow_status as _get_wf_status
    temporal_status = await _get_wf_status(str(project_id))

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
    user: WorkflowAdmin,
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
    user: WorkflowAdmin,
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
