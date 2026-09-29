"""doc_graph 抽取 JSON Schema（skill LLM 结构化输出 → fail-closed 校验）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §5。
extra="forbid"=多余字段直接拒绝; relation 交叉引用在模型层校验。
EntityPayload/RelationPayload 的 etype/predicate 放宽为全枚举 Literal（共享 payload 层）,
域合法性收紧由 *Extraction 子类的域表 ClassVar + 基类 validator 完成（跨域枚举不混用）。
谓词角色表值 = tuple[tuple[str, str], ...] 多角色对集（2026-09-29 数据驱动改造, 单对谓词即
单元素元组; 校验从等值改为成员判定, 支持数注记见各新增对行尾）。
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
_ETYPE = Literal[
    "project",
    "bidder",
    "goods",
    "qualification",
    "mine",
    "org",
    "place",
    "sensitive_point",
    # eia 四类目标扩展（kernel P5, 2026-09-20）：①章节 ②逻辑链节点 ③阈值/条款 ④佐证
    "report",
    "chapter",
    "section",
    "pollution_source",
    "pollutant",
    "treatment_measure",
    "emission_standard",
    "monitoring",
    "standard_threshold",
    "regulation_clause",
    "evidence_requirement",
    "evidence_artifact",
    # eia v2 扩容（spec 2026-09-28 §4.2，计划 Task 9；定型替换在 Task 11）：
    # 资源地质 / 开采工程 / 排放骨架 / 影响结果 / 规划环评 / 受控词表概念 / 佐证
    "coal_seam",
    "aquifer",
    "stratigraphic_unit",
    "fault",
    "goaf",
    "mine_field",
    "mining_district",
    "working_face",
    "mining_method",
    "engineering_site",
    "coal_prep_plant",
    "emission_point",
    "waste_stream",
    "receiving_medium",
    "impact_result",
    "planning_scheme",
    "planning_change",
    "carrying_capacity",
    "retrospective_problem",
    "pollutant_concept",
    "measure_process_concept",
    "pollution_process_concept",
    "analogy_case",
    "measure_spec",
]
_PREDICATE = Literal[
    "bidder_of_project",
    "bidder_supplies_goods",
    "bidder_holds_qualification",
    "project_won_by_bidder",
    "org_compiles_project",
    "org_commissions_project",
    "org_develops_project",
    # eia 四类目标扩展（治理合规链/影响链/章节/阈值/佐证）
    "has_chapter",
    "has_subsection",
    "part_of",
    "treated_by",
    "governed_by",
    "monitored_by",
    "emitted_as",
    "threatens",
    "impact_to",
    "specifies_threshold",
    "cites_clause",
    "requires_evidence",
    "evidenced_by",
    # eia v2 扩容（spec 2026-09-28 §4.2/§4.3，计划 Task 9）：
    # affects=impact_result→sensitive_point（threatens 保持 (pollutant, sensitive_point) 单角色不变）
    "mines",
    "method_of",
    "develops",
    "causes",
    "affects",
    "protected_by",
    "drawdown_of",
    "emitted_via",
    "drains_to",
    "generates_waste",
    "disposed_by",
    "utilized_by",
    "sub_plan_of",
    "changes",
    "constrained_by",
    "problem_of",
    "specified_by",
    "analogous_to",
    "conflicts_with",
    # registry 37 谓词补齐（2026-09-29 数据驱动多对改造）：数据支撑的 3 个入 Literal+域表；
    # pollutes(最大组合支持4)/precedes(支持1) 低于 ≥5 门槛两处均不入——converter 仍丢弃, 待后续批次数据。
    "complies_with",
    "located_in",
    "regulated_by",
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


# --- bid 域表（4 谓词; 值 = tuple[tuple[str, str], ...] 多角色对集——单对谓词包单元素元组,
# 与 eia 表同构（2026-09-29 多对改造, bid 单对语义不变）; MappingProxyType 只读——converter 侧不得改表）---
_PREDICATE_ROLES: MappingProxyType[str, tuple[tuple[str, str], ...]] = MappingProxyType(
    {
        "bidder_of_project": (("bidder", "project"),),
        "bidder_supplies_goods": (("bidder", "goods"),),
        "bidder_holds_qualification": (("bidder", "qualification"),),
        "project_won_by_bidder": (("project", "bidder"),),
    }
)

# --- eia 域表（值 = tuple[tuple[str, str], ...]; 校验 = (subject_etype, object_etype) ∈ 对集）---
_EIA_PREDICATE_ROLES: MappingProxyType[str, tuple[tuple[str, str], ...]] = MappingProxyType(
    {
        "org_compiles_project": (("org", "project"),),
        "org_commissions_project": (("org", "project"),),
        "org_develops_project": (("org", "project"),),
        # 四类目标扩展（角色对 = 抽取器输出契约）
        "has_chapter": (("report", "chapter"),),
        "has_subsection": (("chapter", "section"),),
        "part_of": (
            ("section", "chapter"),
            ("mine", "mining_district"),  # 支持7条(2026-09-29 R2, "色连一号属于高头窑矿区")
            ("mine_field", "mining_district"),  # 支持7条(R2, "勘查区属于西部凹陷区")
            ("stratigraphic_unit", "stratigraphic_unit"),  # 支持6条(R2, "全新统风积沙属于第四系")
        ),
        "treated_by": (
            ("pollution_source", "treatment_measure"),
            ("engineering_site", "treatment_measure"),  # 支持14条(engineering_site对齐, 2026-09-29)
            ("waste_stream", "treatment_measure"),  # 支持20条(2026-09-29 R2, "污废水排入矿井污水处理站处理")
            ("mine", "treatment_measure"),  # 支持12条(R2, 矿方设施清单"锅炉烟气经布袋除尘器", 主体宽松指代)
            ("pollution_source", "measure_process_concept"),  # 支持6条(R2, "处理工艺: 混凝沉淀过滤消毒")
        ),
        "governed_by": (("treatment_measure", "emission_standard"),),
        "monitored_by": (
            ("emission_standard", "monitoring"),
            ("engineering_site", "monitoring"),  # 支持8条(engineering_site对齐, 2026-09-29)
            ("mine", "monitoring"),  # 支持7条(2026-09-29 R2, "煤矿生活污水处理设施监测结果")
        ),
        "emitted_as": (
            ("pollution_source", "pollutant"),
            ("waste_stream", "pollutant"),  # 支持5条(2026-09-29 R2, "生活污水主要污染物为CODcr")
        ),
        "threatens": (("pollutant", "sensitive_point"),),
        "impact_to": (("pollution_source", "sensitive_point"),),
        # specifies_threshold 只收"规定方"主语（标准/规划）；(pollutant|engineering_site, standard_threshold)
        # 支持29/6 条但主宾倒置（限值属于标准, 场地是达标方）拒收——见 R2 引文抽查。
        "specifies_threshold": (
            ("emission_standard", "standard_threshold"),
            ("planning_scheme", "standard_threshold"),  # 支持5条(2026-09-29 R2, "矿区规划规定总用水量173.8万m3/a")
        ),
        "cites_clause": (("report", "regulation_clause"),),
        "requires_evidence": (("treatment_measure", "evidence_requirement"),),
        "evidenced_by": (("treatment_measure", "evidence_artifact"),),
        # --- v2 扩容（spec 2026-09-28 §4.2/§4.3；affects=impact_result→sensitive_point，
        #     threatens 保持 (pollutant, sensitive_point) 单角色不变）---
        "mines": (
            ("mining_district", "coal_seam"),
            ("mine", "coal_seam"),  # 支持8条(2026-09-29 R2)
        ),
        "method_of": (
            ("working_face", "mining_method"),
            ("mine", "mining_method"),  # 支持25条(2026-09-29 R2, "矿井采用露天/井工开采")
        ),
        "develops": (("mine_field", "mining_district"),),
        "causes": (
            ("working_face", "impact_result"),
            ("engineering_site", "impact_result"),  # 支持6条(engineering_site对齐, 2026-09-29)
            ("pollutant", "impact_result"),  # 支持7条(2026-09-29 R2, "铁锰超标致地下水超标")
            ("pollution_process_concept", "impact_result"),  # 支持7条(R2, "污废水散排造成地下水污染")
            ("mine", "impact_result"),  # 支持6条(R2, "沉陷积水造成土壤次生盐渍化")
            ("impact_result", "impact_result"),  # 支持5条(R2, "沉陷导致第四系水重新分布"影响链)
            ("mining_method", "impact_result"),  # 支持5条(R2, "井工开采致地表沉陷裂缝")
        ),
        "affects": (("impact_result", "sensitive_point"),),
        "protected_by": (
            ("sensitive_point", "treatment_measure"),
            ("sensitive_point", "measure_spec"),  # 支持5条(2026-09-29 R2, "对罕台川留设保护煤柱")
        ),
        "drawdown_of": (("impact_result", "aquifer"),),
        "emitted_via": (("pollution_source", "emission_point"),),
        "drains_to": (
            ("emission_point", "receiving_medium"),
            ("receiving_medium", "receiving_medium"),  # 支持5条(2026-09-29 R2, 水系汇入"海拉尔河汇入黑龙江")
        ),
        "generates_waste": (("pollution_source", "waste_stream"),),
        "disposed_by": (
            ("waste_stream", "treatment_measure"),
            ("waste_stream", "engineering_site"),  # 支持6条(engineering_site对齐, 2026-09-29)
            ("waste_stream", "org"),  # 支持13条(2026-09-29 R2, "生活垃圾由垃圾处理站处理")
            ("waste_stream", "place"),  # 支持10条(R2, "岩土剥离物运往排土场")
        ),
        "utilized_by": (
            ("waste_stream", "treatment_measure"),
            ("waste_stream", "measure_process_concept"),  # 支持6条(2026-09-29 R2, "矿坑水处理后循环利用")
            ("waste_stream", "org"),  # 支持5条(R2, "灰渣运往砖厂作为原料综合利用")
        ),
        "sub_plan_of": (("mine_field", "planning_scheme"),),
        "changes": (("planning_change", "planning_scheme"),),
        "constrained_by": (("project", "carrying_capacity"),),
        "problem_of": (("retrospective_problem", "mine_field"),),
        "specified_by": (("treatment_measure", "measure_spec"),),
        "analogous_to": (("project", "analogy_case"),),
        "conflicts_with": (("regulation_clause", "regulation_clause"),),
        # --- registry 37 谓词补齐（2026-09-29 数据驱动多对改造；支持数 = 1564 条候选 raw 三元组计数,
        #     入选门槛 ≥5 且双侧 etype 在域枚举内, 引文语义抽查通过；pollutes(最大组合4)/precedes(1)
        #     未达门槛不入表。specifies_threshold+(engineering_site,standard_threshold) 支持6但因
        #     语义错位弃（规定阈值的主体只能是标准, 非场地））---
        "located_in": (
            ("evidence_artifact", "mine_field"),  # 支持11条
            ("treatment_measure", "mine"),  # 支持11条
            ("mine", "place"),  # 支持11条
            ("place", "place"),  # 支持10条
            ("sensitive_point", "place"),  # 支持9条
            ("monitoring", "aquifer"),  # 支持8条
            ("sensitive_point", "mine_field"),  # 支持6条
            ("mine", "mining_district"),  # 支持5条
            ("engineering_site", "place"),  # 支持5条
            ("engineering_site", "project"),  # 支持5条
        ),
        "complies_with": (
            ("waste_stream", "emission_standard"),  # 支持9条
            ("pollution_source", "emission_standard"),  # 支持6条
        ),
        "regulated_by": (("org", "regulation_clause"),),  # 支持7条
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
    predicate_roles: ClassVar[MappingProxyType[str, tuple[tuple[str, str], ...]]] = MappingProxyType({})

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
            if (subj, obj) not in roles:
                raise ValueError(f"relations[{i}] {r.predicate} 要求 (subject_etype, object_etype) 为 {roles} 之一, 实际 ({subj}, {obj})")
        return self


class BidExtraction(ExtractionPayload):
    """投标域抽取结果（首域）。"""

    domain: Literal["bid"]

    domain_etypes: ClassVar[frozenset[str]] = frozenset({"project", "bidder", "goods", "qualification"})
    domain_predicates: ClassVar[frozenset[str]] = frozenset(_PREDICATE_ROLES)
    predicate_roles: ClassVar[MappingProxyType[str, tuple[tuple[str, str], ...]]] = _PREDICATE_ROLES


class EiaExtraction(ExtractionPayload):
    """环评（EIA）域抽取结果。"""

    domain: Literal["eia"]

    domain_etypes: ClassVar[frozenset[str]] = frozenset(
        {
            "project",
            "mine",
            "org",
            "place",
            "sensitive_point",
            "report",
            "chapter",
            "section",
            "pollution_source",
            "pollutant",
            "treatment_measure",
            "emission_standard",
            "monitoring",
            "standard_threshold",
            "regulation_clause",
            "evidence_requirement",
            "evidence_artifact",
            # --- v2 扩容（spec 2026-09-28 §4.2，24 个；与 eia_v2_draft.yaml 枚举同源，
            #     Task 11 定型替换 registry/eia.yaml 后即为其超集切片）---
            "coal_seam",
            "aquifer",
            "stratigraphic_unit",
            "fault",
            "goaf",
            "mine_field",
            "mining_district",
            "working_face",
            "mining_method",
            "engineering_site",
            "coal_prep_plant",
            "emission_point",
            "waste_stream",
            "receiving_medium",
            "impact_result",
            "planning_scheme",
            "planning_change",
            "carrying_capacity",
            "retrospective_problem",
            "pollutant_concept",
            "measure_process_concept",
            "pollution_process_concept",
            "analogy_case",
            "measure_spec",
        }
    )
    domain_predicates: ClassVar[frozenset[str]] = frozenset(_EIA_PREDICATE_ROLES)
    predicate_roles: ClassVar[MappingProxyType[str, tuple[tuple[str, str], ...]]] = _EIA_PREDICATE_ROLES
