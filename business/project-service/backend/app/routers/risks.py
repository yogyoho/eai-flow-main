"""项目风险路由"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Project, Risk
from app.schemas import (
    RiskCreate,
    RiskListResponse,
    RiskResponse,
    RiskUpdate,
)

router = APIRouter(prefix="/risks", tags=["风险管理"])


@router.get("", response_model=RiskListResponse)
async def list_risks(
    project_id: UUID | None = Query(None),
    status: str | None = Query(None),
    risk_type: str | None = Query(None),
    severity: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    stmt = select(Risk)
    count_stmt = select(func.count(Risk.id))

    if project_id:
        stmt = stmt.where(Risk.project_id == project_id)
        count_stmt = count_stmt.where(Risk.project_id == project_id)
    if status:
        stmt = stmt.where(Risk.status == status)
        count_stmt = count_stmt.where(Risk.status == status)
    if risk_type:
        stmt = stmt.where(Risk.risk_type == risk_type)
        count_stmt = count_stmt.where(Risk.risk_type == risk_type)
    if severity:
        stmt = stmt.where(Risk.severity == severity)
        count_stmt = count_stmt.where(Risk.severity == severity)

    result = await db.execute(stmt.offset(skip).limit(limit).order_by(Risk.created_at.desc()))
    risks = result.scalars().all()

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    return RiskListResponse(risks=[RiskResponse.model_validate(r) for r in risks], total=total)


@router.post("", response_model=RiskResponse, status_code=status.HTTP_201_CREATED)
async def create_risk(
    data: RiskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
):
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    risk = Risk(**data.model_dump(), identified_by=current_user.username)
    db.add(risk)
    await db.flush()
    await db.refresh(risk)
    return RiskResponse.model_validate(risk)


@router.put("/{risk_id}", response_model=RiskResponse)
async def update_risk(
    risk_id: UUID,
    data: RiskUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: TokenPayload = Depends(get_current_user),
):
    result = await db.execute(select(Risk).where(Risk.id == risk_id))
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(risk, key, value)

    if data.status == "resolved":
        from datetime import datetime, timezone
        risk.resolved_date = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(risk)
    return RiskResponse.model_validate(risk)
