# EAI-CUSTOM: 投标资料管理 API（bug-3109 v4）——资质 MinIO 版本库 + 样例台账。
# 端点消费 service.py 真库语义（commit 归路由层: 本层完成后调 db.commit()）。
"""Bid materials management API (qualifications version bank + sample ledger).

Mounted into the Gateway under ``/api/extensions/bid-materials``. Endpoints:

  GET    /qualifications                 列表（include_disabled/qual_type 过滤 + limit/offset 分页）
  POST   /qualifications                 新建资质（QualificationCreate → 201）
  GET    /qualifications/{id}            详情（不存在/停用 → 404）
  PATCH  /qualifications/{id}            更新元数据（QualificationUpdate → service 白名单; disabled 不开放走 DELETE）
  DELETE /qualifications/{id}            软删（disabled=true; MinIO 对象保留）
  POST   /qualifications/{id}/versions   上传新版本（multipart; png/jpg 魔数校验 + sha256 去重幂等 → 201）
  GET    /qualifications/{id}/versions   版本历史（升序——rollback 前置核对目标版本存在）
  POST   /qualifications/{id}/rollback   回滚当前版指针（目标版本存在性校验, 幽灵版本 → 404）
  GET    /qualifications/{id}/file       代理下发扫描件（?version=n 按版本; 缺省当前版——spec §2.3）
  GET    /qualifications/expiring        到期预警清单（?days=90 窗口）
  GET    /qualifications/export-whitelist  entities_whitelist 增量 JSON（WP-2.4 组织级权威源）
  GET    /samples                        样例台账列表（industry/project_category/q 过滤 SQL 下推 + 分页）
  POST   /samples/bulk                   幂等导入（file_hash upsert）
  GET    /samples/{id}                   样例详情
  DELETE /samples/{id}                   停用样例（status=disabled 软停, 非物理删除）

鉴权沿用 eia_samples 模式：全部端点 require_permission("system:access")；
错误映射：QualificationNotFoundError/SampleNotFoundError → 404，ValueError（魔数校验）→ 400。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser as CurrentUserSchema

from .schemas import (
    QualificationCreate,
    QualificationResponse,
    QualificationUpdate,
    QualificationVersionResponse,
    QualificationVersionUploadResponse,
    SampleBulkImportRequest,
    SampleBulkImportResponse,
    SampleResponse,
    WhitelistEntry,
)
from .service import QualificationNotFoundError, QualificationService, SampleNotFoundError, SampleService

router = APIRouter(prefix="/api/extensions/bid-materials", tags=["bid-materials"])

# 命名收口：require_permission 工厂每次调用产新闭包，匿名形态（Depends(require_permission(...))）
# 无法被测试 dependency_overrides 按对象同一性覆盖——命名后路由层测试可覆盖同一函数对象。
_require_system_access = require_permission("system:access")
CurrentUser = Annotated[CurrentUserSchema, Depends(_require_system_access)]


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
    qual_type: str | None = Query(None, max_length=50, description="资质类型过滤（== 精确, SQL 下推）"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """列出资质台账（默认过滤软删行, 过滤 SQL 下推）"""
    rows = await QualificationService(db).list(include_disabled=include_disabled, qual_type=qual_type, limit=limit, offset=offset)
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


@router.post("/qualifications/{qual_id}/versions", response_model=QualificationVersionUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_qualification_version(
    qual_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
    file: UploadFile = File(...),
    note: str | None = Form(None, max_length=200),
):
    """上传新版本扫描件（multipart）：魔数校验（仅 png/jpg）→ sha256 去重（同哈希幂等返回既有版）
    → MinIO put（service 内部 to_thread）→ 建版本行 + 推进 current_version 指针。"""
    if (file.size or 0) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="扫描件过大")
    data = await file.read()
    # 二次守卫（终审 M-2）：chunked 传输无 Content-Length 时 file.size=None，首道检查旁路——读后兜底
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="扫描件过大")
    try:
        row, created = await QualificationService(db).add_version(qual_id, data=data, note=note, uploaded_by=current_user.id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return QualificationVersionUploadResponse(created=created, version=row.version, sha256=row.sha256)


@router.post("/qualifications/{qual_id}/rollback", response_model=QualificationResponse)
async def rollback_qualification(
    qual_id: UUID,
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
    qual_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
    version: int | None = Query(None, description="指定历史版本号（spec §2.3）; 缺省=当前版语义不变"),
):
    """代理下发资质扫描件（MinIO 读取; 版本行/对象缺失 → 404）。
    spec §2.3 ?version=n: 按版本行 (qualification_id, version) 查对象下发——幽灵版本号
    （0/负数/超界, 不设 ge 约束）→ 404「指定版本不存在: v{n}」（与 rollback 同语义,
    靠存在性校验而非 422）; 缺省走 current_file 保持原语义。"""
    try:
        if version is None:
            result = await QualificationService(db).current_file(qual_id)
        else:
            result = await QualificationService(db).version_file(qual_id, version)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if result is None:
        # 版本行缺失已在 service raise（「指定版本不存在」）; 走到这里的 None 只剩对象缺失(NoSuchKey)
        raise HTTPException(status_code=404, detail="当前版本文件不存在" if version is None else f"版本文件不存在: v{version}")
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


@router.get("/qualifications/export-whitelist", response_model=list[WhitelistEntry])
async def export_qualification_whitelist(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """entities_whitelist 增量 JSON（公司+证号+有效期; WP-2.4 组织级权威源）"""
    return await QualificationService(db).export_whitelist()


# ---- 单段 {qual_id} 路由必须声明在 /expiring 与 /export-whitelist 之后 ----
# FastAPI 按声明顺序匹配：{qual_id} 若在前会把 "expiring"/"export-whitelist" 吞成路径参数（422）。


@router.get("/qualifications/{qual_id}", response_model=QualificationResponse)
async def get_qualification(
    qual_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """资质详情（service.get 语义：不存在/已停用 → 404）"""
    try:
        q = await QualificationService(db).get(qual_id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return QualificationResponse.model_validate(q)


@router.patch("/qualifications/{qual_id}", response_model=QualificationResponse)
async def update_qualification(
    qual_id: UUID,
    data: QualificationUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """更新元数据（QualificationUpdate → service 白名单校验：未知键/disabled → 400, 不存在/停用 → 404）"""
    try:
        q = await QualificationService(db).update(qual_id, **data.model_dump(exclude_unset=True))
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return QualificationResponse.model_validate(q)


@router.delete("/qualifications/{qual_id}")
async def disable_qualification(
    qual_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """软删资质（disabled=true; MinIO 对象保留——误删=灾难, 非物理删除）"""
    try:
        await QualificationService(db).soft_delete(qual_id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"disabled": True}


@router.get("/qualifications/{qual_id}/versions", response_model=list[QualificationVersionResponse])
async def list_qualification_versions(
    qual_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """版本历史（version 升序）——rollback 前先读此表确认目标版本存在（解 to_version 不可发现问题）"""
    try:
        rows = await QualificationService(db).versions(qual_id)
    except QualificationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [QualificationVersionResponse.model_validate(v) for v in rows]


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
    sample_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: CurrentUser,
):
    """获取单个样例详情"""
    try:
        sample = await SampleService(db).get(sample_id)
    except SampleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return SampleResponse.model_validate(sample)


@router.delete("/samples/{sample_id}")
async def disable_sample(
    sample_id: UUID,
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
