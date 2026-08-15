"""Pydantic request/response models for the contract-price-analysis API."""

from datetime import date, datetime
from typing import TypeVar
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
    contract_no: str | None = None
    supplier: str | None = None
    project_name: str | None = None
    project_location: str | None = None
    sign_date: date | None = None
    parse_mode: str
    parse_status: str
    confirm_status: str = "pending"
    parse_meta: dict | None = None
    page_count: int | None = None
    preview_prefix: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime


class ItemOut(ORMBase):
    id: UUID
    document_id: UUID
    goods_name: str
    spec_model: str | None = None
    tech_params: dict | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    price_untaxed: float | None = None
    cluster_id: UUID | None = None
    source_contract_no: str | None = None
    is_outlier: bool = False
    # v2 traceability + validation
    source_page: int | None = None
    source_bbox: list | None = None
    source_table_idx: int | None = None
    source_row_idx: int | None = None
    confidence: float | None = None
    validation_status: str = "ok"
    edit_note: str | None = None
    run_id: UUID | None = None
    created_at: datetime


class ClusterOut(ORMBase):
    id: UUID
    category: str
    representative_name: str
    status: str
    stats: dict | None = None
    item_count: int
    version: int
    confirmed_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ClusterDetail(ClusterOut):
    items: list[ItemOut] = []


class RunOut(ORMBase):
    id: UUID
    trigger_type: str
    label: str | None = None
    status: str
    docs_processed: int
    items_extracted: int
    clusters_formed: int
    duration_ms: int | None = None
    excel_path: str | None = None
    error: str | None = None
    scope: dict | None = None
    progress: dict | None = None
    started_at: datetime
    finished_at: datetime | None = None


class DashboardOut(BaseModel):
    contract_count: int
    item_count: int
    cluster_count: int
    pending_cluster_count: int
    confirmed_cluster_count: int
    outlier_count: int = 0  # count of cpa_items with is_outlier=true (>1.5×IQR within their cluster)
    price_range: dict | None = None
    charts: dict | None = None  # {top_goods, price_ranges, validation, cluster_sizes}
    recent_runs: list[RunOut] = []


class ConfigOut(BaseModel):
    parse_mode: str = "table"
    cluster_eps: float = 0.6
    cluster_min_samples: int = 2
    scheduled_enabled: bool = False
    schedule_cron: str | None = None
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
    unit_price: float | None = None
    tech_params: dict | None = None
    goods_name: str | None = None
    spec_model: str | None = None
    validation_status: str | None = None  # ok | needs_review | corrected
    note: str | None = None


class DocumentUpdate(BaseModel):
    """Manual补 fallback for project-level fields the front-page OCR regex missed,
    plus the doc-level metadata a user may correct by hand."""

    project_name: str | None = None
    project_location: str | None = None
    contract_no: str | None = None
    supplier: str | None = None
    sign_date: date | None = None


class DocumentConfirm(BaseModel):
    """Confirm-gate action: mark a parsed document ready for clustering."""

    confirm_status: str  # confirmed | skipped


class ClusterConfirm(BaseModel):
    confirmed_by: str | None = None
    expected_version: int | None = None


class ClusterMerge(BaseModel):
    cluster_ids: list[UUID]
    representative_name: str
    category: str = "未分类"


class ClusterUpdate(BaseModel):
    """Edit a cluster's display fields (manual curation)."""

    category: str | None = None
    representative_name: str | None = None


class ItemMove(BaseModel):
    target_cluster_id: UUID


class PipelineRunRequest(BaseModel):
    mode: str = "table"
    trigger: str = "manual"


class PipelineRunResponse(BaseModel):
    run_id: UUID
    status: str
    message: str


class BatchDeleteRequest(BaseModel):
    item_ids: list[UUID]


class Page[T](BaseModel):
    items: list[T]
    total: int
    skip: int
    limit: int
