from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import Identity, require_opportunity_access, require_sales_permission
from app.config import get_settings
from app.database import get_db
from app.errors import bad_request, forbidden, not_found, unavailable
from app.models import ApprovalRequest, Attachment, Opportunity
from app.storage import build_key, delete_bytes, ensure_bucket, get_bytes, put_bytes

router = APIRouter(prefix="/attachments", tags=["attachments"])
settings = get_settings()

OBJECT_TYPES = {"opportunity", "approval_request", "master_data"}


def _meta(row: Attachment) -> dict:
    return {
        "id": str(row.id),
        "object_type": row.object_type,
        "object_id": str(row.object_id),
        "file_name": row.file_name,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "download_url": f"/sales/api/attachments/{row.id}/download",
    }


async def _ensure_object_access(db: AsyncSession, identity: Identity, object_type: str, object_id: uuid.UUID) -> None:
    if object_type == "opportunity":
        opportunity = await db.get(Opportunity, object_id)
        if opportunity is None:
            raise not_found("商机不存在", "SALES-404-OPPORTUNITY")
        require_opportunity_access(identity, opportunity)
        return
    if object_type == "approval_request":
        request = (await db.execute(select(ApprovalRequest).where(ApprovalRequest.id == object_id).options(selectinload(ApprovalRequest.steps)))).scalar_one_or_none()
        if request is None:
            raise not_found("审批单不存在", "SALES-404-APPROVAL")
        if identity.is_admin or identity.data_scope == "all" or request.requested_by == identity.user_id:
            return
        if any(step.approver_role == identity.sales_role or step.approver_id == identity.user_id for step in request.steps):
            return
        raise forbidden("无权访问该审批附件", "SALES-403-APPROVAL_SCOPE")
    if object_type == "master_data":
        return


@router.get("/health")
async def attachment_health():
    return {"enabled": settings.minio_enabled, "ready": await ensure_bucket(), "bucket": settings.minio_bucket}


@router.get("")
async def list_attachments(
    object_type: str,
    object_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    if object_type not in OBJECT_TYPES:
        raise bad_request("未知附件对象类型", "SALES-400-ATTACHMENT_TYPE")
    await _ensure_object_access(db, identity, object_type, object_id)
    rows = list((await db.execute(select(Attachment).where(Attachment.object_type == object_type, Attachment.object_id == object_id).order_by(Attachment.created_at.desc()))).scalars())
    return {"items": [_meta(row) for row in rows]}


@router.post("", status_code=201)
async def upload_attachment(
    object_type: str = Form(...),
    object_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    if object_type not in OBJECT_TYPES:
        raise bad_request("未知附件对象类型", "SALES-400-ATTACHMENT_TYPE")
    await _ensure_object_access(db, identity, object_type, object_id)
    if object_type == "approval_request" and not identity.has("sales.approval.request") and not identity.has("sales.approval.decide"):
        raise forbidden("缺少审批附件权限", "AUTH-403-PERMISSION_DENIED")
    if object_type == "master_data" and not identity.has("sales.masterdata.import"):
        raise forbidden("缺少主数据附件权限", "AUTH-403-PERMISSION_DENIED")
    if not settings.minio_enabled:
        raise unavailable("对象存储未启用")
    data = await file.read()
    if len(data) > settings.attachment_max_mb * 1024 * 1024:
        raise bad_request(f"附件不能超过 {settings.attachment_max_mb}MB", "SALES-400-ATTACHMENT_SIZE")
    if not await ensure_bucket():
        raise unavailable("对象存储暂不可用")
    key = build_key(object_type, object_id, file.filename or "attachment")
    await put_bytes(key, data, file.content_type)
    row = Attachment(
        object_type=object_type,
        object_id=object_id,
        file_name=file.filename or "attachment",
        content_type=file.content_type,
        size_bytes=len(data),
        bucket=settings.minio_bucket,
        object_key=key,
        uploaded_by=identity.user_id,
    )
    db.add(row)
    await db.flush()
    return _meta(row)


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.read")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Attachment, attachment_id)
    if row is None:
        raise not_found("附件不存在", "SALES-404-ATTACHMENT")
    await _ensure_object_access(db, identity, row.object_type, row.object_id)
    content, content_type = await get_bytes(row.object_key)
    filename = quote(row.file_name)
    return Response(
        content=content,
        media_type=content_type or row.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: uuid.UUID,
    identity: Identity = Depends(require_sales_permission("sales.opportunity.update")),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Attachment, attachment_id)
    if row is None:
        raise not_found("附件不存在", "SALES-404-ATTACHMENT")
    await _ensure_object_access(db, identity, row.object_type, row.object_id)
    await delete_bytes(row.object_key)
    await db.delete(row)
    return {"deleted": True}
