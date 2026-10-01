"""C 库沉淀管线——stage JSON forms → 声明式映射 → EiaExtraction → dg_*（scope=project）.

设计: docs/superpowers/specs/2026-09-30-c-ingest-pipeline-design.md §3–§5
计划: docs/superpowers/plans/2026-09-30-c-ingest-pipeline-plan.md T1/T2/T3（管线半）

分工：
- 映射表 mapping_eia_planning.yaml 是**唯一声明源**（族→字段→实体类型/谓词/对端）；
  本模块是通用解释器——表驱动，改映射不加代码。
- build_payload 纯函数：forms + mapping → EiaExtraction（不碰 DB/图，单测零依赖）。
  fail-closed：字段缺席跳过并计入 skipped_fields（fail-visible）；整族未映射进
  unmapped_families；映射表 etype/谓词/角色对非法在 load_mapping 即 ValueError。
- 写入复用 3.5 机制：payload 携带 project_id → ingest_extraction 经 project_scoped_attrs
  自动打 scope=project + project_id（app/doc_graph/ingest.py，零 DDL）。
- 投影：写库后 load_from_sql 全量幂等装载（自然键 upsert）+ refresh 推理——图 = DB 忠实
  投影（与 actions/projection.py 同语义），不双写。测试 patch _reload_graph 绕开 DB。

谓词语义纪律：映射表声明的 (subject_etype, predicate, object_etype) 必须在
EiaExtraction.predicate_roles 内，load_mapping 静态校验；语义不匹配不强行连边
（如 drains_to 需排放口字段而表单无 → 表里不声明）。

已知边界（机制层声明，管线不复判）：C 库实体自然键 (domain,etype,norm_name) 全局
共享——跨项目同名实体 attrs|| 合并会翻转 project_id 归属（doc_graph/ingest.py
「⚠️ 自然键碰撞提示」明示，机制层不做隐式改名）。主场景为单项目工作区（技能
progress.json 单项目）不触发；多项目并存时应使用异名实体区分。coverage 的族归属
用 attrs.source 前缀精确判定，规避 waste_stream 等跨族共享 etype 的误判。

EAI-CUSTOM(2026-10-01, 子项目 4): 新文件，不触碰 harness/上游核心。
禁改 skills/ 下任何文件——本管线是 stage JSON 的图侧投影消费者，非第二写者。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

# 顶层 import（测试 monkeypatch 目标：app.ontology.c_ingest.pipeline.ingest_extraction）
from app.doc_graph.ingest import ingest_extraction

_MAPPING_PATH = Path(__file__).parent / "mapping_eia_planning.yaml"
_SRC_MAX = 200  # source 溯源标长度上限（attrs.source）
_QUOTE_MAX = 2000  # MentionPayload.quote 上限（schemas.py Field 约束）
_EXTRACTED_BY = "stage_json_ingest"
_CONFIDENCE = 0.95  # 结构化表单直映射（非 LLM 抽取），略低于 1 保留人审余地


# ── 映射表模型（yaml → 强类型，load 时 fail-closed）──


class ItemSpec(BaseModel):
    """array 字段逐元素实体 / entities 多类条目共用形状."""

    model_config = ConfigDict(extra="forbid")

    etype: str
    name: str = ""  # 单实体名：固定名，或 "."（标量字段值即名）
    name_from: list[str] | str = []  # 键序列按序取第一个非空；"." = 字符串元素值即名
    name_template: str = ""  # 无名回退模板：{idx} / {<key>}（键取自元素）
    name_template_keys: list[str] = []  # 模板 {key} 允许的元素键（防御任意格式化）


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = False  # 缺席 → skipped_fields（fail-visible）；coverage 按族级判定
    entity: ItemSpec | None = None  # 标量/object 字段 → 单实体
    items: ItemSpec | None = None  # array 字段 → 逐元素
    entities: list[ItemSpec] = []  # 一字段产多类实体（同元素）
    collect: list[str] = []  # 同族其他标量字段并入本实体 attrs
    relations: list[dict] = []  # 族内边：entities 多类 {predicate, from, to}（同元素 etype 配对）


class FamilySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element: str = ""
    fields: list[FieldSpec]


class IntraRelationSpec(BaseModel):
    """顶层族内边（名称锚定实体——如 collect 出的固定名「矸石」——字段条目表达不了）."""

    model_config = ConfigDict(extra="forbid")

    family: str
    predicate: str
    from_entity_name: str = ""
    from_field: str = ""
    to_field: str


class CrossRelationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicate: str
    from_family: str
    from_field: str
    to_family: str
    to_field: str
    to_entity: str = ""  # to 字段产多类实体时指明对端 etype
    match_field: str = ""  # 对端实体级条件：对端 attrs[match_field] == match_equals 才连（如标准 triplets 的 element）
    match_equals: str = ""


class StageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = ""
    project_entity_hint: str = ""  # project_id 对应矿区主体的提示路径（展示用，不参与校验）
    families: dict[str, FamilySpec]
    intra_relations: list[IntraRelationSpec] = []
    cross_relations: list[CrossRelationSpec] = []


class MappingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    domain: str
    stages: dict[str, StageSpec]


class _SafeFormatDict(dict):
    """name_template 渲染：缺键保留占位原样（与 rules_executor._SafeDict 同法）。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _field_item_specs(f: FieldSpec) -> list[ItemSpec]:
    return ([f.entity] if f.entity else []) + ([f.items] if f.items else []) + list(f.entities)


