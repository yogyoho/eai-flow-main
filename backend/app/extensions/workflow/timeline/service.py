"""Timeline CRUD service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProjectTimeline


async def get_timeline(db: AsyncSession, project_id: UUID) -> list[ProjectTimeline]:
    """Get all timeline entries for a project, ordered by planned_start."""
    stmt = (
        select(ProjectTimeline)
        .where(ProjectTimeline.project_id == project_id)
        .order_by(ProjectTimeline.planned_start)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def upsert_timeline_entry(
    db: AsyncSession, project_id: UUID, phase_node: str, data: dict
) -> ProjectTimeline:
    """Create or update a timeline entry for a phase node."""
    stmt = select(ProjectTimeline).where(
        ProjectTimeline.project_id == project_id,
        ProjectTimeline.phase_node == phase_node,
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()

    if entry:
        for key, value in data.items():
            setattr(entry, key, value)
    else:
        entry = ProjectTimeline(project_id=project_id, phase_node=phase_node, **data)
        db.add(entry)

    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_timeline_entry(db: AsyncSession, entry_id: UUID) -> bool:
    """Delete a timeline entry by ID. Returns True if found and deleted."""
    entry = await db.get(ProjectTimeline, entry_id)
    if not entry:
        return False
    await db.delete(entry)
    await db.commit()
    return True
