"""Pydantic request/response models for the contract-price-analysis API."""

from datetime import date, datetime
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentOut(ORMBase):
    id: UUID
    file_name: str
    storage_uri: str
    file_hash: str
    file_type: str
    contract_no: Optional[str] = None
    supplier: Optional[str] = None
    project_name: Optional[str] = None
    project_location: Optional[str] = None
    sign_date: Optional[date] = None
    parse_mode: str
    parse_status: str
    parse_meta: Optional[dict] = None
    page_count: Optional[int] = None
    preview_prefix: Optional[str] = None
    parsed_at: Optional[datetime] = None
    created_at: datetime


class ItemOut(ORMBase):
    id: UUID
    document_id: UUID
    goods_name: str
    spec_model: Optional[str] = None
    tech_params: Optional[dict] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    price_untaxed: Optional[float] = None
    cluster_id: Optional[UUID] = None
    source_contract_no: Optional[str] = None
    is_outlier: bool = False
    # v2 traceability + validation
    source_page: Optional[int] = None
    source_bbox: Optional[list] = None
    source_table_idx: Optional[int] = None
    source_row_idx: Optional[int] = None
    confidence: Optional[float] = None
    validation_status: str = "ok"
    edit_note: Optional[str] = None
    created_at: datetime


class ClusterOut(ORMBase):
    id: UUID
    category: str
    representative_name: str
    status: str
    stats: Optional[dict] = None
    item_count: int
    version: int
    confirmed_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClusterDetail(ClusterOut):
    items: list[ItemOut] = []


class RunOut(ORMBase):
    id: UUID
    trigger_type: str
    status: str
    docs_processed: int
    items_extracted: int
    clusters_formed: int
    duration_ms: Optional[int] = None
    excel_path: Optional[str] = None
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class DashboardOut(BaseModel):
    contract_count: int
    item_count: int
    cluster_count: int
    pending_cluster_count: int
    confirmed_cluster_count: int
    price_range: Optional[dict] = None
    recent_runs: list[RunOut] = []


class ConfigOut(BaseModel):
    parse_mode: str = "table"
    cluster_eps: float = 0.6
    cluster_min_samples: int = 2
    scheduled_enabled: bool = False
    schedule_cron: Optional[str] = None
    # Table-name keywords that mark a goods/price table even without a clear
    # price header (different contracts name price tables differently).
    price_table_keywords: list[str] = [
        "工程量清单",
        "分部分项",
        "单价措施",
        "设备清单",
        "报价",
        "暂列",
    ]


class ConfigUpdate(ConfigOut):
    pass


class ItemUpdate(BaseModel):
    unit_price: Optional[float] = None
    tech_params: Optional[dict] = None
    goods_name: Optional[str] = None
    spec_model: Optional[str] = None
    note: Optional[str] = None


class DocumentUpdate(BaseModel):
    """Manual补 fallback for project-level fields the front-page OCR regex missed,
    plus the doc-level metadata a user may correct by hand."""

    project_name: Optional[str] = None
    project_location: Optional[str] = None
    contract_no: Optional[str] = None
    supplier: Optional[str] = None
    sign_date: Optional[date] = None


class ClusterConfirm(BaseModel):
    confirmed_by: Optional[str] = None
    expected_version: Optional[int] = None


class ClusterMerge(BaseModel):
    cluster_ids: list[UUID]
    representative_name: str
    category: str = "未分类"


class ItemMove(BaseModel):
    target_cluster_id: UUID


class PipelineRunRequest(BaseModel):
    mode: str = "table"
    trigger: str = "manual"


class PipelineRunResponse(BaseModel):
    run_id: UUID
    status: str
    message: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int