def load_mapping(path: Path = _MAPPING_PATH) -> MappingSpec:
    """映射表加载。fail-closed：schema 违例 / etype 或谓词不在域表 / 角色对不匹配 → ValueError。"""
    from app.doc_graph.schemas import EiaExtraction

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("映射表顶层须为对象")
    spec = MappingSpec(**data)
    for stage_name, stage in spec.stages.items():
        # 产物 etype 静态校验
        for fam_name, fam in stage.families.items():
            for f in fam.fields:
                for it in _field_item_specs(f):
                    if it.etype not in EiaExtraction.domain_etypes:
                        raise ValueError(f"映射表 {stage_name}.{fam_name} 字段 {f.name}: etype {it.etype!r} 不在 eia 域枚举内")
                for rel in f.relations:
                    if rel.get("predicate") not in EiaExtraction.domain_predicates:
                        raise ValueError(f"映射表 {stage_name}.{fam_name}.{f.name}: 谓词 {rel.get('predicate')!r} 不在 eia 域谓词集内")
                    if "to_field" not in rel:
                        etypes = [c.etype for c in _field_item_specs(f)]
                        subj, obj = rel.get("from") or (etypes[0] if etypes else ""), rel.get("to") or (etypes[-1] if etypes else "")
                        if subj and obj and (subj, obj) not in EiaExtraction.predicate_roles[rel["predicate"]]:
                            raise ValueError(f"映射表 {stage_name}.{fam_name}.{f.name}: {rel['predicate']} 角色对 ({subj}, {obj}) 不在域表——语义不匹配不强行连边")
        for rel in stage.intra_relations:
            if rel.predicate not in EiaExtraction.domain_predicates:
                raise ValueError(f"映射表 intra_relations: 谓词 {rel.predicate!r} 不在 eia 域谓词集内")
            if rel.family not in stage.families:
                raise ValueError(f"映射表 intra_relations: 未知族 {rel.family!r}")
            target_field = next((f for f in stage.families[rel.family].fields if f.name == rel.to_field), None)
            if target_field is None:
                raise ValueError(f"映射表 intra_relations: 族 {rel.family} 无字段 {rel.to_field!r}")
        for rel in stage.cross_relations:
            if rel.predicate not in EiaExtraction.domain_predicates:
                raise ValueError(f"映射表 cross_relations: 谓词 {rel.predicate!r} 不在 eia 域谓词集内")
            src = _endpoint_etype(stage, rel.from_family, rel.from_field)
            dst = rel.to_entity or _endpoint_etype(stage, rel.to_family, rel.to_field)
            if src and dst and (src, dst) not in EiaExtraction.predicate_roles[rel.predicate]:
                raise ValueError(
                    f"映射表 cross_relations {rel.from_family}.{rel.from_field}→{rel.to_family}.{rel.to_field}: {rel.predicate} 角色对 ({src}, {dst}) 不在域表 {EiaExtraction.predicate_roles[rel.predicate]} 内——语义不匹配不强行连边"
                )
    return spec


