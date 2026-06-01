"""Timeline API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

from ..models import ProjectTimeline
from .schemas import (
    TimelineEntryCreate,
    TimelineEntryOut,
    TimelineEntryUpdate,
    TimelineListResponse,
)
from .service import delete_timeline_entry, get_timeline, upsert_timeline_entry

router = APIRouter(prefix="/api/extensions/workflow", tags=["timeline"])

TimelineUser = Annotated[CurrentUser, Depends(require_permission("project:read"))]
TimelineEditor = Annotated[CurrentUser, Depends(require_permission("project:edit"))]


@router.get("/projects/{project_id}/timeline", response_model=TimelineListResponse)
async def list_timeline(
    project_id: UUID,
    _user: TimelineUser,
    db: AsyncSession = Depends(get_db),
):
    entries = await get_timeline(db, project_id)
    return TimelineListResponse(entries=[TimelineEntryOut.model_validate(e) for e in entries])


@router.put("/projects/{project_id}/timeline", response_model=TimelineEntryOut)
async def upsert_timeline(
    project_id: UUID,
    body: TimelineEntryCreate,
    _user: TimelineEditor,
    db: AsyncSession = Depends(get_db),
):
    entry = await upsert_timeline_entry(
        db, project_id, body.phase_node, body.model_dump(exclude={"phase_node"}, exclude_unset=True)
    )
    return TimelineEntryOut.model_validate(entry)


@router.patch("/projects/{project_id}/timeline/{entry_id}", response_model=TimelineEntryOut)
async def update_timeline_entry(
    project_id: UUID,
    entry_id: UUID,
    body: TimelineEntryUpdate,
    _user: TimelineEditor,
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    entry = await db.get(ProjectTimeline, entry_id)
    if not entry or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="Timeline entry not found")
    for key, value in data.items():
        setattr(entry, key, value)
    await db.commit()
    await db.refresh(entry)
    return TimelineEntryOut.model_validate(entry)


@router.delete("/projects/{project_id}/timeline/{entry_id}", status_code=204)
async def delete_timeline(
    project_id: UUID,
    entry_id: UUID,
    _user: TimelineEditor,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_timeline_entry(db, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Timeline entry not found")
