"""FastAPI routers for approval workflow."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.extensions.auth.middleware import require_permission
from app.extensions.schemas import CurrentUser

from .schemas import (
    ApprovalActionRequest,
    ApprovalRecordListResponse,
    ApprovalRecordOut,
    ApprovalWorkflowOut,
    SubmitApprovalRequest,
)
from . import service

router = APIRouter(prefix="/api/extensions/approval", tags=["approval"])

CurrentUserWithAccess = Annotated[CurrentUser, Depends(require_permission("system:access"))]


@router.get("/workflows/default", response_model=ApprovalWorkflowOut)
async def get_default_workflow(
    report_type: str = Query(...),
    _user: CurrentUserWithAccess = None,
):
    wf = await service.get_workflow(report_type)
    if not wf:
        raise HTTPException(status_code=404, detail="No workflow found for this report type")
    return wf


@router.post("/submissions", status_code=204)
async def submit_for_approval(
    body: SubmitApprovalRequest,
    _user: CurrentUserWithAccess = None,
):
    await service.submit_for_approval(
        project_id=body.project_id,
        chapter_ids=body.chapter_ids,
        submitted_by=_user.user_id if hasattr(_user, "user_id") else "",
    )


@router.post("/actions", response_model=ApprovalRecordOut)
async def approval_action(
    body: ApprovalActionRequest,
    _user: CurrentUserWithAccess = None,
):
    if body.action not in ("approve", "reject", "comment"):
        raise HTTPException(status_code=400, detail="Invalid action")
    rec = await service.create_action(
        project_id=body.project_id,
        step_id=body.step_id,
        chapter_id=body.chapter_id,
        action=body.action,
        comment=body.comment,
        reviewer_id=_user.user_id if hasattr(_user, "user_id") else "",
        reviewer_name=getattr(_user, "username", ""),
    )
    return rec


@router.get("/records", response_model=ApprovalRecordListResponse)
async def list_records(
    project_id: str = Query(...),
    _user: CurrentUserWithAccess = None,
):
    items = await service.list_records(project_id)
    return ApprovalRecordListResponse(items=items)
