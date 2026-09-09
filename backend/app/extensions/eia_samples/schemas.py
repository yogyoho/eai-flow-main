"""Pydantic schemas for the coal EIA report sample bank (EAI-CUSTOM)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# ============== Samples（样例库，EAI-CUSTOM: coal-eia-report v2 BS3 MVP） ==============


class SampleScenario(StrEnum):
    """样例场景——对齐 coal-eia v2 回填对账定稿的场景矩阵（D1）"""

    PLANNING_EIA = "planning_eia"  # 矿区总体规划环评（深标杆）
    PROJECT_EIA_UNDERGROUND = "project_eia_underground"  # 项目环评·井工
    PROJECT_EIA_OPENPIT = "project_eia_openpit"  # 项目环评·露天
    POST_EIA = "post_eia"  # 环境影响后评价
    TRACKING_EIA = "tracking_eia"  # 规划环评跟踪评价
    RECLAMATION_PLAN = "reclamation_plan"  # 矿山地质环境保护与土地复垦方案
    OTHER = "other"


class SampleStatus(StrEnum):
    """样例解析状态"""

    PARSED = "parsed"  # 已解析出结构（digest/章节树）
    CONVERTED = "converted"  # .doc 已转换为可解析文本
    FILENAME_ONLY = "filename_only"  # 仅登记文件名，未解析
    ENCRYPTED = "encrypted"  # 加密/DRM 容器，不可读（magic-byte 预检命中）
    CONVERTED_FAILED = "converted_failed"  # 转换失败


class SampleCreate(BaseModel):
    """手工登记样例"""

    title: str = Field(..., min_length=1, max_length=500)
    source_path: str = Field(..., min_length=1, max_length=1000)
    file_hash: str = Field(..., min_length=8, max_length=64)
    scenario: SampleScenario = SampleScenario.OTHER
    variant: str | None = Field(None, max_length=200)
    status: SampleStatus = SampleStatus.FILENAME_ONLY
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    notes: str | None = None


class SampleBulkItem(BaseModel):
    """批量导入条目（台账数据入库 / import-bulk upsert）"""

    title: str = Field(..., min_length=1, max_length=500)
    source_path: str = Field(..., min_length=1, max_length=1000)
    file_hash: str = Field(..., min_length=8, max_length=64)
    scenario: SampleScenario = SampleScenario.OTHER
    variant: str | None = Field(None, max_length=200)
    status: SampleStatus = SampleStatus.FILENAME_ONLY
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    notes: str | None = None


class SampleBulkImportRequest(BaseModel):
    """批量导入请求——按 file_hash upsert 幂等"""

    items: list[SampleBulkItem] = Field(..., min_length=1, max_length=500)


class SampleBulkImportResponse(BaseModel):
    created: int
    updated: int
    total: int


class SampleUpdate(BaseModel):
    """单条更新（PATCH，全字段可选）"""

    title: str | None = Field(None, min_length=1, max_length=500)
    source_path: str | None = Field(None, min_length=1, max_length=1000)
    scenario: SampleScenario | None = None
    variant: str | None = Field(None, max_length=200)
    status: SampleStatus | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    notes: str | None = None


class SampleBatchUpdate(BaseModel):
    """批量修改 scenario/status（台账批量归类）"""

    ids: list[UUID] = Field(..., min_length=1, max_length=500)
    scenario: SampleScenario | None = None
    status: SampleStatus | None = None
    variant: str | None = Field(None, max_length=200)
    confidence: float | None = Field(None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "SampleBatchUpdate":
        if all(v is None for v in (self.scenario, self.status, self.variant, self.confidence)):
            raise ValueError("至少需要提供一个待更新字段（scenario/status/variant/confidence）")
        return self


class SampleResponse(BaseModel):
    id: UUID
    title: str
    source_path: str
    file_hash: str
    scenario: str
    variant: str | None
    status: str
    confidence: float | None
    notes: str | None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SampleListResponse(BaseModel):
    samples: list[SampleResponse]
    total: int


# ============== Quality（质检面板，EAI-CUSTOM: coal-eia v2 BS3 二期④） ==============


class QualityCheckOut(BaseModel):
    """单项质检结果"""

    check: str
    result: str  # pass | warn | fail | unknown
    detail: str


class QualityReportResponse(BaseModel):
    """单样例质检报告（GET /samples/{id}/quality）"""

    sample_id: UUID
    title: str
    scenario: str
    checks: list[QualityCheckOut]
    score: int  # 0-100


class QualitySummaryItem(BaseModel):
    """聚合条目（按分数升序=最差优先，前 50）"""

    sample_id: UUID
    title: str
    scenario: str
    score: int
    worst_result: str
    problems: list[str]  # warn/fail 项的 "check: detail"


class QualitySummaryResponse(BaseModel):
    """全库质检聚合（GET /quality/summary）"""

    total: int
    by_result: dict[str, int]  # pass/warn/fail/unknown → 计数（全库逐检查项累计）
    by_scenario: dict[str, dict]  # scenario → {samples, avg_score}
    items: list[QualitySummaryItem]


# ============== Extract（提取流水线，EAI-CUSTOM: coal-eia v2 BS3 二期③） ==============


class ExtractSourceKind(StrEnum):
    """提取源类型——auto 按扩展名（.txt 直读/.docx zip 解析/.doc 拒绝并提示 doc_convert）"""

    TXT = "txt"
    DOCX = "docx"
    AUTO = "auto"


class ExtractRequest(BaseModel):
    """提取流水线请求（POST /samples/{id}/extract）"""

    source_kind: ExtractSourceKind = ExtractSourceKind.AUTO
    save: bool = True  # True 写入 outline_json 并升级 status；False 仅返回预览


class OutlineSectionOut(BaseModel):
    no: str
    title: str


class OutlineChapterOut(BaseModel):
    no: str
    title: str
    sections: list[OutlineSectionOut] = []


class ExtractResponse(BaseModel):
    """提取结果预览（章节树 + 实体候选；save=True 时已入库）"""

    sample_id: UUID
    title: str
    source_kind: str  # 实际解析通道（auto 解析后的真实扩展名）
    source_chars: int
    chapters: list[OutlineChapterOut]
    candidates: dict[str, list[str]]
    saved: bool
