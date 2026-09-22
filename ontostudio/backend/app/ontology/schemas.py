"""Ontology 注册表 pydantic 模型（YAML → 类型化声明）.

母稿 §4.3/§4.4（R4 修订版）：
- 对象类型: enabled/deprecated + access + pk + properties（hidden 列引擎层零透出）
- 链接类型: enabled stub（D3）+ join（foreign_key | normalized_key_match 引擎级归一化）
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PropertySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str  # 物理列名（snake_case）
    api_name: str  # 透出名（camelCase）
    type: Literal["string", "integer", "number", "boolean", "date", "datetime", "json", "uuid"]
    description: str = ""
    indexed: bool = False
    filterable: bool = False
    searchable: bool = False  # search_objects ILIKE 候选
    hidden: bool = False  # true = 服务端强制永不透出（如 connection_config）
    format: str | None = None  # currency | percent | date | text
    unit: str | None = None
    enum: list[str] | None = None


class AccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Literal["postgres_ext", "data_source"]
    table: str | None = None  # postgres_ext: 扩展库物理表
    source_id: str | None = None  # data_source: data_sources.name
    table_name: str | None = None  # data_source: 外部库表名


class PKConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    api_name: str
    type: Literal["string", "integer", "uuid"]
    immutable: bool = True


class ETypeClass(BaseModel):
    """etype → OWL 类映射（国标附录 A 类元数据子集）。

    YAML 键用 camelCase（subClassOf/equivalentClass/hasKey，与设计稿一致），
    python 侧 snake_case 双向兼容（populate_by_name）。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    class_name: str | None = Field(default=None, alias="class")  # 缺省 = etype PascalCase
    sub_class_of: list[str] = Field(default_factory=list, alias="subClassOf")
    equivalent_class: list[str] = Field(default_factory=list, alias="equivalentClass")
    has_key: list[str] = Field(default_factory=list, alias="hasKey")
    label: str | None = None  # 中文标签；缺省用 etype 原名
    definition: str | None = None


class ObjectType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_name: str
    display_name: str
    description: str
    domain: str
    icon: str = "📦"
    enabled: bool = True
    deprecated: bool = False
    version: int = 1
    access: AccessConfig
    pk: PKConfig
    properties: list[PropertySchema] = Field(min_length=1)
    run_source: str | None = None  # 溯源提示钩子（如 cpa_run_history）
    etype_classes: dict[str, ETypeClass] | None = None  # registry v2：etype → OWL 类（kernel P1）
    # EAI-CUSTOM (动作层, 设计 §3): 数据范围归属——值取 permissions.yaml 的**模块 key**
    # （ontology / contract_price / spare_parts / bid_quote…），不是 scope id。
    scope_resource: str | None = None
    # 模板字段名 ≠ 本表列名时的覆盖；缺省恒等映射。
    scope_bindings: dict[str, str] | None = None

    def visible_properties(self, include_hidden: bool = False) -> list[PropertySchema]:
        return [p for p in self.properties if include_hidden or not p.hidden]


class JoinConfig(BaseModel):
    """链接 join 声明。

    foreign_key: source_column → target_column 精确相等（同库单 SQL）。
    normalized_key_match: key_pairs 任一相等（引擎统一 LOWER(BTRIM) + 两侧非空守卫，
    R4：归一化是引擎级标准，不做 per-link ad-hoc 表达式）；source_filter 为源侧附加谓词。
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["foreign_key", "normalized_key_match"]
    source_column: str | None = None
    target_column: str | None = None
    key_pairs: list[list[str]] | None = None  # [[source_col, target_col], ...]，any-of
    source_filter: dict[str, Any] | None = None


class LinkType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_name: str
    display_name: str
    source: str  # ObjectType.api_name
    target: str
    cardinality: Literal["1:1", "N:1", "N:N"]
    direction: Literal["bidirectional"] = "bidirectional"
    reverse: str
    enabled: bool = True  # D3: false = stub——describe 可见并标注, 遍历拒绝
    note: str | None = None  # 如召回探测结果（D12）
    version: int = 1
    cross_module: bool = False
    join: JoinConfig


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    registry_version: int = 1  # 内存单调递增起点；实际版本由加载器维护
    hot_reload: bool = True
    files: list[ManifestFile] = Field(min_length=1)


class PropertyChainAxiom(BaseModel):
    """owl:propertyChainAxiom 声明（环评逻辑链等派生路径）。"""

    model_config = ConfigDict(extra="forbid")

    derived: str  # 派生谓词（如 org_in_ecosystem_of）
    chain: list[str] = Field(min_length=2)  # 链上谓词序列


class InversePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair: list[str] = Field(min_length=2, max_length=2)


class FormalSection(BaseModel):
    """registry v2 formal 段：全局公理（owl:Class/ObjectProperty 层，非实例层）。"""

    model_config = ConfigDict(extra="forbid")

    property_chains: list[PropertyChainAxiom] = Field(default_factory=list)
    transitive: list[str] = Field(default_factory=list)
    inverse: list[InversePair] = Field(default_factory=list)
    disjoint: list[str] = Field(default_factory=list)  # 互斥类名序列（一条声明一组）


class Precondition(BaseModel):
    """动作前置条件：只允许「列 op 字面量」——不做表达式求值。

    EAI-CUSTOM: 设计 §1.1。对标 M2 行为模型的谓词语法，收窄到可静态校验的子集。
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    op: Literal["eq", "ne", "in", "not_in", "is_null", "not_null"]
    value: Any | None = None


