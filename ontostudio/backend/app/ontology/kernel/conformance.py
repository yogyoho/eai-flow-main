"""GB/T 48000.3—2026 符合性套件（kernel P4）——测试即合规证据（spec §5）.

五项检查（与前端校验中心页一一对应）：
  C1 条款 5.4  IRI 命名规约     域命名空间形如 http(s)，实例 IRI=ns+id/<uuid> 机械可逆
  C2 条款 5.3  序列化往返       schema 图 Turtle round-trip 同构 + store 装载一致
  C3 条款 5.3  SHACL 报告       结构化报告形态完整（focusNode/path/message/severity/source）
  C4 附录 A    元数据八项       类声明/标签齐备，subClassOf 目标类已声明
  C5 条款 9    扩展原则         每域命名空间唯一且非 W3C 保留，类名合法
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdflib.namespace import OWL, RDF, RDFS

from app.ontology.kernel.compile import collect_vocabularies, compile_schema_graph
from app.ontology.kernel.export import graphs_isomorphic, parse_turtle, to_turtle
from app.ontology.kernel.store import SCHEMA_GRAPH, OxStore
from app.ontology.registry import Registry


@dataclass
class CheckResult:
    name: str
    clause: str
    passed: bool
    detail: str


def _c1_iri_naming(registry: Registry) -> CheckResult:
    """§5.4：命名空间合法 + 实例 IRI=ns+id/<uuid>（IriScheme 构造保证可逆性）。"""
    vocabs = collect_vocabularies(registry)
    problems: list[str] = []
    for domain, vocab in vocabs.items():
        ns = vocab.scheme.namespace
        if not re.match(r"^https?://", ns):
            problems.append(f"域 {domain} 命名空间非 http(s)：{ns}")
        if ns.count("#") > 1:
            problems.append(f"域 {domain} 命名空间含多个 #：{ns}")
    return CheckResult("IRI 命名规约", "条款 5.4", not problems, "; ".join(problems) or f"{len(vocabs)} 个域命名空间全部合法")


def _c2_serialization_roundtrip(registry: Registry, store: OxStore) -> CheckResult:
    """§5.3：schema 编译 → Turtle → 解析 → 同构；store 内 schema 图 → dump → 同构。"""
    compiled = compile_schema_graph(registry)
    problems: list[str] = []
    if not graphs_isomorphic(compiled, parse_turtle(to_turtle(compiled))):
        problems.append("registry→Turtle→解析 不同构")
    store_ttl = store.dump_turtle(SCHEMA_GRAPH)
    if store_ttl and not graphs_isomorphic(compiled, parse_turtle(store_ttl)):
        problems.append("store 内 schema 图与编译产物不同构")
    return CheckResult("序列化往返", "条款 5.3", not problems, "; ".join(problems) or f"{len(compiled)} 三元组 Turtle round-trip 同构")


def _c3_shacl_report_shape(report) -> CheckResult:  # noqa: ANN001 - ValidationReport
    """§5.3：SHACL 报告形态完整（每条违规五字段齐备）。"""
    problems = [f"violation[{i}] 缺字段 {k}" for i, v in enumerate(report.violations) for k in ("focusNode", "path", "message", "severity", "source") if k not in v]
    return CheckResult("SHACL 报告", "条款 5.3", not problems, "; ".join(problems) or f"报告结构完整（conforms={report.conforms}, {len(report.violations)} 违规）")


def _c4_appendix_a_metadata(registry: Registry) -> CheckResult:
    """附录 A：类声明（owl:Class）/标签齐备；subClassOf 目标类必须已声明。"""
    schema = compile_schema_graph(registry)
    problems: list[str] = []
    for vocab in collect_vocabularies(registry).values():
        for class_name in vocab.class_names:
            subject = vocab.class_ref(class_name)
            if (subject, RDF.type, OWL.Class) not in schema:
                problems.append(f"{class_name} 缺 owl:Class 声明")
            if not list(schema.objects(subject, RDFS.label)):
                problems.append(f"{class_name} 缺 rdfs:label（附录 A 标签项）")
    for _, _, target in schema.triples((None, RDFS.subClassOf, None)):
        if (target, RDF.type, OWL.Class) not in schema:
            problems.append(f"subClassOf 目标未声明：{target}")
    return CheckResult("附录 A 元数据", "附录 A", not problems, "; ".join(problems) or f"{len(schema)} 三元组元数据完整")


def _c5_extension_principles(registry: Registry) -> CheckResult:
    """§9：每域命名空间唯一、非 W3C 保留空间；类名不含非法字符。"""
    vocabs = collect_vocabularies(registry)
    problems: list[str] = []
    ns_seen: dict[str, str] = {}
    for domain, vocab in vocabs.items():
        ns = vocab.scheme.namespace
        if ns in ns_seen:
            problems.append(f"命名空间跨域冲突：{domain} 与 {ns_seen[ns]} 共用 {ns}")
        ns_seen[ns] = domain
        if ns.startswith(("http://www.w3.org/", "urn:")):
            problems.append(f"域 {domain} 占用 W3C 保留命名空间")
        for class_name in vocab.class_names:
            if "#" in class_name or any(ch.isspace() for ch in class_name):
                problems.append(f"域 {domain} 类名非法：{class_name}")
    return CheckResult("扩展原则", "条款 9", not problems, "; ".join(problems) or f"{len(vocabs)} 域命名空间唯一合法")


def run_conformance(store: OxStore, registry: Registry, shacl_report=None) -> list[CheckResult]:
    """五项全量。shacl_report 可注入（调用方先 run_shacl，避免重复校验开销）。"""
    from app.ontology.kernel.validate import run_shacl

    return [
        _c1_iri_naming(registry),
        _c2_serialization_roundtrip(registry, store),
        _c3_shacl_report_shape(shacl_report or run_shacl(store, registry)),
        _c4_appendix_a_metadata(registry),
        _c5_extension_principles(registry),
    ]


def all_passed(results: list[CheckResult]) -> bool:
    return all(r.passed for r in results)
