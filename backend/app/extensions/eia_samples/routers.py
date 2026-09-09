# EAI-CUSTOM: 煤矿环评报告样例库 API——自 knowledge_factory/routers.py 样例段原样迁出
# （2026-09 独立应用化：KF 是通用模块，领域样例库不得混入；端点行为不变，仅换路由前缀归属）。
"""Coal EIA report sample bank management API.

Mounted into the Gateway under ``/api/extensions/eia-samples``. Endpoints:

  GET    /samples                  分页列出样例台账（scenario×status 双轴过滤 + 模糊搜索）
  POST   /samples                  手工登记样例（file_hash 重复 → 409）
  POST   /samples/import-bulk      批量导入（按 file_hash upsert 幂等）
  POST   /samples/batch-update     批量修改 scenario/status/variant/confidence
  GET    /samples/{sample_id}      获取单个样例
  PATCH  /samples/{sample_id}      更新单个样例
  DELETE /samples/{sample_id}      删除样例登记

鉴权沿用原样例段模式：require_permission("system:access")；应用级页面可见性由
前端 config/permissions.yaml 页面键（ces:page:samples）+ 角色授权控制。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser as CurrentUserSchema

from .schemas import (
    SampleBatchUpdate,
    SampleBulkImportRequest,
    SampleBulkImportResponse,
    SampleCreate,
    SampleListResponse,
    SampleResponse,
    SampleScenario,
    SampleStatus,
    SampleUpdate,
)
from .service import SampleHashConflictError, SampleService

router = APIRouter(prefix="/api/extensions/eia-samples", tags=["Coal EIA Samples"])

CurrentUser = Annotated[CurrentUserSchema, Depends(require_permission("system:access"))]


# ============== Sample APIs（样例库，EAI-CUSTOM: coal-eia-report v2 BS3 MVP） ==============


@router.get("/samples", response_model=SampleListResponse)
async def list_samples(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    scenario: SampleScenario | None = Query(None, description="场景过滤"),
    status: SampleStatus | None = Query(None, description="解析状态过滤"),
    search: str | None = Query(None, max_length=200, description="标题/来源路径模糊搜索"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
):
    """分页列出样例台账（scenario×status 双轴过滤）"""
    samples, total = await SampleService.list_samples(db, scenario=scenario, status=status, search=search, page=page, limit=limit)
    return SampleListResponse(samples=[SampleResponse.model_validate(s) for s in samples], total=total)


@router.post("/samples", response_model=SampleResponse, status_code=status.HTTP_201_CREATED)
async def create_sample(
    data: SampleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """手工登记样例（入库向导提交；file_hash 重复返回 409）"""
    try:
        return await SampleService.create_sample(db, data, user_id=current_user.id)
    except SampleHashConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/samples/import-bulk", response_model=SampleBulkImportResponse)
async def import_bulk_samples(
    payload: SampleBulkImportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """批量导入样例台账——按 file_hash upsert，幂等可重复执行（既有台账数据入库通道）"""
    result = await SampleService.bulk_import(db, payload)
    return SampleBulkImportResponse(**result)


@router.post("/samples/batch-update")
async def batch_update_samples(
    data: SampleBatchUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """批量修改 scenario/status/variant/confidence（台账归类）"""
    updated = await SampleService.batch_update(db, data)
    return {"updated": updated}


@router.get("/samples/{sample_id}", response_model=SampleResponse)
async def get_sample(
    sample_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """获取单个样例"""
    sample = await SampleService.get_sample(db, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="样例不存在")
    return sample


@router.patch("/samples/{sample_id}", response_model=SampleResponse)
async def update_sample(
    sample_id: UUID,
    data: SampleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """更新单个样例（场景/状态/置信标注等）"""
    sample = await SampleService.get_sample(db, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="样例不存在")
    return await SampleService.update_sample(db, sample, data)


@router.delete("/samples/{sample_id}")
async def delete_sample(
    sample_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """删除样例登记"""
    sample = await SampleService.get_sample(db, sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="样例不存在")
    await SampleService.delete_sample(db, sample)
    return {"message": "样例已删除"}