class StateChange(BaseModel):
    """动作后置：受影响列的新值。set 与 now 互斥。"""

    model_config = ConfigDict(extra="forbid")

    field: str
    set: Any | None = None
    now: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> StateChange:
        if self.now == (self.set is not None):
            raise ValueError(f"{self.field}: set 与 now 必须二选一（不可同时给出或同时缺省）")
        return self


class ActionSpec(BaseModel):
    """注册表动作声明（设计 §1.1）。本期只支持 COMMAND。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    domain: str
    target: str  # ObjectType.api_name
    behavior_type: Literal["COMMAND"] = "COMMAND"
    required_permissions: list[str] = Field(min_length=1)
    preconditions: list[Precondition] = Field(default_factory=list)
    postconditions: list[StateChange] = Field(min_length=1)
    version: int = 1


class DomainFile(BaseModel):
    """单个域 YAML 文件根模型。"""

    model_config = ConfigDict(extra="forbid")

    object_types: list[ObjectType] = []
    link_types: list[LinkType] = []
    # ---- registry v2 formal 段（kernel P1, EAI-CUSTOM）：全部可选，缺省 = 纯业务词表 ----
    namespaces: dict[str, str] | None = None  # 前缀 → 命名空间 IRI（国标 §9.2 每域一空间）
    formal: FormalSection | None = None  # OWL 2 RL 公理声明
    # ---- 动作层（设计 §1.1, EAI-CUSTOM）：声明式写回；缺省空 = 无动作 ----
    actions: list[ActionSpec] = []

    @model_validator(mode="after")
    def _check_refs(self) -> DomainFile:
        """动作声明的交叉引用校验（构造即校验，fail-closed）。

        EAI-CUSTOM: 设计 §1.1。**模型级**校验而非「公开方法 + 须显式调用」——与本仓既有
        跨字段校验同一模式（`app/doc_graph/schemas.py` 的 `ExtractionPayload._check_domain_and_refs`），
        调用方只需 `model_validate`，不存在「忘了调就静默半加载」的路径。

        分工边界（M-1）：本校验器只管**列引用**（`field` / `scope_bindings` 是否指向本文件
        已声明的列）。`scope_resource` 的**值域**（是否已知模块 key）不在校验，仍在
        `scripts/ontology_lint.py`（Task 9）——别以为漏了。

        不对称说明（M-4）：`actions[].target` 只接受**同文件**已声明的 ObjectType，而
        `link_types` 允许跨文件前向引用。这是有意收窄：动作与其目标同域同文件（Task 3 的
        `review_entity.*` 与 `graph_entity` 同在 `doc_graph.yaml`），跨域动作还会同时踩到
        下面 M-2 的 domain 一致性校验。
        """
        by_api_name = {ot.api_name: ot for ot in self.object_types}
        props = {name: {p.name for p in ot.properties} for name, ot in by_api_name.items()}

        seen: set[str] = set()
        for a in self.actions:
            if a.id in seen:
                raise ValueError(f"duplicate action id: {a.id}")
            seen.add(a.id)
            if a.target not in by_api_name:
                raise ValueError(f"unknown action target: {a.target!r} (action {a.id})")
            # M-2: action.domain 会写进 dg_action_audit.domain，而同行的表名来自 target 对象。
            # 两者不一致会产出「domain 与表对不上」的审计行，而审计是这条链路唯一的追溯凭据。
            target_domain = by_api_name[a.target].domain
            if a.domain != target_domain:
                raise ValueError(f"action {a.id}: domain {a.domain!r} 与 target 所属域 {target_domain!r} 不一致")
            declared = props[a.target]
            for cond in list(a.preconditions) + list(a.postconditions):
                if cond.field not in declared:
                    raise ValueError(f"unknown action field: {cond.field!r} on {a.target} (action {a.id})")

        for ot in self.object_types:
            declared = props[ot.api_name]
            for template_field, physical in (ot.scope_bindings or {}).items():
                if physical not in declared:
                    raise ValueError(f"unknown scope binding: {template_field}->{physical} on {ot.api_name}")
        return self
