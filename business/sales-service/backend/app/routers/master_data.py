from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Identity, require_sales_permission
from app.database import get_db
from app.domain import add_audit, utc_now
from app.errors import bad_request, not_found
from app.models import (
    Contact,
    Customer,
    CustomerGroup,
    ImportJob,
    Mine,
    PilotProject,
    Product,
    Workface,
)

router = APIRouter(prefix="/master-data", tags=["master-data"])

DATA_TYPES = {
    "customer-groups": CustomerGroup,
    "customers": Customer,
    "mines": Mine,
    "workfaces": Workface,
    "products": Product,
    "contacts": Contact,
    "pilot-projects": PilotProject,
}

HEADER_ALIASES = {
    "name": ["name", "名称", "客户名称", "矿井名称", "工作面名称", "产品名称", "姓名", "示范面名称"],
    "credit_code": ["credit_code", "统一社会信用代码"],
    "region_code": ["region_code", "区域"],
    "is_new_customer": ["is_new_customer", "是否新客户"],
    "parent_id": ["parent_id"],
    "group_id": ["group_id"],
    "group_name": ["group_name", "集团", "客户集团"],
    "customer_id": ["customer_id"],
    "customer_name": ["customer_name", "客户"],
    "mine_id": ["mine_id"],
    "mine_name": ["mine_name", "矿井"],
    "workface_id": ["workface_id"],
    "workface_name": ["workface_name", "工作面"],
    "product_line": ["product_line", "产品线"],
    "model": ["model", "型号"],
    "capacity": ["capacity", "产能"],
    "mining_height_m": ["mining_height_m", "采高"],
    "conditions": ["conditions", "条件"],
    "related_party_status": ["related_party_status", "关联方状态"],
    "address": ["address", "地址"],
    "title": ["title", "职务"],
    "role": ["role", "角色"],
    "influence": ["influence", "影响力"],
    "stance": ["stance", "立场"],
    "phone": ["phone", "电话"],
    "email": ["email", "邮箱"],
    "completed_at": ["completed_at", "完成时间"],
    "effect": ["effect", "效果"],
    "evidence_url": ["evidence_url", "证据链接"],
}


