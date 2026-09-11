"""doc_graph 抽取 JSON Schema（skill LLM 结构化输出 → fail-closed 校验）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §5。
extra="forbid"=多余字段直接拒绝; relation 交叉引用在模型层校验。
新增抽取域 = 新增 *Extraction 模型 + etype/predicate 枚举, 不动引擎与读侧。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MentionPayload(BaseModel):
    """证据载荷（落 dg_mentions）。"""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=200)
    doc_span: dict = Field(default_factory=dict)  # {page?, quote_start?, quote_end?}
    quote: str = Field(default="", max_length=2000)


class EntityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etype: Literal["project", "bidder", "goods", "qualification"]
    name: str = Field(min_length=1, max_length=300)
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    mention: MentionPayload


class RelationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: Literal["bidder_of_project", "bidder_supplies_goods", "bidder_holds_qualification", "project_won_by_bidder"]
    subject: str  # 同 payload 内实体 name 引用
    object: str
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    mention: MentionPayload


_PREDICATE_ROLES: dict[str, tuple[str, str]] = {
    "bidder_of_project": ("bidder", "project"),
    "bidder_supplies_goods": ("bidder", "goods"),
    "bidder_holds_qualification": ("bidder", "qualification"),
    "project_won_by_bidder": ("project", "bidder"),
}


class BidExtraction(BaseModel):
    """投标域抽取结果（首域）。"""

    model_config = ConfigDict(extra="forbid")

    domain: Literal["bid"]
    extracted_by: str = Field(default="llm", max_length=100)
    thread_id: str = Field(default="", max_length=100)
    entities: list[EntityPayload] = Field(min_length=1)
    relations: list[RelationPayload] = []

    @model_validator(mode="after")
    def _check_relation_refs(self):
        names = {e.name for e in self.entities}
        name_to_etype = {e.name: e.etype for e in self.entities}
        for i, r in enumerate(self.relations):
            for side in ("subject", "object"):
                ref = getattr(r, side)
                if ref not in names:
                    raise ValueError(f"relations[{i}].{side} 引用未声明实体: {ref!r} (已声明: {sorted(names)})")
            roles = _PREDICATE_ROLES[r.predicate]
            subj, obj = name_to_etype[r.subject], name_to_etype[r.object]
            if (subj, obj) != roles:
                raise ValueError(f"relations[{i}] {r.predicate} 要求 (subject_etype, object_etype)={roles}, 实际 ({subj}, {obj})")
        return self
