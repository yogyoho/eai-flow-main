#!/usr/bin/env python3
"""EIA B 库领域规律挖掘（ontostudio 子项目 5 交付 1；2026-09-30 归并深化版）——真实图三类高频组合统计.

EAI-CUSTOM(2026-09-30, 子项目 5): 只读脚本，不写库、不碰容器。挖掘只 load 断言图（不 refresh）。

用法（宿主机本地，与 eia_rules_baseline.py 同通道）:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_mine.py
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_mine.py --min-support 2   # 扩量门槛
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_mine.py --no-normalize    # 关归一（复现旧基线）

流程 = 生产同路径：dg_* 三表 → KernelService.load_from_sql（内存图）→ 断言图三类链模式
挖掘 → 频次聚合 → 落盘 JSON + Markdown 到 scripts/eia_pattern_mine_out/。

归并挖掘（2026-09-30 深化）：聚合前先做**变体归一**——实体名按受控词表
（scripts/eia_schema_mining/controlled_vocab.yaml）aliases 映射到规范名（悬浮/ss→悬浮物、
有资质的单位→有资质单位……），无别名映射保持原名；「、」复合名仅当**每段**都命中词表时
全分解展开（如「悬浮物、cod、石油类、氟化物、溶解性总固体」→ 5 条规范污染物），否则整体保留。
归一后按规范名配对聚合：变体对合并（support=报告集**并集**——保持「跨报告共现」语义，不做
算术累加虚高），碎片对消失；entries 额外带 subject_variants/object_variants（变体名+实际 etype
清单，供 eia_pattern_ingest 把变体实例也连 analogous_to 边）。

五类组合（support 阈值见 --min-support，默认 3；批次 2 2026-10-01 新增④⑤）：
  ① 治理规律  X —emitted_as→ 污染物 P，X —treated_by→ 治理措施 T   （什么污染物配什么工艺）
  ② 标准规律  治理措施 T —governed_by→ 排放标准 S                 （什么工艺配什么标准）
  ③ 处置规律  固废流 W —disposed_by/utilized_by→ 处置去向 G       （什么固废去什么处置）
  ④ 敏感点防护 敏感点 —protected_by→ 治理措施 T                   （哪类敏感点配什么防护）
  ⑤ 监测覆盖  矿区/工程场地 —monitored_by→ 监测要求 M             （哪类源配什么监测）

批次 2 类型归组（EAI-CUSTOM 2026-10-01）：④⑤主语是「类型」不是单点名——敏感点/源的名
一报告一换（王家村/吕家沟村…），类型才跨报告可比。主体名按关键词归组表
（SENSITIVE_POINT_TYPES / MONITOR_SOURCE_TYPES，顺序=优先级 first-match，维护=往组内加
关键词）映射为类型名作 canonical subject；实际单点实例名照旧记入 subject_variants 供
ingest 变体连边（support 口径不变=配对级去重报告数）。未命中关键词表的主体跳过并打印
（mine 主体另有 etype 兜底矿区整体）；④的宾语侧只收 treatment_measure（protected_by 的
measure_spec 煤柱规格对 6 条不收，保持任务口径），object 侧照旧走受控词表位置归一。

support 定义（B 库 domain_common 语义要求跨项目共性，同报告多条同配对是冗余不是共性）：
  support_count    = 配对级**去重报告数**——按构成该配对路径的**边的自身溯源**
                     （dg_mentions.relation_id → document_id slug）聚合；边无 relation mention 的
                     历史行回退端点实体溯源（mention.document_id ∪ attrs.source_report）。
                     端点实体各自 mention 覆盖率的并集会虚高（两实体各在 20 份报告出现 ≠ 该配对
                     在 20 份报告共现），故不入 support；
  occurrence_count = 去重路径实例数（按中间节点/对端实体去重）——同报告冗余度，仅作参考。
只挖 scope=sample 实体（A 库是蒸馏原料；B/C 库产物不参与自我蒸馏）。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DatabaseConfig  # noqa: E402
from app.ontology.kernel.service import KernelService  # noqa: E402

OUT_DIR = Path(__file__).parent / "eia_pattern_mine_out"
VOCAB_PATH = Path(__file__).parent / "eia_schema_mining" / "controlled_vocab.yaml"

_PRED_NS = "https://ontology.eai-flow.com/eia#predicate/"
_ATTR_NS = "https://ontology.eai-flow.com/eia#attr/"
_EIA_CLASS_NS = "https://ontology.eai-flow.com/eia#"
_KERNEL_NS = "https://ontology.eai-flow.com/kernel#"
_ASSERTED = "graph:asserted"

_DOC_PREFIXES = ("eia-batch:", "eia-sample:")

# 处置/利用去向的目标 etype 白名单（谓词角色表 2026-09-29 R2 支持域）
_DISPOSAL_TARGET_ETYPES = ("treatment_measure", "org", "engineering_site", "place", "measure_process_concept")

# B2 批次 etype 白名单：④防护宾语只收治理措施（protected_by 的 measure_spec 煤柱规格对不收，保持任务口径）；
# ⑤监测主语=矿区/工程场地（monitored_by 角色表支持域；emission_standard→monitoring 0 边不设）。
_PROTECT_TARGET_ETYPES = ("treatment_measure",)
_MONITOR_SOURCE_ETYPES = ("mine", "engineering_site")


# ---------------------------------------------------------------- 受控词表归一


# 三类模式各位置的适用词表（按位置作用域归一——比按 etype 更窄更准：治理主语只可能是污染物概念、
# 处置宾语只可能是处置去向概念；同名跨表（如「矸石井下充填」既是 measure 概念名又是井下充填别名）
# 在位置作用域下天然无冲突）。
# ①治理  subject=pollutant_concept / object=measure_process_concept
# ②标准  subject=measure_process_concept / object=（emission_standard，无表）
# ③处置  subject=（waste_stream，无表）/ object=disposal_target_concept ∪ measure_process_concept
POSITION_TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "治理": {"subject": ("pollutant_concept",), "object": ("measure_process_concept",)},
    "标准": {"subject": ("measure_process_concept",), "object": ()},
    "处置": {"subject": (), "object": ("disposal_target_concept", "measure_process_concept")},
    # B2：敏感点防护 subject=类型归组（关键词表，见 SENSITIVE_POINT_TYPES，非词表归一）/ object=measure 表；
    # 监测覆盖 subject=源类型归组 / object=monitoring（无词表，保原名）。
    "敏感点防护": {"subject": (), "object": ("measure_process_concept",)},
    "监测覆盖": {"subject": (), "object": ()},
}

# ---------------------------------------------------------------- B2 类型归组表（顺序=优先级 first-match；维护=往组内加关键词）


# 敏感点类型关键词表：单点名一报告一换（王家村/吕家沟村…），按类型归组才跨报告可比。
# 注意优先级语义：「基本农田保护区」归农田不归保护区（①先于③）、「达溪河中华鳖…保护区」
# 归保护区不归水体/保护生物（③先于⑤⑥）。未命中任何关键词的敏感点跳过（打印清单供增补）。
SENSITIVE_POINT_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("基本农田", ("基本农田", "永久农田")),
    ("遗址文物", ("遗址", "烽火台", "烽燧", "古墓", "墓", "文物", "化石", "岩画", "坎儿井", "清真寺", "纪念址", "堡址", "出土点", "古城", "长城", "古建筑")),
    ("保护区", ("保护区", "森林公园", "地质公园", "公园", "生态红线", "保护红线")),
    ("公益林", ("公益林", "林地")),
    ("保护生物", ("古树", "动物", "植物", "生物", "产卵场", "越冬场", "种质", "候鸟", "龟", "鳖", "鱼")),
    ("水体", ("河", "水库", "湿地", "水源", "水体", "河道", "湖泊", "湖")),
    ("城镇边界", ("开发边界",)),
    ("村庄居民点", ("村", "居民点", "村镇", "集镇", "社区", "城镇", "镇")),
    ("线路", ("高速", "公路", "国道", "省道", "铁路", "专用线", "输电", "输气", "特高压", "千伏", "kv", "大桥", "管道")),
    ("草地", ("草原", "草地")),
]

# 监测源类型关键词表：污染源/场地主体按源类型归组（与敏感点同机制）。
# 「…排土场/矸石场地」堆存语义优先于工业场地（③先于④）。
MONITOR_SOURCE_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("矿井水", ("矿井水", "矿坑水", "生活污水")),
    ("锅炉烟气", ("锅炉", "烟气", "供热", "废气")),
    ("矸石堆场", ("矸石", "排矸", "排土场", "煤泥")),
    ("工业场地", ("工业场地", "工业广场", "厂界", "厂区", "场地")),
    ("线路", ("铁路", "专用线", "道路", "公路", "输电")),
    ("矿区整体", ("矿区", "煤矿", "矿井", "露天", "井田")),
]

# 关键词未命中时的 etype 兜底：mine 主体多为「XX煤矿/XX一井」专名碎片，按矿区整体聚合；
# engineering_site 无兜底——未命中即跳过（场地专名归组价值低，打印清单）。
MONITOR_SOURCE_FALLBACK: dict[str, str] = {"mine": "矿区整体"}


def _classify_by_keywords(name: str, table: list[tuple[str, tuple[str, ...]]]) -> str | None:
    """名字 → 类型名（表顺序 first-match，子串命中，latin 关键词大小写不敏感）；全未命中 None。"""
    lowered = (name or "").strip().lower()
    for type_name, keywords in table:
        if any(k in lowered for k in keywords):
            return type_name
    return None


def load_normalizer(vocab_path: Path) -> NameNormalizer:
    """受控词表 yaml → NameNormalizer（alias 键统一 strip+lower，大小写不敏感覆盖 ss/COD/NOx 类）。"""
    raw = yaml.safe_load(vocab_path.read_text(encoding="utf-8")) or {}
    per_table_maps: dict[str, dict[str, str]] = {}
    conflicts: list[str] = []
    for table, spec in raw.items():
        mapping: dict[str, str] = {}
        for concept in spec.get("concepts", []):
            canon = str(concept["name"]).strip()
            for alias in [canon, *concept.get("aliases", [])]:
                key = str(alias).strip().lower()
                hit = mapping.get(key)
                if hit and hit != canon:
                    conflicts.append(f"{table}:{alias}→{hit}/{canon}")
                    continue
                mapping[key] = canon
        per_table_maps[table] = mapping
    return NameNormalizer(per_table_maps, conflicts, str(vocab_path))


class NameNormalizer:
    """实体名 → 规范名（按模式位置给适用词表）。规则：①全名 alias 命中→规范名；
    ②「、」复合名每段都命中→全分解展开；③否则原名。latin 别名大小写不敏感（ss/COD/NOx 均命中）；
    无别名映射的保持原名。"""

    def __init__(self, per_table_maps: dict[str, dict[str, str]], conflicts: list[str], vocab_path: str):
        self._tables = per_table_maps
        self.conflicts = conflicts
        self.vocab_path = vocab_path
        self.normalized_hits = 0
        self.compound_expansions = 0

    def _merged(self, tables: tuple[str, ...]) -> dict[str, str]:
        merged: dict[str, str] = {}
        for t in tables:
            for k, v in self._tables.get(t, {}).items():
                merged.setdefault(k, v)
        return merged

    def expand(self, name: str, tables: tuple[str, ...]) -> list[str]:
        """名字 → 规范名列表（长度 >1 即复合名全分解）。tables = 该模式位置适用的词表。"""
        raw = (name or "").strip()
        mapping = self._merged(tables)
        if not mapping:
            return [raw]
        hit = mapping.get(raw.lower())
        if hit:
            if hit != raw:
                self.normalized_hits += 1
            return [hit]
        parts = [p.strip() for p in raw.split("、")] if "、" in raw else []
        if len(parts) > 1 and all(p.lower() in mapping for p in parts):
            canon: list[str] = []
            for p in parts:
                c = mapping[p.lower()]
                if c not in canon:
                    canon.append(c)
            self.compound_expansions += 1
            return canon
        return [raw]


# ---------------------------------------------------------------- 图装载与拉平


def parse_slug(document_id: str | None) -> str | None:
    """document_id → 报告 slug（与 eia_scope_tag.py 同规则；异形值保留原值不丢信息）。"""
    if not document_id:
        return None
    for prefix in _DOC_PREFIXES:
        if document_id.startswith(prefix):
            return document_id[len(prefix) :]
    return document_id


def _load_graph() -> KernelService:
    async def _run() -> KernelService:
        kernel = KernelService()  # 内存图（不碰持久化 kernel 路径）
        dsn = DatabaseConfig.from_env().url
        stats = await kernel.load_from_sql(dsn=dsn)
        print(f"装载 {stats['entities']} 实体 / {stats['relations']} 关系 / {stats['mentions']} mentions")
        return kernel

    return asyncio.run(_run())


def _collect(kernel: KernelService) -> tuple[dict, dict, dict, dict]:
    """断言图一次性拉平：实体名/etype/scope、出边、mention 文档集."""
    store = kernel.store
    name_of: dict[str, str] = {}
    scope_of: dict[str, str] = {}
    rows = store.query(f'SELECT ?e ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ ?e ?p ?o . FILTER(STRSTARTS(STR(?p), "{_ATTR_NS}") && (?p = <{_ATTR_NS}norm_name> || ?p = <{_ATTR_NS}scope> || ?p = <{_ATTR_NS}source_report>)) }} }}')
    source_report_of: dict[str, str] = {}
    for r in rows:
        p = str(r["p"]).rsplit("#attr/", 1)[-1]
        if p == "norm_name":
            name_of[r["e"]] = r["o"]
        elif p == "scope":
            scope_of[r["e"]] = r["o"]
        elif p == "source_report":
            source_report_of[r["e"]] = r["o"]

    # 类 IRI（eia#TreatmentMeasure）→ etype（treatment_measure）：registry etype_class_map 反转。
    # 图内 rdf:type 存的是 PascalCase 类名，直接取局部名与 snake_case etype 比较会全量失配。
    from app.ontology.kernel.loader import etype_class_map
    from app.ontology.registry import get_registry

    class_to_etype = {cls: et for et, cls in etype_class_map(get_registry(), "eia").items()}
    etype_of: dict[str, str] = {}
    for r in store.query(f'SELECT ?e ?cls WHERE {{ GRAPH <{_ASSERTED}> {{ ?e a ?cls . FILTER(STRSTARTS(STR(?cls), "{_EIA_CLASS_NS}")) }} }}'):
        et = class_to_etype.get(str(r["cls"])[len(_EIA_CLASS_NS) :])
        if et:
            etype_of.setdefault(r["e"], et)

    out_edges: dict[str, list[tuple[str, str]]] = {}
    for r in store.query(f'SELECT DISTINCT ?s ?p ?o WHERE {{ GRAPH <{_ASSERTED}> {{ ?s ?p ?o . FILTER(STRSTARTS(STR(?p), "{_PRED_NS}")) }} }}'):
        pred = str(r["p"])[len(_PRED_NS) :]
        out_edges.setdefault(r["s"], []).append((pred, r["o"]))

    docs_of: dict[str, set[str]] = defaultdict(set)
    for r in store.query(f"SELECT ?e ?d WHERE {{ GRAPH <{_ASSERTED}> {{ ?m <{_KERNEL_NS}mentionOfEntity> ?e ; <{_KERNEL_NS}documentId> ?d }} }}"):
        slug = parse_slug(r.get("d"))
        if slug:
            docs_of[r["e"]].add(slug)

    # 边级溯源：关系节点 (s,pred,o) → 该边被抽取自的文档集（mentionOfRelation）。
    # support 用它（配对级共现支持度）——端点实体各自 mention 覆盖率的并集会虚高
    # （两实体各在 20 份报告出现 ≠ 该配对在 20 份报告共现）。
    edge_docs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in store.query(
        f"SELECT ?s ?p ?o ?d WHERE {{ GRAPH <{_ASSERTED}> {{ ?rel <{_KERNEL_NS}edgeSubject> ?s ; <{_KERNEL_NS}edgePredicate> ?p ; <{_KERNEL_NS}edgeObject> ?o . ?m <{_KERNEL_NS}mentionOfRelation> ?rel ; <{_KERNEL_NS}documentId> ?d }} }}"
    ):
        slug = parse_slug(r.get("d"))
        if slug:
            pred = str(r["p"])[len(_PRED_NS) :] if str(r["p"]).startswith(_PRED_NS) else str(r["p"])
            edge_docs[(r["s"], pred, r["o"])].add(slug)

    return name_of, etype_of, scope_of, {"out": out_edges, "docs": docs_of, "sr": source_report_of, "edge_docs": edge_docs}


def _in_scope_sample(iri: str, scope_of: dict[str, str]) -> bool:
    """有效归属规则：未打标按 sample（与 mcp._scope_filter_sparql 同一缺省规则）。"""
    return scope_of.get(iri, "sample") == "sample"


def _reports_of(iris: list[str], docs_of: dict[str, set[str]], sr_of: dict[str, str]) -> set[str]:
    """沿边实体溯源聚合：mention 文档 slug ∪ attrs.source_report（打标回填，兜无 mention 行）。"""
    out: set[str] = set()
    for iri in iris:
        out |= docs_of.get(iri, set())
        sr = sr_of.get(iri)
        if sr:
            out.add(sr)
    return out


def _etype_majority(iris: list[str], etype_of: dict[str, str]) -> tuple[str | None, bool]:
    """一组实例 IRI 的多数 etype + 是否混型（同名跨 etype 场景提示）。"""
    counter = Counter(etype_of.get(i) for i in iris if etype_of.get(i))
    if not counter:
        return None, False
    return counter.most_common(1)[0][0], len(counter) > 1


def _pattern_id(pattern_type: str, subject_name: str, object_name: str, predicate: str) -> str:
    raw = f"{pattern_type}|{subject_name}|{object_name}|{predicate}"
    return "dp-" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- 聚合（按规范名配对）


def _aggregate(
    pattern_type: str,
    paths: list[tuple],
    name_of: dict[str, str],
    etype_of: dict[str, str],
    docs_of: dict[str, set[str]],
    sr_of: dict[str, str],
) -> list[dict]:
    """paths 元素 = (subject_iri, object_iri, predicate, bridge_iris[], edge_reports:set, s_canon, o_canon)
    → 按**规范名**配对聚合。变体对在同名规范下合并：support=报告集并集（跨报告共现语义），
    occurrence=路径实例数；subject_variants/object_variants 记录变体（名+实际 etype）供入图连边。
    """
    grouped: dict[tuple, dict] = {}
    for subj, obj, pred, bridges, edge_reports, s_canon, o_canon in paths:
        key = (s_canon, o_canon, pred)
        g = grouped.setdefault(key, {"iris": [], "bridges": [], "reports": set(), "s_vars": {}, "o_vars": {}})
        g["iris"] += [subj, obj]
        g["bridges"] += bridges
        g["reports"] |= edge_reports if edge_reports else _reports_of([subj, obj, *bridges], docs_of, sr_of)
        for iri, store in ((subj, g["s_vars"]), (obj, g["o_vars"])):
            nm, et = name_of.get(iri), etype_of.get(iri)
            if nm:
                store[nm] = et

    entries = []
    for (s_name, o_name, pred), g in grouped.items():
        reports = g["reports"]
        s_etype, s_mixed = _etype_majority([i for i in g["iris"][::2]], etype_of)
        o_etype, o_mixed = _etype_majority([i for i in g["iris"][1::2]], etype_of)
        # 处置规律同名不同谓词（disposed_by/utilized_by 语义不同）→ 名字带谓词消歧
        pred_suffix = f"（{pred}）" if pattern_type == "处置" else ""
        pattern_name = f"{pattern_type}规律：{s_name}→{o_name}{pred_suffix}"
        entries.append(
            {
                "pattern_id": _pattern_id(pattern_type, s_name, o_name, pred),
                "pattern_name": pattern_name,
                "pattern_type": pattern_type,
                "subject_name": s_name,
                "subject_etype": s_etype,
                "object_name": o_name,
                "object_etype": o_etype,
                "predicate": pred,
                "occurrence_count": len(g["bridges"]) if pattern_type == "治理" else len(g["iris"]) // 2,
                "support_count": len(reports),
                "source_reports": sorted(reports),
                "pattern_desc": (f"样例库 {len(reports)} 份报告共现：{s_name}（{s_etype}）配 {o_name}（{o_etype}）" + (f"（{pred}）" if pattern_type == "处置" else "") + f"——{pattern_type}规律（B 库蒸馏，跨报告支持度 {len(reports)}）"),
                "mixed_etype": s_mixed or o_mixed,
                "subject_variants": sorted(({"name": n, "etype": et} for n, et in g["s_vars"].items()), key=lambda v: v["name"]),
                "object_variants": sorted(({"name": n, "etype": et} for n, et in g["o_vars"].items()), key=lambda v: v["name"]),
            }
        )
    entries.sort(key=lambda e: (-e["support_count"], -e["occurrence_count"], e["subject_name"]))
    return entries


# ---------------------------------------------------------------- B2 两类链模式挖掘（路径收集，模块级可单测）


def _edge_reports(edge_docs: dict[tuple[str, str, str], set[str]], *triples: tuple[str, str, str]) -> set[str]:
    """边级溯源聚合（_mine 内 edge_reports 闭包的模块级版，B2 函数用；口径同批次 1）。"""
    rep: set[str] = set()
    for t in triples:
        rep |= edge_docs.get(t, set())
    return rep


def _sensitive_protect_paths(
    out_edges: dict[str, list[tuple[str, str]]],
    etype_of: dict[str, str],
    scope_of: dict[str, str],
    name_of: dict[str, str],
    edge_docs: dict[tuple[str, str, str], set[str]],
    normalizer: NameNormalizer | None,
) -> tuple[list[tuple], list[str]]:
    """④ 敏感点防护：SP —protected_by→ 治理措施。subject canonical=类型归组名（单点实例名入变体），
    object 走受控词表位置归一（含「、」复合名展开）。返回 (expand 后 paths, 未归类敏感点名清单)。"""
    paths: list[tuple] = []
    unclassified: list[str] = []
    tables = POSITION_TABLES["敏感点防护"]
    for sp, elist in out_edges.items():
        if etype_of.get(sp) != "sensitive_point" or not _in_scope_sample(sp, scope_of):
            continue
        sp_type = _classify_by_keywords(name_of.get(sp, ""), SENSITIVE_POINT_TYPES)
        if sp_type is None:
            unclassified.append(name_of.get(sp, ""))
            continue
        for p, o in elist:
            if p != "protected_by" or etype_of.get(o) not in _PROTECT_TARGET_ETYPES or not _in_scope_sample(o, scope_of):
                continue
            o_name = name_of.get(o)
            if not o_name:
                continue
            reports = _edge_reports(edge_docs, (sp, p, o))
            o_list = normalizer.expand(o_name, tables["object"]) if normalizer else [o_name]
            for oc in o_list:
                paths.append((sp, o, p, [], reports, sp_type, oc))
    return paths, unclassified


def _monitor_paths(
    out_edges: dict[str, list[tuple[str, str]]],
    etype_of: dict[str, str],
    scope_of: dict[str, str],
    name_of: dict[str, str],
    edge_docs: dict[tuple[str, str, str], set[str]],
    normalizer: NameNormalizer | None,
) -> tuple[list[tuple], list[str]]:
    """⑤ 监测覆盖：矿区/工程场地 —monitored_by→ 监测要求。subject canonical=源类型归组名
    （关键词表 first-match，mine 未命中 etype 兜底矿区整体；engineering_site 未命中跳过）。
    返回 (expand 后 paths, 未归类源名清单)。"""
    paths: list[tuple] = []
    unclassified: list[str] = []
    tables = POSITION_TABLES["监测覆盖"]
    for s, elist in out_edges.items():
        if etype_of.get(s) not in _MONITOR_SOURCE_ETYPES or not _in_scope_sample(s, scope_of):
            continue
        s_name = name_of.get(s, "")
        s_type = _classify_by_keywords(s_name, MONITOR_SOURCE_TYPES) or MONITOR_SOURCE_FALLBACK.get(etype_of.get(s, ""))
        if s_type is None:
            unclassified.append(s_name)
            continue
        for p, o in elist:
            if p != "monitored_by" or etype_of.get(o) != "monitoring" or not _in_scope_sample(o, scope_of):
                continue
            o_name = name_of.get(o)
            if not o_name:
                continue
            reports = _edge_reports(edge_docs, (s, p, o))
            o_list = normalizer.expand(o_name, tables["object"]) if normalizer else [o_name]
            for oc in o_list:
                paths.append((s, o, p, [], reports, s_type, oc))
    return paths, unclassified


# ---------------------------------------------------------------- 五类链模式挖掘


def _mine(kernel: KernelService, normalizer: NameNormalizer | None) -> dict[str, list[dict]]:
    name_of, etype_of, scope_of, edges = _collect(kernel)
    out, docs_of, sr_of, edge_docs = edges["out"], edges["docs"], edges["sr"], edges["edge_docs"]

    def is_ent(iri: str, etype: str) -> bool:
        return etype_of.get(iri) == etype and _in_scope_sample(iri, scope_of)

    def edge_reports(*triples: tuple[str, str, str]) -> set[str]:
        rep: set[str] = set()
        for t in triples:
            rep |= edge_docs.get(t, set())
        return rep

    def expand_paths(raw_paths: list[tuple], tables: dict[str, tuple[str, ...]]) -> list[tuple]:
        """(s,o,pred,bridges,reports) → 笛卡尔展开复合名全分解后的 (…, s_canon, o_canon) 路径。"""
        flat: list[tuple] = []
        for s_iri, o_iri, pred, bridges, reports in raw_paths:
            s_name, o_name = name_of.get(s_iri), name_of.get(o_iri)
            if not s_name or not o_name:
                continue
            s_list = normalizer.expand(s_name, tables["subject"]) if normalizer else [s_name]
            o_list = normalizer.expand(o_name, tables["object"]) if normalizer else [o_name]
            for sc in s_list:
                for oc in o_list:
                    flat.append((s_iri, o_iri, pred, bridges, reports, sc, oc))
        return flat

    # ① 治理规律：X —emitted_as→ P，X —treated_by→ T（X = 污染源/固废流/…，角色表支持域内任意桥）
    treat_paths = []
    for src, elist in out.items():
        pols = [o for p, o in elist if p == "emitted_as" and is_ent(o, "pollutant")]
        tms = [o for p, o in elist if p == "treated_by" and is_ent(o, "treatment_measure")]
        if not (_in_scope_sample(src, scope_of) and pols and tms):
            continue
        for pol in pols:
            for tm in tms:
                treat_paths.append((pol, tm, "emitted_as+treated_by", [src], edge_reports((src, "emitted_as", pol), (src, "treated_by", tm))))
    treat = _aggregate("治理", expand_paths(treat_paths, POSITION_TABLES["治理"]), name_of, etype_of, docs_of, sr_of)

    # ② 标准规律：T —governed_by→ S
    std_paths = [(s, o, "governed_by", [], edge_reports((s, "governed_by", o))) for s, elist in out.items() if is_ent(s, "treatment_measure") for p, o in elist if p == "governed_by" and is_ent(o, "emission_standard")]
    std = _aggregate("标准", expand_paths(std_paths, POSITION_TABLES["标准"]), name_of, etype_of, docs_of, sr_of)

    # ③ 处置规律：W —disposed_by/utilized_by→ G
    disp_paths = []
    for w, elist in out.items():
        if not is_ent(w, "waste_stream"):
            continue
        for p, o in elist:
            if p in ("disposed_by", "utilized_by") and etype_of.get(o) in _DISPOSAL_TARGET_ETYPES and _in_scope_sample(o, scope_of):
                disp_paths.append((w, o, p, [], edge_reports((w, p, o))))
    disp = _aggregate("处置", expand_paths(disp_paths, POSITION_TABLES["处置"]), name_of, etype_of, docs_of, sr_of)

    # ④ 敏感点防护规律（B2）：敏感点 —protected_by→ 治理措施（主体按类型关键词归组，未归类跳过）
    prot_paths, prot_unclassified = _sensitive_protect_paths(out, etype_of, scope_of, name_of, edge_docs, normalizer)
    prot = _aggregate("敏感点防护", prot_paths, name_of, etype_of, docs_of, sr_of)

    # ⑤ 监测覆盖规律（B2）：矿区/工程场地 —monitored_by→ 监测要求（主体按源类型关键词归组 + mine 兜底）
    mon_paths, mon_unclassified = _monitor_paths(out, etype_of, scope_of, name_of, edge_docs, normalizer)
    mon = _aggregate("监测覆盖", mon_paths, name_of, etype_of, docs_of, sr_of)

    if prot_unclassified:
        print(f"[敏感点防护] 未归类敏感点跳过 {len(prot_unclassified)} 个（词表增补候选）：{'、'.join(sorted(set(prot_unclassified)))}")
    if mon_unclassified:
        print(f"[监测覆盖] 未归类源跳过 {len(mon_unclassified)} 个（词表增补候选）：{'、'.join(sorted(set(mon_unclassified)))}")

    return {"治理": treat, "标准": std, "处置": disp, "敏感点防护": prot, "监测覆盖": mon}


# ---------------------------------------------------------------- 落盘


def _write_report(mined: dict[str, list[dict]], duration_ms: float, min_support: int, normalizer: NameNormalizer | None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    candidates = {t: [e for e in entries if e["support_count"] >= min_support] for t, entries in mined.items()}
    payload = {
        "mined_at": now,
        "scope": "真实图断言层（dg_* 全量装载 → 内存 kernel，生产同路径 load；只挖 scope=sample）",
        "support_definition": "support_count=配对级去重报告数（按路径各边的 relation mention.document_id slug 聚合，边缺 relation mention 回退端点实体溯源）；occurrence_count=去重路径实例数",
        "min_support": min_support,
        "normalization": (
            None
            if normalizer is None
            else {
                "vocab": normalizer.vocab_path,
                "alias_conflicts": normalizer.conflicts,
                "normalized_name_hits": normalizer.normalized_hits,
                "compound_expansions": normalizer.compound_expansions,
                "rule": "聚合前按受控词表 aliases 归一到规范名；「、」复合名每段都命中才全分解；support=报告集并集（不 arithmetic 累加）",
            }
        ),
        "counts": {t: {"pairs": len(entries), "candidates": len(candidates[t])} for t, entries in mined.items()},
        "patterns": mined,
    }
    json_path = OUT_DIR / "patterns.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# EIA B 库领域规律挖掘报告（子项目 5 交付 1 · 归并深化版）",
        "",
        f"- 挖掘时间：{now}",
        "- 数据：真实图断言层（dg_* 全量 → 内存 kernel，生产同路径 load）；只挖 scope=sample 实体",
        f"- support 定义：去重报告数（mention 溯源 ∪ attrs.source_report）；入图门槛 ≥{min_support}",
        "- 归并：" + ("关闭（--no-normalize）" if normalizer is None else f"受控词表归一（{normalizer.vocab_path}），名称归一命中 {normalizer.normalized_hits} 次、复合名全分解 {normalizer.compound_expansions} 次"),
        "",
        f"| 类型 | 配对数 | 入图候选（support≥{min_support}） |",
        "|---|---|---|",
    ]
    for t, entries in mined.items():
        lines.append(f"| {t}规律 | {len(entries)} | {len(candidates[t])} |")
    for t, entries in mined.items():
        lines += ["", f"## {t}规律（按 support 降序，Top 20）", "", "| 配对 | 谓词 | support(报告) | occurrence(路径) | 报告 |", "|---|---|---|---|---|"]
        for e in entries[:20]:
            pair = f"{e['subject_name']}（{e['subject_etype']}）→ {e['object_name']}（{e['object_etype']}）"
            reports = "、".join(e["source_reports"][:5]) + ("…" if len(e["source_reports"]) > 5 else "")
            lines.append(f"| {pair} | {e['predicate']} | {e['support_count']} | {e['occurrence_count']} | {reports} |")
    (OUT_DIR / "pattern_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n挖掘耗时 {duration_ms:.0f}ms")
    if normalizer:
        print(f"归一：名称命中 {normalizer.normalized_hits}，复合名全分解 {normalizer.compound_expansions}，alias 冲突 {len(normalizer.conflicts)} {normalizer.conflicts[:3]}")
    for t, entries in mined.items():
        print(f"\n[{t}规律] 配对 {len(entries)}，入图候选 {len(candidates[t])}（support≥{min_support}）")
        for e in entries[:10]:
            print(f"  {e['subject_name']} → {e['object_name']}  support={e['support_count']} occurrence={e['occurrence_count']}")
    print(f"\n落盘: {json_path}\n落盘: {OUT_DIR / 'pattern_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="EIA B 库领域规律挖掘（受控词表归并版，只读）")
    parser.add_argument("--min-support", type=int, default=3, help="入图门槛（跨报告支持度，默认 3；扩量用 2）")
    parser.add_argument("--vocab", type=Path, default=VOCAB_PATH, help="受控词表 yaml 路径")
    parser.add_argument("--no-normalize", action="store_true", help="关闭变体归一（复现归并前基线口径）")
    args = parser.parse_args()

    normalizer = None if args.no_normalize else load_normalizer(args.vocab)
    t0 = time.perf_counter()
    kernel = _load_graph()
    mined = _mine(kernel, normalizer)
    _write_report(mined, (time.perf_counter() - t0) * 1000, args.min_support, normalizer)


if __name__ == "__main__":
    main()
