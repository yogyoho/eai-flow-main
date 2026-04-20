"""Pydantic schemas for knowledge factory API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============== Enums ==============


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class StepStatus(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class StructureType(str, Enum):
    NARRATIVE_TEXT = "narrative_text"
    TABLE = "table"
    FORMULA = "formula"
    DIAGRAM = "diagram"
    MIXED = "mixed"


# ============== Domain ==============


class DomainCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    parent_domain: Optional[str] = None
    standard_chapters: Optional[dict] = None


class DomainResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    parent_domain: Optional[str]
    standard_chapters: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainListResponse(BaseModel):
    domains: list[DomainResponse]
    total: int


# ============== Extraction Config ==============


class ExtractionConfig(BaseModel):
    llm_model: str = "qwen-max"
    chunk_strategy: str = "semantic"  # semantic | fixed | section
    merge_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    min_section_length: int = Field(default=100, ge=10)


# ============== Step Status ==============


class StepStatusSchema(BaseModel):
    name: str
    status: StepStatus
    duration: Optional[str] = None
    detail: str = ""


# ============== Content Contract ==============


class ContentContract(BaseModel):
    key_elements: list[str] = Field(default_factory=list)
    structure_type: StructureType = StructureType.NARRATIVE_TEXT
    style_rules: Optional[str] = None
    min_word_count: Optional[int] = None
    forbidden_phrases: list[str] = Field(default_factory=list)


# ============== Cross Section Rule ==============


class CrossSectionRule(BaseModel):
    rule_id: str
    description: str
    source_sections: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    validation_type: str = "data_consistency"
    fields: list[str] = Field(default_factory=list)


# ============== Template Section ==============


class TemplateSection(BaseModel):
    id: str
    title: str
    level: int = 1
    required: bool = True
    purpose: Optional[str] = None
    children: Optional[list["TemplateSection"]] = None
    content_contract: Optional[ContentContract] = None
    compliance_rules: Optional[list[str]] = None
    rag_sources: Optional[list[str]] = None
    generation_hint: Optional[str] = None
    example_snippet: Optional[str] = None
    completeness_score: Optional[int] = None


# ============== Template Result ==============


class TemplateResult(BaseModel):
    template_id: UUID
    name: str
    version: str
    chapters: int
    sections: int
    completeness_score: int
    domain: str


# ============== Template Document (full) ==============


class TemplateDocument(BaseModel):
    template_id: UUID
    name: str
    version: str
    domain: str
    status: TemplateStatus
    completeness_score: int
    root_sections: list[TemplateSection] = Field(default_factory=list)
    cross_section_rules: list[CrossSectionRule] = Field(default_factory=list)
    created_at: str


# ============== Template List Item ==============


class TemplateListItem(BaseModel):
    id: UUID
    domain: str
    name: str
    version: str
    status: TemplateStatus
    completeness_score: int
    source_report_count: int = 0
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    templates: list[TemplateListItem]
    total: int


# ============== Template Version ==============


class TemplateVersionResponse(BaseModel):
    id: UUID
    version: str
    changelog: Optional[str]
    published_by: Optional[str] = None
    published_at: datetime

    model_config = {"from_attributes": True}


# ============== Extraction Task Create ==============


class ExtractionTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(default="default", max_length=100)
    source_report_ids: list[UUID]
    target_template_name: str = Field(..., min_length=1, max_length=200)
    config: Optional[ExtractionConfig] = None


# ============== Extraction Task Response ==============


class ExtractionTaskResponse(BaseModel):
    id: UUID
    name: Optional[str]
    domain: Optional[str]
    source_reports: list[str] = Field(default_factory=list)
    status: TaskStatus
    progress: int
    steps: list[StepStatusSchema] = Field(default_factory=list)
    result: Optional[TemplateResult] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExtractionTaskListResponse(BaseModel):
    tasks: list[ExtractionTaskResponse]
    total: int


# ============== Template Update ==============


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    root_sections_json: Optional[dict] = None
    cross_section_rules: Optional[list[dict]] = None
    completeness_score: Optional[int] = Field(None, ge=0, le=100)


# ============== Compliance Rule ==============


class ComplianceRuleBase(BaseModel):
    """合规规则基础模型"""
    rule_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=50)
    type_name: str = Field(default="")
    severity: str = Field(..., min_length=1, max_length=20)
    severity_name: str = Field(default="")
    enabled: bool = True
    description: Optional[str] = None
    industry: str = Field(..., min_length=1, max_length=50)
    industry_name: str = Field(default="")
    report_types: list[str] = Field(default_factory=list)
    applicable_regions: list[str] = Field(default_factory=list)
    national_level: bool = True
    source_sections: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    validation_config: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    auto_fix_suggestion: Optional[str] = None


class ComplianceRuleCreate(ComplianceRuleBase):
    """创建合规规则"""
    pass


class ComplianceRuleUpdate(BaseModel):
    """更新合规规则"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    type_name: Optional[str] = None
    severity: Optional[str] = Field(None, min_length=1, max_length=20)
    severity_name: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    industry: Optional[str] = Field(None, min_length=1, max_length=50)
    industry_name: Optional[str] = None
    report_types: Optional[list[str]] = None
    applicable_regions: Optional[list[str]] = None
    national_level: Optional[bool] = None
    source_sections: Optional[list[str]] = None
    target_sections: Optional[list[str]] = None
    validation_config: Optional[dict] = None
    error_message: Optional[str] = None
    auto_fix_suggestion: Optional[str] = None