def _endpoint_etype(stage: StageSpec, family: str, fld: str) -> str:
    """cross/intra 端引用 (family, field) 的产物 etype；未知引用/多类实体返回 ""（运行时再定）。"""
    fam = stage.families.get(family)
    if fam is None:
        return ""
    for f in fam.fields:
        if f.name == fld:
            etypes = {c.etype for c in _field_item_specs(f)}
            return etypes.pop() if len(etypes) == 1 else ""
    return ""


# ── build：forms + mapping → EiaExtraction（纯函数）──


@dataclass
class BuildResult:
    payload: Any | None  # EiaExtraction | None（类型延后 import，避免模块级循环）
    unmapped_families: list[str] = field(default_factory=list)
    skipped_fields: list[str] = field(default_factory=list)  # 族.字段（值缺席/空/无名）
    fallback_named: list[str] = field(default_factory=list)  # 用回退模板命名的实体
    entity_count: int = 0
    relation_count: int = 0
    stage: str = ""

    def report(self) -> dict:
        return {"stage": self.stage, "unmapped_families": self.unmapped_families, "skipped_fields": self.skipped_fields, "fallback_named": self.fallback_named}


class _Builder:
    """单次 build 的解释器状态（实体/关系累积 + 自然键消重）。"""

    def __init__(self, stage_spec: StageSpec, stage: str) -> None:
        self.stage_spec = stage_spec
        self.stage = stage
        self.entities: dict[tuple[str, str], dict] = {}  # (etype, name) → {etype,name,attrs,quote}
        self.relations: dict[tuple[str, str, str], dict] = {}  # (subject,predicate,object)
        self.unmapped: list[str] = []
        self.skipped: list[str] = []
        self.fallback: list[str] = []
        self.by_origin: dict[tuple[str, str], list[tuple[str, str]]] = {}  # (family, field) → [(etype, name)]

    def _add_entity(self, etype: str, name: Any, attrs: dict, quote: str, family: str, fld: str) -> tuple[str, str] | None:
        if name is None or not str(name).strip():
            return None
        name = str(name).strip()[:300]
        merged = dict(attrs)
        merged["source"] = f"stage_json:{self.stage}:{family}#{fld}"[:_SRC_MAX]
        key = (etype, name)
        if key in self.entities:
            self.entities[key]["attrs"] = {**self.entities[key]["attrs"], **merged}  # 同自然键归并（后者浅覆盖）
        else:
            self.entities[key] = {"etype": etype, "name": name, "attrs": merged, "quote": quote}
        self.by_origin.setdefault((family, fld), []).append(key)
        return key

    def _element_name(self, elem: Any, spec: ItemSpec, idx: int, family: str, fld: str) -> str | None:
        if spec.name_from == ".":
            if isinstance(elem, str) and elem.strip():
                return elem.strip()
        elif isinstance(spec.name_from, list) and isinstance(elem, dict):
            for k in spec.name_from:
                v = elem.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        if spec.name_template:
            fmt: dict[str, str] = {"idx": str(idx)}
            for k in spec.name_template_keys:
                v = elem.get(k) if isinstance(elem, dict) else None
                if v is not None:
                    fmt[k] = str(v)
            self.fallback.append(f"{family}.{fld}#{idx}")
            return spec.name_template.format_map(_SafeFormatDict(fmt))
        return None  # 解析不出名：跳过（计入 skipped，fail-visible）

    def build_family(self, family: str, fam: FamilySpec, fdata: dict) -> None:
        """单族解释：字段产出实体 + 字段级 relations（entities 多类的同元素配对边）。"""
        for f in fam.fields:
            val = fdata.get(f.name)
            if val is None or val == "" or val == [] or val == {}:
                self.skipped.append(f"{family}.{f.name}")
                continue
            quote = json.dumps({f.name: val}, ensure_ascii=False, default=str)[:_QUOTE_MAX]
            produced: list[tuple[str, str]] = []
            if f.entity is not None:
                # 单实体：name="." → 标量值即名；否则固定名。object 值展平进 attrs，标量进 {字段名: 值}
                nm = str(val).strip() if f.entity.name == "." and isinstance(val, (str, int, float)) else f.entity.name
                attrs = {k: v for k, v in val.items() if v is not None} if isinstance(val, dict) else {f.name: val}
                key = self._add_entity(f.entity.etype, nm, attrs, quote, family, f.name)
                if key:
                    produced.append(key)
            else:
                specs = ([f.items] if f.items else []) + list(f.entities)
                for spec in specs:
                    if not isinstance(val, list):
                        self.skipped.append(f"{family}.{f.name}(non-array)")
                        continue
                    for i, elem in enumerate(val):
                        nm = self._element_name(elem, spec, i, family, f.name)
                        if nm is None:
                            self.skipped.append(f"{family}.{f.name}#{i}(unnamed)")
                            continue
                        attrs = {k: v for k, v in elem.items() if v is not None} if isinstance(elem, dict) else {"value": elem}
                        key = self._add_entity(spec.etype, nm, attrs, quote, family, f.name)
                        if key:
                            produced.append(key)
            if f.collect and produced:
                extra = {c: fdata[c] for c in f.collect if fdata.get(c) is not None}
                first = self.entities[produced[0]]
                first["attrs"] = {**first["attrs"], **extra, "source": f"stage_json:{self.stage}:{family}#{f.name}"[:_SRC_MAX]}
            for c in f.collect:
                if fdata.get(c) in (None, "", [], {}):
                    self.skipped.append(f"{family}.{c}")
            self.by_origin.setdefault((family, f.name), produced)
            for rel in f.relations:
                if "to_field" in rel:
                    for s_e, s_n in produced:
                        for o_e, o_n in self.by_origin.get((family, str(rel["to_field"])), []):
                            self._add_rel(str(rel["predicate"]), s_e, s_n, o_e, o_n, quote)
                else:
                    # entities 多类：from/to 指同元素配对的 etype（产出序 zip 对齐）
                    subs = [k for k in produced if k[0] == rel.get("from")]
                    objs = [k for k in produced if k[0] == rel.get("to")]
                    for (s_e, s_n), (o_e, o_n) in zip(subs, objs):
                        self._add_rel(str(rel["predicate"]), s_e, s_n, o_e, o_n, quote)

    def _add_rel(self, pred: str, s_e: str, s_n: str, o_e: str, o_n: str, quote: str) -> None:
        from app.doc_graph.schemas import EiaExtraction

        if s_n == o_n:
            return  # 自环无语义
        if (s_e, o_e) not in EiaExtraction.predicate_roles.get(pred, set()):
            return  # 角色对不匹配：放弃该边（声明面已静态校验；运行时对端可能是多类实体）
        self.relations.setdefault((s_n, pred, o_n), {"pred": pred, "s": s_n, "o": o_n, "quote": quote})

    def build_cross(self, rel: CrossRelationSpec, forms: dict) -> None:
        src = self.by_origin.get((rel.from_family, rel.from_field), [])
        dst = self.by_origin.get((rel.to_family, rel.to_field), [])
        if rel.to_entity:
            dst = [k for k in dst if k[0] == rel.to_entity]
        if rel.match_field:
            # 对端实体级条件过滤：元素键值已展开进 attrs，直接查 attrs（如标准 triplets 的 element=大气）
            dst = [k for k in dst if str(self.entities[k]["attrs"].get(rel.match_field, "")) == rel.match_equals]
        for s_e, s_n in src:
            for o_e, o_n in dst:
                self._add_rel(rel.predicate, s_e, s_n, o_e, o_n, f"cross:{rel.from_family}.{rel.from_field}->{rel.to_family}.{rel.to_field}")

    def build_intra(self, rel: IntraRelationSpec) -> None:
        if rel.from_entity_name:
            fam_etypes = {_endpoint_etype_of_field(f) for f in self.stage_spec.families[rel.family].fields}
            srcs = [k for k in self.entities if k[0] in fam_etypes and k[1] == rel.from_entity_name]
        else:
            srcs = self.by_origin.get((rel.family, rel.from_field), [])
        for s_e, s_n in srcs:
            for o_e, o_n in self.by_origin.get((rel.family, rel.to_field), []):
                self._add_rel(rel.predicate, s_e, s_n, o_e, o_n, f"intra:{rel.family}")


