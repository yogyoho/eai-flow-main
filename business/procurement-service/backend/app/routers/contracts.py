"""合同管理 API 路由"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenPayload, get_current_user
from app.database import get_db
from app.models import Contract, TenderProject
from app.schemas import (
    ContractCreate,
    ContractListResponse,
    ContractResponse,
    ContractUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contracts", tags=["合同管理"])


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """查询合同列表"""
    stmt = select(Contract)
    if keyword:
        stmt = stmt.where(Contract.title.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(Contract.status == status)
    if project_id:
        stmt = stmt.where(Contract.project_id == project_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.order_by(Contract.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    contracts = list(result.scalars().all())

    return ContractListResponse(
        contracts=[ContractResponse.model_validate(c) for c in contracts],
        total=total,
    )


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """创建合同"""
    contract = Contract(**data.model_dump())
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return ContractResponse.model_validate(contract)


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """获取合同详情"""
    stmt = select(Contract).where(Contract.id == contract_id)
    result = await db.execute(stmt)
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    return ContractResponse.model_validate(contract)


@router.put("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: UUID,
    data: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """更新合同"""
    stmt = select(Contract).where(Contract.id == contract_id)
    result = await db.execute(stmt)
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contract, field, value)
    await db.commit()
    await db.refresh(contract)
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/risk-check")
async def check_contract_risk(
    contract_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: TokenPayload = Depends(get_current_user),
):
    """合同风险检测"""
    stmt = select(Contract).where(Contract.id == contract_id)
    result = await db.execute(stmt)
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")

    warnings: list[str] = []
    issues: list[str] = []
    risk_level = "low"

    if contract.total_price is None:
        issues.append("合同金额未填写")
        risk_level = "medium"

    if contract.sign_date is None:
        warnings.append("合同未填写签订日期")

    if contract.end_date and contract.start_date:
        if contract.end_date < contract.start_date:
            issues.append("合同结束日期早于开始日期")
            risk_level = "high"

    if contract.payment_terms is None:
        warnings.append("合同未填写付款条款")

    if len(issues) > 0:
        risk_level = "high"
    elif len(warnings) > 0:
        risk_level = "medium"

    contract.risk_level = risk_level
    contract.risk_issues = issues if issues else None
    await db.commit()

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "risk_level": risk_level,
    }
