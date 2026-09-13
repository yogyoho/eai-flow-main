"""doc_graph 抽取 JSON Schema（skill LLM 结构化输出 → fail-closed 校验）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §5。
extra="forbid"=多余字段直接拒绝; relation 交叉引用在模型层校验。
EntityPayload/RelationPayload 的 etype/predicate 放宽为全枚举 Literal（共享 payload 层）,
域合法性收紧由 *Extraction 子类的域表 ClassVar + 基类 validator 完成（跨域枚举不混用）。
新增抽取域 = 新增 *Extraction 模型 + 域表 ClassVar, 不动引擎与读侧。
"""

from datetime import datetime
from types import MappingProxyType
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MentionPayload(BaseModel):
    """证据载荷（落 dg_mentions）。"""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=200)
    doc_span: dict = Field(default_factory=dict)  # {page?, quote_start?, quote_end?}
    quote: str = Field(default="", max_length=2000)


# 全枚举 Literal（bid 4 etype + eia 5 etype, project 共享 → 8; bid 4 谓词 + eia 3 谓词 → 7）。
# 共享 payload 只约束全集, 域内合法性由 *Extraction 子类校验。
_ETYPE = Literal["project", "bidder", "goods", "qualification", "mine", "org", "place", "sensitive_point"]
_PREDICATE = Literal[
    "bidder_of_project",
    "bidder_supplies_goods",
    "bidder_holds_qualification",
    "project_won_by_bidder",
    "org_compiles_project",
    "org_commissions_project",
    "org_develops_project",
]


class EntityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etype: _ETYPE
    name: str = Field(min_length=1, max_length=300)
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    mention: MentionPayload


class RelationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: _PREDICATE
    subject: str  # 同 payload 内实体 name 引用
    object: str
    attrs: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    mention: MentionPayload


# --- bid 域表（4 谓词角色; MappingProxyType 只读——converter 侧不得改表）---
_PREDICATE_ROLES: MappingProxyType[str, tuple[str, str]] = MappingProxyType(
    {
        "bidder_of_project": ("bidder", "project"),
        "bidder_supplies_goods": ("bidder", "goods"),
        "bidder_holds_qualification": ("bidder", "qualification"),
        "project_won_by_bidder": ("project", "bidder"),
    }
)

# --- eia 域表（3 谓词全为 org→project 角色）---
_EIA_PREDICATE_ROLES: MappingProxyType[str, tuple[str, str]] = MappingProxyType(
    {
        "org_compiles_project": ("org", "project"),
        "org_commissions_project": ("org", "project"),
        "org_develops_project": ("org", "project"),
    }
)


class ExtractionPayload(BaseModel):
    """抽取结果基类——共享字段 + 域枚举收紧/交叉引用/谓词角色校验.

    域表由子类以 ClassVar 覆盖; 基类默认空集 → 直接实例化基类时任何实体/谓词都被拒（fail-closed）。
    """

    model_config = ConfigDict(extra="forbid")

    domain: str  # 域标识（基类契约, ingest 通用取值依赖）; Literal 收窄由子类覆盖
    extracted_by: str = Field(default="llm", max_length=100)
    thread_id: str = Field(default="", max_length=100)
    entities: list[EntityPayload] = Field(min_length=1)
    relations: list[RelationPayload] = []

    domain_etypes: ClassVar[frozenset[str]] = frozenset()
    domain_predicates: ClassVar[frozenset[str]] = frozenset()
    predicate_roles: ClassVar[MappingProxyType[str, tuple[str, str]]] = MappingProxyType({})

    @model_validator(mode="after")
    def _check_domain_and_refs(self):
        dom = type(self).__name__
        for i, e in enumerate(self.entities):
            if e.etype not in self.domain_etypes:
                raise ValueError(f"entities[{i}].etype {e.etype!r} 不在 {dom} 域枚举内 (允许: {sorted(self.domain_etypes)})")
        names = {e.name for e in self.entities}
        name_to_etype = {e.name: e.etype for e in self.entities}
        for i, r in enumerate(self.relations):
            if r.predicate not in self.domain_predicates:
                raise ValueError(f"relations[{i}].predicate {r.predicate!r} 不在 {dom} 域谓词集内 (允许: {sorted(self.domain_predicates)})")
            for side in ("subject", "object"):
                ref = getattr(r, side)
                if ref not in names:
                    raise ValueError(f"relations[{i}].{side} 引用未声明实体: {ref!r} (已声明: {sorted(names)})")
            roles = self.predicate_roles[r.predicate]
            subj, obj = name_to_etype[r.subject], name_to_etype[r.object]
            if (subj, obj) != roles:
                raise ValueError(f"relations[{i}] {r.predicate} 要求 (subject_etype, object_etype)={roles}, 实际 ({subj}, {obj})")
        return self


class BidExtraction(ExtractionPayload):
    """投标域抽取结果（首域）。"""

    domain: Literal["bid"]

    domain_etypes: ClassVar[frozenset[str]] = frozenset({"project", "bidder", "goods", "qualification"})
    domain_predicates: ClassVar[frozenset[str]] = frozenset(_PREDICATE_ROLES)
    predicate_roles: ClassVar[MappingProxyType[str, tuple[str, str]]] = _PREDICATE_ROLES


class EiaExtraction(ExtractionPayload):
    """环评（EIA）域抽取结果。"""

    domain: Literal["eia"]

    domain_etypes: ClassVar[frozenset[str]] = frozenset({"project", "mine", "org", "place", "sensitive_point"})
    domain_predicates: ClassVar[frozenset[str]] = frozenset(_EIA_PREDICATE_ROLES)
    predicate_roles: ClassVar[MappingProxyType[str, tuple[str, str]]] = _EIA_PREDICATE_ROLES
