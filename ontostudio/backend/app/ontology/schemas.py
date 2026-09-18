"""Ontology 注册表 pydantic 模型（YAML → 类型化声明）.

母稿 §4.3/§4.4（R4 修订版）：
- 对象类型: enabled/deprecated + access + pk + properties（hidden 列引擎层零透出）
- 链接类型: enabled stub（D3）+ join（foreign_key | normalized_key_match 引擎级归一化）
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class DomainFile(BaseModel):
    """单个域 YAML 文件根模型。"""

    model_config = ConfigDict(extra="forbid")

    object_types: list[ObjectType] = []
    link_types: list[LinkType] = []
    # ---- registry v2 formal 段（kernel P1, EAI-CUSTOM）：全部可选，缺省 = 纯业务词表 ----
    namespaces: dict[str, str] | None = None  # 前缀 → 命名空间 IRI（国标 §9.2 每域一空间）
    formal: FormalSection | None = None  # OWL 2 RL 公理声明
