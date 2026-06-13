"""FastAPI routers for workflow definitions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission, require_super_admin
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
    TemplateApprovalAction,
    TemplateApprovalOut,
    WorkflowDefinitionCreate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionOut,
    WorkflowDefinitionUpdate,
    WorkflowNodeStatus,
    WorkflowSignalRequest,
    WorkflowStartRequest,
    WorkflowStatusResponse,
)
from .service import (
    create_definition as _create_definition_svc,
    delete_definition as _delete_definition_svc,
    get_definition as _get_definition_svc,
    list_approvals as _list_approvals_svc,
    list_definitions as _list_definitions_svc,
    review_approval as _review_approval_svc,
    submit_for_approval as _submit_approval_svc,
    update_definition as _update_definition_svc,
    validate_dag,
    withdraw_approval as _withdraw_approval_svc,
)
from .traceability import find_missing_sources

router = APIRouter(prefix="/api/extensions/workflow", tags=["workflow"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]
WorkflowReader = Annotated[CurrentUser, Depends(require_permission("workflow:read"))]
WorkflowWriter = Annotated[CurrentUser, Depends(require_permission("project:create"))]
WorkflowAdmin = Annotated[CurrentUser, Depends(require_permission("project:advance"))]
WorkflowSuperAdmin = Annotated[CurrentUser, Depends(require_super_admin())]
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
    template_status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    items, total = await _list_definitions_svc(db, is_template=is_template, report_type=report_type, template_status=template_status, skip=skip, limit=limit)
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
    definition = await _get_definition_svc(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(definition)


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
        org_bindings=body.org_bindings,
        created_by=user.id,
        description=body.description,
        visible_dept_ids=body.visible_dept_ids,
    )
    return WorkflowDefinitionOut.model_validate(definition)


@router.put("/definitions/{definition_id}", response_model=WorkflowDefinitionOut)
async def update_definition(
    definition_id: UUID,
    body: WorkflowDefinitionUpdate,
    _user: WorkflowSuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    update_data = body.model_dump(exclude_unset=True)
    definition = await _update_definition_svc(db, definition_id, update_data)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(definition)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: UUID,
    _user: WorkflowSuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    deleted = await _delete_definition_svc(db, definition_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow definition not found")


@router.post("/definitions/validate", response_model=DAGValidationResult)
async def validate_definition(
    body: dict,
    _user: WorkflowReader,
):
    result = validate_dag(body)
    return DAGValidationResult(**result)


@router.post("/definitions/{definition_id}/publish-template", response_model=WorkflowDefinitionOut)
async def publish_template(
    definition_id: UUID,
    _user: WorkflowSuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    """Publish a workflow definition as a reusable template."""
    from .service import publish_as_template as _publish_svc

    definition = await _publish_svc(db, definition_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionOut.model_validate(definition)


# ── Template Approval ──


@router.post("/definitions/{definition_id}/submit-approval", response_model=TemplateApprovalOut)
async def submit_template_approval(
    definition_id: UUID,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Submit a template for approval."""
    approval = await _submit_approval_svc(db, definition_id, user.id)
    return TemplateApprovalOut.model_validate(approval)


