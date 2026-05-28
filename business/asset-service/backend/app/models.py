"""SQLAlchemy 模型定义"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Asset(Base):
    """资产台账"""
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    serial_no: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    depreciation_method: Mapped[str] = mapped_column(String(20), default="straight_line")
    useful_life_years: Mapped[int] = mapped_column(default=5)
    residual_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    dept_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dept_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    custodian_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    custodian_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class MaintenanceRecord(Base):
    """维修保养记录"""
    __tablename__ = "maintenance_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    maintenance_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    maintenance_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_maintenance_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Allocation(Base):
    """调拨记录"""
    __tablename__ = "allocations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    from_dept_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    from_dept_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_dept_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_dept_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    from_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    to_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    allocation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AssetCheck(Base):
    """资产盘点"""
    __tablename__ = "asset_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    check_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dept_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dept_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    check_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_count: Mapped[int] = mapped_column(default=0)
    checked_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    operator_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScrapRecord(Base):
    """报废记录"""
    __tablename__ = "scrap_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    scrap_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    scrap_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scrap_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scrap_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    operator_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