def _endpoint_etype_of_field(f: FieldSpec) -> str:
    return next(iter({c.etype for c in _field_item_specs(f)}), "")


def build_payload(project_id: str, stage: str, forms: dict, mapping: MappingSpec | None = None) -> BuildResult:
    """纯函数：forms + mapping → EiaExtraction（payload 为 None = 无映射数据可写）。"""
    from app.doc_graph.schemas import EiaExtraction, EntityPayload, MentionPayload, RelationPayload

    mapping = mapping or load_mapping()
    stage_spec = mapping.stages.get(stage)
    if stage_spec is None:
        raise ValueError(f"映射表无 stage {stage!r}（可用: {sorted(mapping.stages)}）")
    if not isinstance(forms, dict) or not forms:
        raise ValueError("forms 须为非空对象（整份 stage JSON 的 forms）")

    b = _Builder(stage_spec, stage)
    for family, fdata in forms.items():
        fam = stage_spec.families.get(family)
        if fam is None:
            b.unmapped.append(family)
            continue
        if not isinstance(fdata, dict):
            b.skipped.append(f"{family}(non-object)")
            continue
        b.build_family(family, fam, fdata)
    for rel in stage_spec.cross_relations:
        b.build_cross(rel, forms)
    for rel in stage_spec.intra_relations:
        b.build_intra(rel)

    result = BuildResult(payload=None, unmapped_families=b.unmapped, skipped_fields=b.skipped, fallback_named=b.fallback, stage=stage)
    if not b.entities:
        return result  # 无映射数据可写：不调 ingest（payload min_length=1 会拒）
    doc_id = f"stage_json:{stage}"
    entities = [EntityPayload(etype=e["etype"], name=e["name"], attrs=e["attrs"], confidence=_CONFIDENCE, mention=MentionPayload(document_id=doc_id, quote=e["quote"][:_QUOTE_MAX])) for e in b.entities.values()]
    relations = [RelationPayload(predicate=r["pred"], subject=r["s"], object=r["o"], confidence=_CONFIDENCE, mention=MentionPayload(document_id=doc_id, quote=r["quote"][:_QUOTE_MAX])) for r in b.relations.values()]
    result.payload = EiaExtraction(domain=mapping.domain, project_id=project_id, extracted_by=_EXTRACTED_BY, entities=entities, relations=relations)
    result.entity_count = len(entities)
    result.relation_count = len(relations)
    return result