@router.post("/definitions/{definition_id}/review-approval", response_model=TemplateApprovalOut)
async def review_template_approval(
    definition_id: UUID,
    body: TemplateApprovalAction,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Review (approve/reject) a pending approval request for a template."""
    approvals = await _list_approvals_svc(db, definition_id)
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
    """List all approval records for a template."""
    approvals = await _list_approvals_svc(db, definition_id)
    return [TemplateApprovalOut.model_validate(a) for a in approvals]


@router.post("/definitions/{definition_id}/withdraw-approval")
async def withdraw_template_approval(
    definition_id: UUID,
    user: WorkflowWriter,
    db: AsyncSession = Depends(get_db),
):
    """Withdraw a pending approval request for a template."""
    success = await _withdraw_approval_svc(db, definition_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="No pending approval to withdraw")
    return {"status": "withdrawn"}


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

    # Verify the current user is the assigned reviewer
    if review.reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="You are not the assigned reviewer for this review")

    # Optimistic lock: conditional UPDATE — only succeeds if status is still "pending"
    result = await db.execute(
        sa_update(PhaseReview)
        .where(PhaseReview.id == review_id, PhaseReview.status == "pending")
        .values(status=body.action, comment=body.comment, updated_at=func.now())
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=400, detail="Review already acted on")

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

        # Application-side fallback: update project state even without Temporal
        if not all_approved:
            from .review import apply_rejection_rollback
            await apply_rejection_rollback(db, project_id, review.phase_node)

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


@router.get("/projects/{project_id}/workflow-status")
async def get_workflow_status_endpoint(
    project_id: UUID,
    user: CurrentUserWithAccess,
):
    """Get the current workflow execution status for a project."""
    from app.extensions.database import get_db_context
    from app.extensions.models import ProjectChapter, ReportProject

    async with get_db_context() as db:
        project = await db.get(ReportProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        temporal_status = None
        if project.workflow_id or project.temporal_workflow_id:
            try:
                from .temporal.client import get_workflow_status as _get_wf_status
                temporal_status = await _get_wf_status(str(project_id))
            except Exception:
                pass

        nodes: list[WorkflowNodeStatus] = []
        wf_name: str | None = None
        wf_graph: dict | None = None
        if project.workflow_id:
            definition = await db.get(WorkflowDefinition, project.workflow_id)
            if definition and definition.graph_json:
                graph = definition.graph_json
                wf_name = definition.name
                wf_graph = graph
                current = project.current_phase_node
                project_done = project.status == "completed"

                from .service import topological_sort

                topo_order = topological_sort(graph)
                topo_index = {nid: idx for idx, nid in enumerate(topo_order)}

                phase_node_ids = [n["id"] for n in graph.get("nodes", []) if n.get("type") in ("phase", "subflow")]
                chapter_counts: dict[str, tuple[int, int]] = {}
                if phase_node_ids:
                    ch_count_stmt = (
                        select(
                            ProjectChapter.phase_node,
                            func.count(ProjectChapter.id).label("total"),
                            func.sum(
                                func.cast(ProjectChapter.status.in_(("completed", "approved", "reviewed")), Integer)
                            ).label("done"),
                        )
                        .where(ProjectChapter.project_id == project_id)
                        .where(ProjectChapter.phase_node.in_(phase_node_ids))
                        .group_by(ProjectChapter.phase_node)
                    )
                    ch_result = await db.execute(ch_count_stmt)
                    for phase_node_val, total, done in ch_result.all():
                        chapter_counts[phase_node_val] = (total, done or 0)

                review_node_ids = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "review"]
                review_counts: dict[str, tuple[int, int]] = {}
                if review_node_ids:
                    from app.extensions.workflow.models import PhaseReview

                    rv_count_stmt = (
                        select(
                            PhaseReview.phase_node,
                            func.count(PhaseReview.id).label("total"),
                            func.sum(func.cast(PhaseReview.status == "approved", Integer)).label("approved"),
                        )
                        .where(PhaseReview.project_id == project_id)
                        .where(PhaseReview.phase_node.in_(review_node_ids))
                        .group_by(PhaseReview.phase_node)
                    )
                    rv_result = await db.execute(rv_count_stmt)
                    for phase_node_val, total, approved in rv_result.all():
                        review_counts[phase_node_val] = (total, approved or 0)

                for n in graph.get("nodes", []):
                    nid = n["id"]
                    node_type = n.get("type", "subflow")

                    if project_done:
                        node_status = "completed"
                    elif current is None:
                        node_status = "pending"
                    elif nid == current:
                        node_status = "running"
                    elif topo_index.get(nid, 0) < topo_index.get(current, 0):
                        node_status = "completed"
                    else:
                        node_status = "pending"

                    if temporal_status and temporal_status.get("status") == "running" and nid == current:
                        node_status = "running"

                    kwargs: dict = {}
                    if node_type in ("phase", "subflow") and nid in chapter_counts:
                        total, done = chapter_counts[nid]
                        kwargs["chapter_total"] = total
                        kwargs["chapter_completed"] = done
                    if node_type == "review" and nid in review_counts:
                        total, approved = review_counts[nid]
                        kwargs["review_total"] = total
                        kwargs["review_approved"] = approved

                    nodes.append(WorkflowNodeStatus(
                        node_id=nid,
                        node_type=node_type,
                        label=n.get("data", {}).get("label", nid),
                        status=node_status,
                        **kwargs,
                    ))

        # Fallback: no workflow definition linked, but project has a phase node
        # Build a synthetic node list from current_phase_node so the UI can still
        # display progress and allow manual phase completion.
        if not project.workflow_id and project.current_phase_node:
            current = project.current_phase_node
            project_done = project.status == "completed"

            # Collect chapter counts for the current phase
            chapter_counts: dict[str, tuple[int, int]] = {}
            ch_count_stmt = (
                select(
                    ProjectChapter.phase_node,
                    func.count(ProjectChapter.id).label("total"),
                    func.sum(
                        func.cast(ProjectChapter.status.in_(("completed", "approved", "reviewed")), Integer)
                    ).label("done"),
                )
                .where(ProjectChapter.project_id == project_id)
                .where(ProjectChapter.phase_node == current)
                .group_by(ProjectChapter.phase_node)
            )
            ch_result = await db.execute(ch_count_stmt)
            for phase_node_val, total, done in ch_result.all():
                chapter_counts[phase_node_val] = (total, done or 0)

            node_status = "completed" if project_done else "running"
            kwargs: dict = {}
            if current in chapter_counts:
                total, done = chapter_counts[current]
                kwargs["chapter_total"] = total
                kwargs["chapter_completed"] = done

            nodes.append(WorkflowNodeStatus(
                node_id=current,
                node_type="subflow",
                label=current.replace("-", " ").replace("_", " ").title(),
                status=node_status,
                **kwargs,
            ))

        # Determine overall workflow status
        wf_status = "idle"
        project_done = project.status == "completed"
        if project_done:
            wf_status = "completed"
        elif temporal_status:
            wf_status = temporal_status.get("status", "idle")

        return WorkflowStatusResponse(
            project_id=project_id,
            workflow_id=project.workflow_id,
            temporal_workflow_id=project.temporal_workflow_id,
            current_phase_node=project.current_phase_node,
            status=wf_status,
            nodes=nodes,
            workflow_name=wf_name,
            graph_json=wf_graph,
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

    # Prevent duplicate workflow start
    if project.temporal_workflow_id:
        raise HTTPException(status_code=400, detail="Workflow already started for this project")

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


# ── Workflow Signal ──


async def send_workflow_signal(
    project_id: UUID,
    body: WorkflowSignalRequest,
    db: AsyncSession = None,
) -> dict:
    """Send an arbitrary signal to a running workflow for a project.

    Extracted for testability — the router delegates to this function.
    """
    from app.extensions.models import ReportProject

    if db is None:
        return {"status": "error", "detail": "Database session required"}

    project = await db.get(ReportProject, project_id)
    if not project:
        return {"status": "error", "detail": "Project not found"}

    if not project.temporal_workflow_id:
        return {"status": "error", "detail": "No active workflow"}

    from .temporal.client import send_signal as _send_signal

    try:
        await _send_signal(
            project_id=str(project_id),
            signal_name=body.signal_name,
            args=[body.args],
        )
        return {"status": "signal_sent"}
    except Exception:
        return {"status": "error", "detail": "Signal delivery failed"}


@router.post("/projects/{project_id}/workflow-signal")
async def workflow_signal_endpoint(
    project_id: UUID,
    body: WorkflowSignalRequest,
    user: WorkflowAdmin,
    db: AsyncSession = Depends(get_db),
):
    """Send a signal to a running Temporal workflow."""
    result = await send_workflow_signal(project_id, body, db)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "Unknown error"))
    return result
