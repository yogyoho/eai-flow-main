"""bid_write API schemas(批十九 T5)——与 bid_review/schemas.py 同构(from_
orm 全开,progress/engine_meta 直透;矩阵行 PATCH 单模型)。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WriteTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    biz_no: str | None = None
    status: str
    progress: dict = Field(default_factory=dict)
    error: str | None = None
    project_name: str | None = None
    lot_name: str | None = None
    tender_no: str | None = None
    created_at: datetime | None = None
    engine_meta: dict = Field(default_factory=dict)


class MatrixRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clause_id: str
    kind: str
    source_path: str
    requirement: str
    star: bool
    strategy: str
    target_section: str
    evidence_refs: list = Field(default_factory=list)
    status: str
    conf: float | None = None
    verified: bool = False
    note: str = ""


class MatrixRowPatch(BaseModel):
    """行级人工卡点(F1):strategy 推进 + 确认/解阻;star 行 negative 须 note
    (routers 校验 422)。status 合法值=draft|confirmed|blocked(解阻=确认)。"""

    strategy: str | None = None
    status: str | None = None
    target_section: str | None = None
    note: str | None = None
    evidence_refs: list[Any] | None = None


class GenerateKnobs(BaseModel):
    """生成旋钮(批廿一 M2;POST /generate body;None 键不覆盖 meta.knobs 已存值)。"""

    unit_prices: dict[str, str] | None = None
    sign_date: str | None = None
    price_note: str | None = None
    general_commitments: list[dict] | None = None
    page_estimates: dict[str, int] | None = None
    total_pages: int | None = None
    # 批廿五 P1-δ:质保承诺(L4-001 输入 bid.warranty_period;原样透传不造数,单位随填)
    warranty_period: str | None = None


class MaterialIn(BaseModel):
    """素材实体新建(F2/P1-α);entity_type 合法值=contracts.MATERIAL_ENTITY_TYPES
    (非法 422 面);verifiable 不收=派生 bool(evidence_refs)。"""

    entity_type: str
    name: str
    fields: dict = Field(default_factory=dict)
    evidence_refs: list = Field(default_factory=list)


class MaterialPatch(BaseModel):
    """素材实体部分更新(None 键不覆盖)。"""

    name: str | None = None
    fields: dict | None = None
    evidence_refs: list | None = None


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    name: str
    fields: dict = Field(default_factory=dict)
    evidence_refs: list = Field(default_factory=list)
    verifiable: bool = False
    created_at: datetime | None = None


class ProfileIn(BaseModel):
    """投标主体 profile(BL 主体信息唯一素材源;形态={name, legal_rep, …} 自由面)。"""

    profile: dict


class LetterDefaults(BaseModel):
    """函默认值(project.policy.letter_defaults;抽取缺席时的 D1 兜底填面)。"""

    model_config = ConfigDict(extra="forbid")

    validity_days: int | None = None
    sign_date: str | None = None


class PolicyBody(BaseModel):
    """project.policy.* 键词汇钉(P1-β):extra=forbid→ghost 键 422;
    tax_rate 0..1(0.09=9%);price_adjust_mechanism=False→PS-009 命中升 D0。"""

    model_config = ConfigDict(extra="forbid")

    letter_defaults: LetterDefaults | None = None
    tax_rate: float | None = Field(default=None, ge=0, le=1)
    price_adjust_mechanism: bool | None = None


class DocumentIn(BaseModel):
    """正文 AST 保存(批廿八 M2;PUT 幂等全量)。ast 根 type 必须=="doc"
    (routers 422 面);schema_version=editor document_ast_schema semver。"""

    ast: dict
    schema_version: str = ""


class EditorAssertIn(BaseModel):
    """编辑器真执行器请求(批三十;只读)。ast 根 type 必须=="doc"(routers 422);
    skills 缺省=全量(CMN 恒执行)。不落 skill_run:编辑防抖高频面。"""

    ast: dict
    skills: list[str] | None = None


class ApprovalSubmitIn(BaseModel):
    """提交正文审批（批三十二）。ast 缺省=使用已保存正文；传入则以本次 AST
    冻结为新修订，避免未保存内容漏出审批快照。"""

    ast: dict | None = None
    schema_version: str = ""
    document_hash: str | None = None
    workflow_definition_id: str | None = None
    reviewer_ids: list[str] | None = None
    gate_mode: str | None = None
    ratio_threshold: float | None = Field(default=None, ge=0, le=1)
    label: str | None = None
    comment: str | None = None


class ApprovalActionIn(BaseModel):
    """审批动作；instance_id 防误操作到另一轮审批。"""

    instance_id: str
    action: Literal["approved", "rejected"]
    comment: str | None = None