class ComplianceRuleResponse(ComplianceRuleBase):
    """合规规则响应"""
    id: UUID
    seed_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplianceRuleListResponse(BaseModel):
    """合规规则列表响应"""
    rules: list[ComplianceRuleResponse]
    total: int
    page: int = 1
    limit: int = 20


class ComplianceRuleImportResponse(BaseModel):
    """种子数据导入响应"""
    success: bool
    total: int
    created: int
    updated: int
    skipped: int
    errors: int
    error_messages: list[str] = Field(default_factory=list)


class ComplianceRuleStatusResponse(BaseModel):
    """种子数据状态响应"""
    seed_version: str
    seed_total: int
    db_total: int
    db_enabled: int
    db_disabled: int
    in_seed_not_in_db: list[str] = Field(default_factory=list)
    in_db_not_in_seed: list[str] = Field(default_factory=list)
    up_to_date: bool


class ComplianceRuleStatisticsResponse(BaseModel):
    """规则统计响应"""
    total: int
    enabled: int
    disabled: int
    from_seed: int
    type_distribution: dict[str, int] = Field(default_factory=dict)
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    industry_distribution: dict[str, int] = Field(default_factory=dict)


class ComplianceRuleOverviewResponse(BaseModel):
    """规则总览响应"""
    statistics: ComplianceRuleStatisticsResponse
    seed_status: ComplianceRuleStatusResponse
    trigger_statistics: dict[str, Any] = Field(default_factory=dict)


class RuleDictionaryOptionResponse(BaseModel):
    value: str
    label: str


class RuleDictionariesResponse(BaseModel):
    industries: list[RuleDictionaryOptionResponse] = Field(default_factory=list)
    report_types: list[RuleDictionaryOptionResponse] = Field(default_factory=list)
    regions: list[RuleDictionaryOptionResponse] = Field(default_factory=list)


# ============== Compliance Check ==============


class ValidationIssueSchema(BaseModel):
    """验证问题"""
    rule_id: str
    rule_name: str
    severity: str  # critical, warning, info
    check_result: str  # pass, fail, warning, error, skip
    message: str
    field_name: Optional[str] = None
    source_value: Optional[str] = None
    target_value: Optional[str] = None
    location: Optional[list[str]] = None
    suggestion: Optional[str] = None
    details: dict = Field(default_factory=dict)


class ComplianceCheckRequest(BaseModel):
    """合规性检查请求"""
    report_data: Optional[dict] = Field(default_factory=dict, description="报告结构化数据")
    raw_text: Optional[str] = Field(None, description="原始文本内容")
    extracted_fields: Optional[dict] = Field(default_factory=dict, description="提取的字段值")
    report_type: Optional[str] = Field(None, description="报告类型")
    industry: Optional[str] = Field(None, description="行业")
    region: Optional[str] = Field(None, description="地区")
    rule_ids: Optional[list[str]] = Field(None, description="指定要检查的规则ID")
    check_all: bool = Field(True, description="是否检查所有匹配的规则")
    stop_on_first_fail: bool = Field(False, description="遇到第一个失败是否停止")
    thread_id: Optional[UUID] = Field(None, description="会话ID")


class ComplianceCheckResponse(BaseModel):
    """合规性检查响应"""
    success: bool
    total_rules: int
    passed: int
    failed: int
    warnings: int
    errors: int
    skipped: int
    has_critical_issues: bool
    duration_ms: float
    issues: list[ValidationIssueSchema] = Field(default_factory=list)
