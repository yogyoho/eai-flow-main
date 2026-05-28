"""仪表盘路由"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Project, Risk, Task
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    total_projects_result = await db.execute(select(func.count(Project.id)))
    total_projects = total_projects_result.scalar() or 0

    draft_result = await db.execute(select(func.count(Project.id)).where(Project.status == "draft"))
    draft_count = draft_result.scalar() or 0

    ongoing_result = await db.execute(select(func.count(Project.id)).where(Project.status == "ongoing"))
    ongoing_count = ongoing_result.scalar() or 0

    completed_result = await db.execute(select(func.count(Project.id)).where(Project.status == "completed"))
    completed_count = completed_result.scalar() or 0

    suspended_result = await db.execute(select(func.count(Project.id)).where(Project.status == "suspended"))
    suspended_count = suspended_result.scalar() or 0

    budget_result = await db.execute(select(func.coalesce(func.sum(Project.budget), 0)))
    total_budget = budget_result.scalar() or Decimal("0")

    total_tasks_result = await db.execute(select(func.count(Task.id)))
    total_tasks = total_tasks_result.scalar() or 0

    pending_tasks_result = await db.execute(
        select(func.count(Task.id)).where(Task.status.in_(["todo", "in_progress"]))
    )
    pending_tasks = pending_tasks_result.scalar() or 0

    overdue_tasks_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.due_date < func.now(),
            Task.status.in_(["todo", "in_progress"])
        )
    )
    overdue_tasks = overdue_tasks_result.scalar() or 0

    high_risks_result = await db.execute(
        select(func.count(Risk.id)).where(Risk.severity == "high", Risk.status == "identified")
    )
    high_risks = high_risks_result.scalar() or 0

    return DashboardStats(
        total_projects=total_projects,
        draft_count=draft_count,
        ongoing_count=ongoing_count,
        completed_count=completed_count,
        suspended_count=suspended_count,
        total_budget=total_budget,
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        overdue_tasks=overdue_tasks,
        high_risks=high_risks,
    )
