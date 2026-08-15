# EAI-CUSTOM: forked from contract_price/schemas.py; 差异=客户维度(csp_customers + customer_id)
# + 备件域(part_name/spec);csp_run_history 无 excel_path、有 customers_resolved。
"""Pydantic request/response models for the spare-parts-analysis API."""

from datetime import date, datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerOut(ORMBase):
    """客户主数据(D3):canonical_name 规范名 + aliases 别名列表。"""

    id: UUID
    canonical_name: str
    aliases: list = []
    source: str | None = None  # master / imported / ocr
    status: str = "active"  # active | pending | merged
    merged_into: UUID | None = None
    doc_count: int = 0  # 关联文档数(读时聚合,非列)
    created_at: datetime
    updated_at: datetime


class DocumentOut(ORMBase):
    id: UUID
    file_name: str
    storage_uri: str
    file_hash: str
    file_type: str
    contract_no: str | None = None
    supplier: str | None = None
    customer_id: UUID | None = None  # 需方/买方 = 分析维度(D3)
    customer_name: str | None = None  # 冗余,OCR 原文
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
    part_name: str
    spec: str | None = None
    tech_params: dict | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    price_untaxed: float | None = None
    customer_id: UUID | None = None  # 从文档继承(D3 分析维度)
    customer_name: str | None = None  # 冗余
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
    customers_resolved: int = 0  # 归一命中的客户数(D3,④ 特色)
    duration_ms: int | None = None
    error: str | None = None
    scope: dict | None = None
    progress: dict | None = None
    started_at: datetime
    finished_at: datetime | None = None


class DashboardOut(BaseModel):
    contract_count: int
    item_count: int
    cluster_count: int
    customer_count: int = 0  # distinct customer_id(D3)
    pending_cluster_count: int
    confirmed_cluster_count: int
    outlier_count: int = 0  # count of csp_items with is_outlier=true (>1.5×IQR within their cluster)
    price_range: dict | None = None
    charts: dict | None = None  # {top_parts, price_ranges, validation, cluster_sizes, by_customer}
    recent_runs: list[RunOut] = []


class ConfigOut(BaseModel):
    parse_mode: str = "table"
    cluster_eps: float = 0.6
    cluster_min_samples: int = 2
    scheduled_enabled: bool = False
    schedule_cron: str | None = None
    # Table-name keywords that mark a spare-parts/price table even without a clear
    # price header (备件扫描件表头命名各异)。
    price_table_keywords: list[str] = [
        "备件清单",
        "规格型号",
        "报价单",
        "备品备件",
        "单价",
        "数量",
    ]


class ConfigUpdate(ConfigOut):
    pass


class ItemUpdate(BaseModel):
    unit_price: float | None = None
    tech_params: dict | None = None
    part_name: str | None = None
    spec: str | None = None
    validation_status: str | None = None  # ok | needs_review | corrected
    note: str | None = None


class DocumentUpdate(BaseModel):
    """Manual补 fallback for project-level fields the front-page OCR regex missed,
    plus the doc-level metadata a user may correct by hand。"""

    project_name: str | None = None
    project_location: str | None = None
    contract_no: str | None = None
    supplier: str | None = None
    customer_id: UUID | None = None  # 手工修正需方
    customer_name: str | None = None
    sign_date: date | None = None


class DocumentConfirm(BaseModel):
    """Confirm-gate action: mark a parsed document ready for clustering。"""

    confirm_status: str  # confirmed | skipped


class ClusterConfirm(BaseModel):
    confirmed_by: str | None = None
    expected_version: int | None = None


class ClusterMerge(BaseModel):
    cluster_ids: list[UUID]
    representative_name: str
    category: str = "未分类"


class ClusterUpdate(BaseModel):
    """Edit a cluster's display fields (manual curation)。"""

    category: str | None = None
    representative_name: str | None = None


class ItemMove(BaseModel):
    target_cluster_id: UUID


# ── 客户主数据(D3)──


class CustomerCreate(BaseModel):
    canonical_name: str
    aliases: list[str] = []


class CustomerUpdate(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] | None = None


class CustomerClaim(BaseModel):
    """把一个 OCR 脏客户名认领到指定规范客户(并入 aliases)。"""

    raw_name: str


class CustomerMerge(BaseModel):
    """合并 N 个客户到一个规范客户:source 别名并入 target,
    所有 csp_documents/csp_items.customer_id 回填到 target。"""

    source_ids: list[UUID]
    target_id: UUID


class CustomerResolve(BaseModel):
    """批量预览:把若干脏客户名解析到 canonical_id(未命中 → pending 占位)。"""

    raw_names: list[str]


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
