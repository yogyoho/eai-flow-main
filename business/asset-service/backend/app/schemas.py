"""Pydantic Schema 定义"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Asset ──────────────────────────────────────────────────────────────────────

class AssetBase(BaseModel):
    asset_no: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=50)
    model: Optional[str] = Field(None, max_length=200)
    serial_no: Optional[str] = Field(None, max_length=100)
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[Decimal] = None
    depreciation_method: str = "straight_line"
    useful_life_years: int = 5
    residual_value: Decimal = Decimal("0")
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    custodian_id: Optional[str] = Field(None, max_length=100)
    custodian_name: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=300)
    status: str = "normal"
    remark: Optional[str] = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=50)
    model: Optional[str] = Field(None, max_length=200)
    serial_no: Optional[str] = Field(None, max_length=100)
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    depreciation_method: Optional[str] = None
    useful_life_years: Optional[int] = None
    residual_value: Optional[Decimal] = None
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    custodian_id: Optional[str] = Field(None, max_length=100)
    custodian_name: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=300)
    status: Optional[str] = None
    remark: Optional[str] = None


class AssetResponse(AssetBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    current_value: Optional[Decimal]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    assets: list[AssetResponse]
    total: int


# ── Maintenance ────────────────────────────────────────────────────────────────

class MaintenanceRecordBase(BaseModel):
    asset_id: UUID
    maintenance_type: str = Field(..., max_length=30)
    description: Optional[str] = None
    cost: Optional[Decimal] = None
    maintenance_date: Optional[datetime] = None
    next_maintenance_date: Optional[datetime] = None
    vendor: Optional[str] = Field(None, max_length=200)


class MaintenanceRecordCreate(MaintenanceRecordBase):
    pass


class MaintenanceRecordResponse(MaintenanceRecordBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operator_id: Optional[str]
    operator_name: Optional[str]
    created_at: datetime


class MaintenanceListResponse(BaseModel):
    records: list[MaintenanceRecordResponse]
    total: int


# ── Allocation ─────────────────────────────────────────────────────────────────

class AllocationCreate(BaseModel):
    asset_id: UUID
    to_dept_id: Optional[str] = Field(None, max_length=100)
    to_dept_name: Optional[str] = Field(None, max_length=200)
    to_location: Optional[str] = Field(None, max_length=300)
    reason: Optional[str] = None


class AllocationUpdate(BaseModel):
    status: Optional[str] = None
    approved_by: Optional[str] = Field(None, max_length=100)


class AllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID
    from_dept_id: Optional[str]
    from_dept_name: Optional[str]
    to_dept_id: Optional[str]
    to_dept_name: Optional[str]
    from_location: Optional[str]
    to_location: Optional[str]
    allocation_date: Optional[datetime]
    reason: Optional[str]
    status: str
    approved_by: Optional[str]
    operator_id: Optional[str]
    created_at: datetime


class AllocationListResponse(BaseModel):
    records: list[AllocationResponse]
    total: int


# ── Depreciation ────────────────────────────────────────────────────────────────

class DepreciationRecord(BaseModel):
    asset_id: UUID
    asset_name: str
    asset_no: str
    purchase_date: Optional[datetime]
    purchase_price: Optional[Decimal]
    useful_life_years: int
    residual_value: Decimal
    current_value: Optional[Decimal]
    monthly_depreciation: Decimal
    accumulated_depreciation: Decimal
    status: str


class DepreciationResponse(BaseModel):
    records: list[DepreciationRecord]
    total: Decimal
    total_monthly: Decimal


# ── Asset Check ────────────────────────────────────────────────────────────────

class AssetCheckCreate(BaseModel):
    check_name: str = Field(..., max_length=200)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    check_date: Optional[datetime] = None


class AssetCheckUpdate(BaseModel):
    status: Optional[str] = None


class AssetCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    check_no: str
    check_name: str
    dept_id: Optional[str]
    dept_name: Optional[str]
    check_date: Optional[datetime]
    total_count: int
    checked_count: int
    status: str
    operator_id: Optional[str]
    created_at: datetime


class AssetCheckListResponse(BaseModel):
    checks: list[AssetCheckResponse]
    total: int


# ── Scrap ─────────────────────────────────────────────────────────────────────

class ScrapRecordCreate(BaseModel):
    asset_id: UUID
    scrap_reason: Optional[str] = None
    scrap_date: Optional[datetime] = None
    scrap_value: Optional[Decimal] = None


class ScrapRecordUpdate(BaseModel):
    status: Optional[str] = None
    approved_by: Optional[str] = Field(None, max_length=100)


class ScrapRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID
    scrap_no: str
    scrap_reason: Optional[str]
    scrap_date: Optional[datetime]
    scrap_value: Optional[Decimal]
    approved_by: Optional[str]
    status: str
    operator_id: Optional[str]
    created_at: datetime


class ScrapListResponse(BaseModel):
    records: list[ScrapRecordResponse]
    total: int


# ── Dashboard ──────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_assets: int
    total_value: Decimal
    normal_count: int
    maintenance_count: int
    allocated_count: int
    scrapped_count: int
    pending_maintenance: int
    pending_allocations: int
    pending_scraps: int