# ── 写入 + 投影（生产路径；测试 patch ingest_extraction / _reload_graph 绕开 DB）──


async def ingest_project_forms(project_id: str, stage: str, forms: dict) -> dict:
    """build → DB 写入（scope=project 打标在 ingest_extraction 内）→ 图投影装载 + 推理刷新。"""
    if not project_id or not str(project_id).strip():
        raise ValueError("project_id 必填（技能工作区项目标识，≤200 字符）")
    project_id = str(project_id).strip()[:200]
    built = build_payload(project_id, stage, forms)
    if built.payload is None:
        return {**built.report(), "project_id": project_id, "entities_created": 0, "relations_created": 0, "written": False, "message": "无映射数据可写（forms 均为未映射族或字段全缺）"}
    counts = await ingest_extraction(built.payload)
    await _reload_graph()
    _refresh_inference()
    return {
        **built.report(),
        "project_id": project_id,
        "entities_created": counts.get("entities_upserted", 0),
        "relations_created": counts.get("relations", 0),
        "written": True,
    }


async def _reload_graph() -> None:
    """写库后的图投影：全量幂等装载（自然键 upsert，DB = 忠实真相）。推理刷新见 _refresh_inference。"""
    from app.ontology.kernel.service import get_kernel

    await get_kernel().load_from_sql()


