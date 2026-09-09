# EAI-CUSTOM: 投标资料管理 API（bug-3109 v4）——资质 MinIO 版本库 + 样例台账。
# 端点消费 service.py 真库语义（commit 归路由层: 本层完成后调 db.commit()）。
"""Bid materials management API (qualifications version bank + sample ledger).

Mounted into the Gateway under ``/api/extensions/bid-materials``. Endpoints:

  GET    /qualifications                 列表（include_disabled + limit/offset 分页）
  POST   /qualifications                 新建资质（QualificationCreate → 201）
  POST   /qualifications/{id}/versions   上传新版本（multipart; png/jpg 魔数校验 + sha256 去重幂等）
  POST   /qualifications/{id}/rollback   回滚当前版指针（目标版本存在性校验, 幽灵版本 → 404）
  GET    /qualifications/{id}/file       代理下发当前版扫描件（MinIO → bytes → Response）
  GET    /qualifications/expiring        到期预警清单（?days=90 窗口）
  GET    /qualifications/export-whitelist  entities_whitelist 增量 JSON（WP-2.4 组织级权威源）
  GET    /samples                        样例台账列表（industry/project_category/q 过滤 SQL 下推 + 分页）
  POST   /samples/bulk                   幂等导入（file_hash upsert）
  GET    /samples/{id}                   样例详情
  DELETE /samples/{id}                   停用样例（status=disabled 软停, 非物理删除）

鉴权沿用 eia_samples 模式：全部端点 require_permission("system:access")；
错误映射：QualificationNotFoundError/SampleNotFoundError → 404，ValueError（魔数/白名单字段）→ 400。
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser as CurrentUserSchema

from .models import BidSample
from .schemas import (
    QualificationCreate,
    QualificationResponse,
    QualificationVersionResponse,
    SampleBulkImportRequest,
    SampleBulkImportResponse,
    SampleResponse,
)
from .service import QualificationNotFoundError, QualificationService, SampleNotFoundError, SampleService

router = APIRouter(prefix="/api/extensions/bid-materials", tags=["bid-materials"])

CurrentUser = Annotated[CurrentUserSchema, Depends(require_permission("system:access"))]


class RollbackRequest(BaseModel):
    """回滚请求体：目标版本号（必须真实存在的版本行）。"""

    to_version: int


def _media_type(ext: str) -> str:
    return "image/png" if ext == "png" else "image/jpeg"


# ============== Qualification APIs（资质版本库） ==============


@router.get("/qualifications", response_model=list[QualificationResponse])
async def list_qualifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    include_disabled: bool = Query(False, description="是否含已停用（软删）资质"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """列出资质台账（默认过滤软删行, SQL 下推）"""
    rows = await QualificationService(db).list(include_disabled=include_disabled, limit=limit, offset=offset)
    return [QualificationResponse.model_validate(q) for q in rows]


@router.post("/qualifications", response_model=QualificationResponse, status_code=status.HTTP_201_CREATED)
async def create_qualification(
    data: QualificationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """新建资质登记行（版本号 0, 文件本体走 /versions 上传）"""
    q = await QualificationService(db).create(**data.model_dump())
    await db.commit()
    return QualificationResponse.model_validate(q)


@router.post("/qualifications/{qual_id}/versions")
async def upload_qualification_version(
    qual_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    file: UploadFile = File(...),
    note: str | None = Form(None),
):
    """上传新版本扫描件（multipart）：魔数校验（仅 png/jpg）→ sha256 去重（同哈希幂等返回既有版）
    → MinIO put（service 内部 to_thread）→ 建版本行 + 推进 current_version 指针。"""
    data = await file.read()
    try:
        row, created = await QualificationService(db).add_version(qual_id, data=data, note=note, uploaded_by=current_user.id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"created": created, "version": QualificationVersionResponse.model_validate(row)}


@router.post("/qualifications/{qual_id}/rollback", response_model=QualificationResponse)
async def rollback_qualification(
    qual_id: uuid.UUID,
    data: RollbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """回滚当前版到指定版本（改指针不删对象; 目标版本不存在 → 404）"""
    try:
        q = await QualificationService(db).rollback(qual_id, to_version=data.to_version)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return QualificationResponse.model_validate(q)


@router.get("/qualifications/{qual_id}/file")
async def download_qualification_file(
    qual_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """代理下发当前版扫描件（MinIO 读取; 无版本或对象缺失 → 404）"""
    try:
        result = await QualificationService(db).current_file(qual_id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="当前版本文件不存在")
    data, ext = result
    return Response(
        content=data,
        media_type=_media_type(ext),
        headers={"Content-Disposition": f'inline; filename="qualification-{qual_id}.{ext}"'},
    )


@router.get("/qualifications/expiring", response_model=list[QualificationResponse])
async def list_expiring_qualifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    days: int = Query(90, ge=1, le=365, description="到期预警窗口（天）"),
):
    """到期预警清单：valid_until 落在未来 days 天内的未停用资质（按到期日升序）"""
    rows = await QualificationService(db).expiring(days=days)
    return [QualificationResponse.model_validate(q) for q in rows]


@router.get("/qualifications/export-whitelist", response_model=list[dict])
async def export_qualification_whitelist(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """entities_whitelist 增量 JSON（公司+证号+有效期; WP-2.4 组织级权威源）"""
    return await QualificationService(db).export_whitelist()


# ============== Sample APIs（样例台账） ==============


@router.get("/samples", response_model=list[SampleResponse])
async def list_samples(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    industry: str | None = Query(None, max_length=50, description="行业过滤（== 精确）"),
    project_category: str | None = Query(None, max_length=50, description="品类过滤（== 精确）"),
    q: str | None = Query(None, max_length=200, description="标题模糊搜索（ilike）"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """列出样例台账（过滤全部下推 SQL + limit/offset 分页）"""
    rows = await SampleService(db).list(industry=industry, project_category=project_category, q=q, limit=limit, offset=offset)
    return [SampleResponse.model_validate(s) for s in rows]


@router.post("/samples/bulk", response_model=SampleBulkImportResponse, status_code=status.HTTP_201_CREATED)
async def bulk_import_samples(
    payload: SampleBulkImportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """批量导入样例台账——file_hash upsert 幂等可重复执行（updated 恒 0: 幂等语义只分新/跳过）"""
    result = await SampleService(db).bulk([item.model_dump() for item in payload.items])
    await db.commit()
    return SampleBulkImportResponse(created=result["created"], updated=0, total=len(payload.items))


@router.get("/samples/{sample_id}", response_model=SampleResponse)
async def get_sample(
    sample_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """获取单个样例详情"""
    sample = await db.get(BidSample, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="样例不存在")
    return SampleResponse.model_validate(sample)


@router.delete("/samples/{sample_id}")
async def disable_sample(
    sample_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """停用样例（status=disabled 软停, 非物理删除）"""
    try:
        await SampleService(db).disable(sample_id)
    except SampleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"message": "样例已停用"}