def _canonical(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        clean_key = key.strip()
        target = clean_key
        for canonical, aliases in HEADER_ALIASES.items():
            if clean_key in aliases:
                target = canonical
                break
        out[target] = (value or "").strip()
    return out


def _bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是", "新客户"}


def _date(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


async def _resolve_id(db: AsyncSession, model, row: dict[str, str], id_key: str, name_key: str, name_field: str = "name"):
    raw = row.get(id_key)
    if raw:
        try:
            return uuid.UUID(raw)
        except ValueError:
            raise bad_request(f"{id_key} 无效：{raw}", "SALES-400-IMPORT_ID")
    name = row.get(name_key)
    if name:
        obj = (await db.execute(select(model).where(getattr(model, name_field) == name).limit(1))).scalar_one_or_none()
        if obj:
            return obj.id
        raise bad_request(f"找不到 {name_key}={name}", "SALES-400-IMPORT_REF")
    return None


async def _create_row(db: AsyncSession, data_type: str, row: dict[str, str], identity: Identity):
    now = utc_now()
    if data_type == "customer-groups":
        obj = CustomerGroup(
            name=row.get("name") or "",
            credit_code=row.get("credit_code") or None,
            region_code=row.get("region_code") or None,
            is_new_customer=_bool(row.get("is_new_customer")),
            parent_id=await _resolve_id(db, CustomerGroup, row, "parent_id", "parent_name"),
            source="import",
            data_as_of=now,
        )
    elif data_type == "customers":
        group_id = await _resolve_id(db, CustomerGroup, row, "group_id", "group_name")
        obj = Customer(
            name=row.get("name") or "",
            group_id=group_id,
            credit_code=row.get("credit_code") or None,
            region_code=row.get("region_code") or None,
            address=row.get("address") or None,
            related_party_status=row.get("related_party_status") or "unknown",
            source="import",
            data_as_of=now,
        )
    elif data_type == "mines":
        customer_id = await _resolve_id(db, Customer, row, "customer_id", "customer_name")
        if not customer_id:
            raise bad_request("矿井缺少 customer_id 或客户名称", "SALES-400-IMPORT_REF")
        customer = await db.get(Customer, customer_id)
        obj = Mine(
            customer_id=customer_id,
            group_id=customer.group_id if customer else None,
            name=row.get("name") or "",
            region_code=row.get("region_code") or (customer.region_code if customer else None),
            capacity=row.get("capacity") or None,
            source="import",
            data_as_of=now,
        )
    elif data_type == "workfaces":
        mine_id = await _resolve_id(db, Mine, row, "mine_id", "mine_name")
        if not mine_id:
            raise bad_request("工作面缺少 mine_id 或矿井名称", "SALES-400-IMPORT_REF")
        obj = Workface(
            mine_id=mine_id,
            name=row.get("name") or "",
            mining_height_m=Decimal(row["mining_height_m"]) if row.get("mining_height_m") else None,
            conditions=row.get("conditions") or None,
            source="import",
            data_as_of=now,
        )
    elif data_type == "products":
        obj = Product(
            product_line=row.get("product_line") or "未分类",
            model=row.get("model") or None,
            name=row.get("name") or "",
            source="import",
        )
    elif data_type == "contacts":
        customer_id = await _resolve_id(db, Customer, row, "customer_id", "customer_name")
        if not customer_id:
            raise bad_request("联系人缺少 customer_id 或客户名称", "SALES-400-IMPORT_REF")
        obj = Contact(
            customer_id=customer_id,
            name=row.get("name") or "",
            title=row.get("title") or None,
            role=row.get("role") or None,
            influence=row.get("influence") or None,
            stance=row.get("stance") or None,
            phone=row.get("phone") or None,
            email=row.get("email") or None,
            source="import",
            data_as_of=now,
        )
    elif data_type == "pilot-projects":
        group_id = await _resolve_id(db, CustomerGroup, row, "group_id", "group_name")
        if not group_id:
            raise bad_request("示范面缺少 group_id 或客户集团", "SALES-400-IMPORT_REF")
        workface_id = await _resolve_id(db, Workface, row, "workface_id", "workface_name")
        obj = PilotProject(
            customer_group_id=group_id,
            workface_id=workface_id,
            name=row.get("name") or "",
            completed_at=_date(row.get("completed_at")),
            effect=row.get("effect") or None,
            evidence_url=row.get("evidence_url") or None,
            source="import",
            data_as_of=now,
        )
    else:
        raise bad_request("未知主数据类型", "SALES-400-MASTER_TYPE")
    if not (obj.name or "").strip():
        raise bad_request("名称不能为空", "SALES-400-IMPORT_NAME")
    db.add(obj)
    await db.flush()
    return obj


@router.get("/options")
async def options(
    identity: Identity = Depends(require_sales_permission("sales.masterdata.read")),
    db: AsyncSession = Depends(get_db),
):
    groups = list((await db.execute(select(CustomerGroup).order_by(CustomerGroup.name))).scalars())
    customers = list((await db.execute(select(Customer).order_by(Customer.name))).scalars())
    mines = list((await db.execute(select(Mine).order_by(Mine.name))).scalars())
    workfaces = list((await db.execute(select(Workface).order_by(Workface.name))).scalars())
    products = list((await db.execute(select(Product).where(Product.is_active.is_(True)).order_by(Product.product_line))).scalars())
    contacts = list((await db.execute(select(Contact).order_by(Contact.name))).scalars())
    return {
        "groups": [{"id": str(x.id), "name": x.name, "is_new_customer": x.is_new_customer, "region_code": x.region_code} for x in groups],
        "customers": [{"id": str(x.id), "name": x.name, "group_id": str(x.group_id) if x.group_id else None, "region_code": x.region_code, "related_party_status": x.related_party_status} for x in customers],
        "mines": [{"id": str(x.id), "name": x.name, "customer_id": str(x.customer_id)} for x in mines],
        "workfaces": [{"id": str(x.id), "name": x.name, "mine_id": str(x.mine_id)} for x in workfaces],
        "products": [{"id": str(x.id), "name": x.name, "product_line": x.product_line, "model": x.model} for x in products],
        "contacts": [{"id": str(x.id), "name": x.name, "customer_id": str(x.customer_id), "title": x.title} for x in contacts],
    }


@router.get("/import-jobs")
async def import_jobs(
    identity: Identity = Depends(require_sales_permission("sales.masterdata.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(50))).scalars())
    return {
        "items": [
            {
                "id": str(j.id),
                "type": j.type,
                "file_name": j.file_name,
                "total": j.total,
                "success": j.success,
                "failed": j.failed,
                "status": j.status,
                "errors": j.error_json,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in rows
        ]
    }


@router.get("/{data_type}")
async def list_master_data(
    data_type: str,
    keyword: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    identity: Identity = Depends(require_sales_permission("sales.masterdata.read")),
    db: AsyncSession = Depends(get_db),
):
    model = DATA_TYPES.get(data_type)
    if model is None:
        raise bad_request("未知主数据类型", "SALES-400-MASTER_TYPE")
    conditions = []
    if keyword and hasattr(model, "name"):
        conditions.append(model.name.ilike(f"%{keyword.strip()}%"))
    total = int((await db.execute(select(func.count(model.id)).where(*conditions))).scalar_one())
    rows = list((await db.execute(select(model).where(*conditions).order_by(model.name).offset(skip).limit(limit))).scalars())
    return {"items": [_serialize(model, row) for row in rows], "total": total, "skip": skip, "limit": limit}


def _serialize(model, row) -> dict[str, Any]:
    data: dict[str, Any] = {"id": str(row.id)}
    for column in model.__table__.columns:
        if column.name == "id":
            continue
        value = getattr(row, column.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        data[column.name] = value
    return data


@router.post("/{data_type}", status_code=201)
async def create_master_data(
    data_type: str,
    payload: dict[str, Any],
    identity: Identity = Depends(require_sales_permission("sales.masterdata.import")),
    db: AsyncSession = Depends(get_db),
):
    model = DATA_TYPES.get(data_type)
    if model is None:
        raise bad_request("未知主数据类型", "SALES-400-MASTER_TYPE")
    allowed = {c.name for c in model.__table__.columns if c.name not in {"id", "created_at", "updated_at", "source", "data_as_of"}}
    unknown = set(payload) - allowed
    if unknown:
        raise bad_request(f"不允许的字段：{', '.join(sorted(unknown))}", "SALES-400-MASTER_FIELD")
    data = {k: v for k, v in payload.items() if v is not None}
    data["source"] = "manual"
    if hasattr(model, "data_as_of"):
        data["data_as_of"] = utc_now()
    for key in ("group_id", "customer_id", "mine_id", "workface_id", "parent_id", "customer_group_id"):
        if key in data and isinstance(data[key], str):
            data[key] = uuid.UUID(data[key])
    if "mining_height_m" in data:
        data["mining_height_m"] = Decimal(str(data["mining_height_m"]))
    obj = model(**data)
    db.add(obj)
    await db.flush()
    add_audit(
        db,
        actor_id=identity.user_id,
        action="masterdata.create",
        object_type=data_type,
        object_id=str(obj.id),
        after={"name": getattr(obj, "name", None)},
    )
    return _serialize(model, obj)


@router.patch("/{data_type}/{record_id}")
async def update_master_data(
    data_type: str,
    record_id: uuid.UUID,
    payload: dict[str, Any],
    identity: Identity = Depends(require_sales_permission("sales.masterdata.import")),
    db: AsyncSession = Depends(get_db),
):
    model = DATA_TYPES.get(data_type)
    if model is None:
        raise bad_request("未知主数据类型", "SALES-400-MASTER_TYPE")
    obj = await db.get(model, record_id)
    if obj is None:
        raise not_found("主数据不存在", "SALES-404-MASTER")
    allowed = {c.name for c in model.__table__.columns if c.name not in {"id", "created_at", "updated_at", "source", "data_as_of"}}
    unknown = set(payload) - allowed
    if unknown:
        raise bad_request(f"不允许的字段：{', '.join(sorted(unknown))}", "SALES-400-MASTER_FIELD")
    for key, value in payload.items():
        if key.endswith("_id") and isinstance(value, str) and value:
            value = uuid.UUID(value)
        if key == "mining_height_m" and value is not None:
            value = Decimal(str(value))
        setattr(obj, key, value)
    if hasattr(obj, "data_as_of"):
        obj.data_as_of = utc_now()
    add_audit(
        db,
        actor_id=identity.user_id,
        action="masterdata.update",
        object_type=data_type,
        object_id=str(obj.id),
        after=payload,
    )
    await db.flush()
    return _serialize(model, obj)


@router.post("/import/upload")
async def import_master_data(
    data_type: str = Form(...),
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    identity: Identity = Depends(require_sales_permission("sales.masterdata.import")),
    db: AsyncSession = Depends(get_db),
):
    if data_type not in DATA_TYPES:
        raise bad_request("未知主数据类型", "SALES-400-MASTER_TYPE")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise bad_request("文件不能超过 10MB", "SALES-400-IMPORT_SIZE")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise bad_request("CSV 缺少表头", "SALES-400-IMPORT_HEADER")
    success = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(reader, start=2):
        canonical = _canonical(row)
        if not any(canonical.values()):
            continue
        try:
            savepoint = await db.begin_nested()
            await _create_row(db, data_type, canonical, identity)
            if dry_run:
                await savepoint.rollback()
            else:
                await savepoint.commit()
            success += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"row": index, "error": str(exc)})
    job = ImportJob(
        type=data_type,
        file_name=file.filename,
        total=success + failed,
        success=success,
        failed=failed,
        status="validated" if dry_run else "completed",
        error_json=errors[:200],
        created_by=identity.user_id,
    )
    db.add(job)
    add_audit(
        db,
        actor_id=identity.user_id,
        action="masterdata.import",
        object_type=data_type,
        object_id=str(job.id),
        after={"total": job.total, "success": success, "failed": failed, "dry_run": dry_run},
    )
    await db.flush()
    return {
        "job_id": str(job.id),
        "total": job.total,
        "success": success,
        "failed": failed,
        "errors": errors[:200],
        "dry_run": dry_run,
    }