def _refresh_inference() -> None:
    """推理重算（闭包 + 派生 + 规则）——与 actions/projection.py 的收尾同语义。"""
    from app.ontology.kernel.service import get_kernel

    get_kernel().refresh()


# ── coverage：对照映射表必填族 → C 库（图上）覆盖度 ──


def _project_family_stats(store: Any, project_id: str) -> dict[str, int]:
    """kernel 图上 scope=project 且 project_id 匹配的实体，按 attrs.source 的族前缀分组计数。

    族归属用 source 精确判定（stage_json:<stage>:<族>#<字段>）而非 etype 交集——
    waste_stream 等类型跨族共享，etype 交会把固废的矸石误判成 water 族齐套。
    """
    from app.ontology.mcp import _ASSERTED, _EIA_NS

    rows = store.query(f'SELECT ?e ?src WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/scope> "project" ; <{_EIA_NS}attr/project_id> {json.dumps(project_id, ensure_ascii=False)} ; <{_EIA_NS}attr/source> ?src }} }}')
    counts: dict[str, int] = {}
    for r in rows:
        src = str(r.get("src") or "")
        if src.startswith("stage_json:"):
            parts = src.split(":")
            if len(parts) >= 3:
                fam = parts[2].split("#")[0]
                counts[fam] = counts.get(fam, 0) + 1
    return counts


def check_project_coverage(project_id: str, stage: str = "planning_eia") -> dict:
    """门 1 图上齐套检查：映射表各族在本项目 C 库实体覆盖度 + 缺失清单。

    族 covered 判定 = 图（scope=project + project_id）存在 attrs.source 前缀
    stage_json:<stage>:<族># 的实体（source 精确归属，etype 交会误判跨族共享类型）。
    """
    from app.ontology.mcp import _kernel_store

    mapping = load_mapping()
    stage_spec = mapping.stages.get(stage)
    if stage_spec is None:
        raise ValueError(f"映射表无 stage {stage!r}")
    store = _kernel_store()
    counts = _project_family_stats(store, project_id)
    families_out = []
    for fam_name, fam in stage_spec.families.items():
        etypes = sorted({c.etype for f in fam.fields for c in _field_item_specs(f)})
        n = counts.get(fam_name, 0)
        families_out.append({"family": fam_name, "element": fam.element, "required": any(f.required for f in fam.fields), "etypes": etypes, "covered": n > 0, "entity_count": n})
    required = [f for f in families_out if f["required"]]
    missing = [f["family"] for f in required if not f["covered"]]
    return {
        "project_id": project_id,
        "stage": stage,
        "families": families_out,
        "required_family_count": len(required),
        "covered_required": len([f for f in required if f["covered"]]),
        "missing_families": missing,
        "coverage_complete": not missing,
        "hint": "coverage_complete=false 时缺失族对应 stage JSON 表单未沉淀或未 ingest——回技能侧核对 forms 完整性后重跑 ontology_ingest_project_forms。",
    }
