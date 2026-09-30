#!/usr/bin/env python3
"""EIA B 库领域规律挖掘（ontostudio 子项目 5 交付 1）——真实图三类高频组合统计.

EAI-CUSTOM(2026-09-30, 子项目 5): 只读脚本，不写库、不碰容器。

用法（宿主机本地，与 eia_rules_baseline.py 同通道）:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_mine.py

流程 = 生产同路径：dg_* 三表 → KernelService.load_from_sql（内存图）→ 断言图三类链模式
挖掘 → 频次聚合 → 落盘 JSON + Markdown 到 scripts/eia_pattern_mine_out/。

三类组合（support 阈值见 MIN_SUPPORT）：
  ① 治理规律  X —emitted_as→ 污染物 P，X —treated_by→ 治理措施 T   （什么污染物配什么工艺）
  ② 标准规律  治理措施 T —governed_by→ 排放标准 S                 （什么工艺配什么标准）
  ③ 处置规律  固废流 W —disposed_by/utilized_by→ 处置去向 G       （什么固废去什么处置）

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

import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DatabaseConfig  # noqa: E402
from app.ontology.kernel.service import KernelService  # noqa: E402

OUT_DIR = Path(__file__).parent / "eia_pattern_mine_out"
MIN_SUPPORT = 3  # 入图门槛（跨报告支持度）

_PRED_NS = "https://ontology.eai-flow.com/eia#predicate/"
_ATTR_NS = "https://ontology.eai-flow.com/eia#attr/"
_EIA_CLASS_NS = "https://ontology.eai-flow.com/eia#"
_KERNEL_NS = "https://ontology.eai-flow.com/kernel#"
_ASSERTED = "graph:asserted"

_DOC_PREFIXES = ("eia-batch:", "eia-sample:")

# 处置/利用去向的目标 etype 白名单（谓词角色表 2026-09-29 R2 支持域）
_DISPOSAL_TARGET_ETYPES = ("treatment_measure", "org", "engineering_site", "place", "measure_process_concept")


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


def _aggregate(
    pattern_type: str,
    paths: list[tuple],
    name_of: dict[str, str],
    etype_of: dict[str, str],
    docs_of: dict[str, set[str]],
    sr_of: dict[str, str],
) -> list[dict]:
    """paths 元素 = (subject_iri, object_iri, predicate, bridge_iris[], edge_reports:set) → 按配对聚合。

    edge_reports = 构成该路径的各边的 mention 文档集并集——配对级共现溯源；
    空集（边无 relation mention 的历史行）回退端点实体溯源（mention ∪ attrs.source_report）。
    """
    grouped: dict[tuple, dict] = {}
    for subj, obj, pred, bridges, edge_reports in paths:
        s_name, o_name = name_of.get(subj), name_of.get(obj)
        if not s_name or not o_name:
            continue
        key = (s_name, o_name, pred)
        g = grouped.setdefault(key, {"iris": [], "bridges": [], "reports": set()})
        g["iris"] += [subj, obj]
        g["bridges"] += bridges
        g["reports"] |= edge_reports if edge_reports else _reports_of([subj, obj, *bridges], docs_of, sr_of)

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
            }
        )
    entries.sort(key=lambda e: (-e["support_count"], -e["occurrence_count"], e["subject_name"]))
    return entries


def _mine(kernel: KernelService) -> dict[str, list[dict]]:
    name_of, etype_of, scope_of, edges = _collect(kernel)
    out, docs_of, sr_of, edge_docs = edges["out"], edges["docs"], edges["sr"], edges["edge_docs"]

    def is_ent(iri: str, etype: str) -> bool:
        return etype_of.get(iri) == etype and _in_scope_sample(iri, scope_of)

    def edge_reports(*triples: tuple[str, str, str]) -> set[str]:
        rep: set[str] = set()
        for t in triples:
            rep |= edge_docs.get(t, set())
        return rep

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
    treat = _aggregate("治理", treat_paths, name_of, etype_of, docs_of, sr_of)

    # ② 标准规律：T —governed_by→ S
    std_paths = [(s, o, "governed_by", [], edge_reports((s, "governed_by", o))) for s, elist in out.items() if is_ent(s, "treatment_measure") for p, o in elist if p == "governed_by" and is_ent(o, "emission_standard")]
    std = _aggregate("标准", std_paths, name_of, etype_of, docs_of, sr_of)

    # ③ 处置规律：W —disposed_by/utilized_by→ G
    disp_paths = []
    for w, elist in out.items():
        if not is_ent(w, "waste_stream"):
            continue
        for p, o in elist:
            if p in ("disposed_by", "utilized_by") and etype_of.get(o) in _DISPOSAL_TARGET_ETYPES and _in_scope_sample(o, scope_of):
                disp_paths.append((w, o, p, [], edge_reports((w, p, o))))
    disp = _aggregate("处置", disp_paths, name_of, etype_of, docs_of, sr_of)

    return {"治理": treat, "标准": std, "处置": disp}


def _write_report(mined: dict[str, list[dict]], duration_ms: float) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    candidates = {t: [e for e in entries if e["support_count"] >= MIN_SUPPORT] for t, entries in mined.items()}
    payload = {
        "mined_at": now,
        "scope": "真实图断言层（dg_* 全量装载 → 内存 kernel，生产同路径 load；只挖 scope=sample）",
        "support_definition": "support_count=配对级去重报告数（按路径各边的 relation mention.document_id slug 聚合，边缺 relation mention 回退端点实体溯源）；occurrence_count=去重路径实例数",
        "min_support": MIN_SUPPORT,
        "counts": {t: {"pairs": len(entries), "candidates": len(candidates[t])} for t, entries in mined.items()},
        "patterns": mined,
    }
    json_path = OUT_DIR / "patterns.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# EIA B 库领域规律挖掘报告（子项目 5 交付 1）",
        "",
        f"- 挖掘时间：{now}",
        "- 数据：真实图断言层（dg_* 全量 → 内存 kernel，生产同路径 load）；只挖 scope=sample 实体",
        f"- support 定义：去重报告数（mention 溯源 ∪ attrs.source_report）；入图门槛 ≥{MIN_SUPPORT}",
        "",
        f"| 类型 | 配对数 | 入图候选（support≥{MIN_SUPPORT}） |",
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
    for t, entries in mined.items():
        print(f"\n[{t}规律] 配对 {len(entries)}，入图候选 {len(candidates[t])}（support≥{MIN_SUPPORT}）")
        for e in entries[:10]:
            print(f"  {e['subject_name']} → {e['object_name']}  support={e['support_count']} occurrence={e['occurrence_count']}")
    print(f"\n落盘: {json_path}\n落盘: {OUT_DIR / 'pattern_report.md'}")


def main() -> None:
    t0 = time.perf_counter()
    kernel = _load_graph()
    mined = _mine(kernel)
    _write_report(mined, (time.perf_counter() - t0) * 1000)


if __name__ == "__main__":
    main()
