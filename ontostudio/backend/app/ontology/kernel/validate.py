"""SHACL 约束校验（kernel P4）——写路径闭世界校验 + 结构化报告.

- shapes 编译：registry → NodeShapes（每 etype 类：status 枚举/norm_name 必填）+
  kernel 固定形状（Mention 实体/关系指向二选一 sh:xone / MergeAudit 字段完备）。
- 数据图 = graph:asserted（SHACL 管写路径，闭世界；对齐 OWL 开世界推理层，spec §4）。
- 报告：conforms + violations（focusNode/path/message/severity/source）——
  国标 §5.3"SHACL 约束验证（结构化输出）"的原生满足面。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pyshacl import validate
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.kernel.vocab import (
    C_MENTION,
    C_MERGE_AUDIT,
    P_AUDIT_REVERSED,
    P_AUDIT_SOURCE,
    P_AUDIT_TARGET,
    P_MENTION_OF_ENTITY,
    P_MENTION_OF_RELATION,
    P_STATUS,
)
from app.ontology.registry import Registry

SH = "http://www.w3.org/ns/shacl#"


@dataclass
class ValidationReport:
    conforms: bool
    violations: list[dict] = field(default_factory=list)
    duration_ms: int = 0


def _p(g: Graph, s, predicate: str, o) -> None:
    g.add((s, URIRef(SH + predicate), o))


def _severity(g: Graph, ps: BNode, message: str) -> None:
    _p(g, ps, "message", Literal(message, lang="zh"))
    _p(g, ps, "severity", URIRef(SH + "Violation"))


def _status_shape(g: Graph, node_shape: BNode) -> None:
    ps = BNode()
    _p(g, node_shape, "property", ps)
    _p(g, ps, "path", URIRef(P_STATUS))
    head = BNode()
    Collection(g, head, [Literal(v) for v in ("active", "pending_review", "merged")])
    _p(g, ps, "in", head)
    _p(g, ps, "maxCount", Literal(1))
    _severity(g, ps, "status 必须是 active/pending_review/merged 之一")


def _min_count(g: Graph, node_shape: BNode, path: str, count: int, message: str) -> None:
    ps = BNode()
    _p(g, node_shape, "property", ps)
    _p(g, ps, "path", URIRef(path))
    _p(g, ps, "minCount", Literal(count))
    _severity(g, ps, message)


def compile_shapes(registry: Registry) -> Graph:
    """registry → SHACL shapes 图（词表合法性由 compile 层 fail-closed 保证）。"""
    shapes = Graph()
    shapes.bind("sh", SH)

    # 每 etype 类：status 枚举 + norm_name 必填
    for vocab in collect_vocabularies(registry).values():
        for class_name in sorted(vocab.class_names):
            node_shape = BNode()
            shapes.add((node_shape, RDF.type, URIRef(SH + "NodeShape")))
            _p(shapes, node_shape, "targetClass", vocab.class_ref(class_name))
            _status_shape(shapes, node_shape)
            _min_count(shapes, node_shape, f"{vocab.scheme.namespace}attr/norm_name", 1, f"{class_name} 规范化名必填")

    # Mention：实体/关系指向二选一（sh:xone 两个备选 NodeShape）
    mention = BNode()
    shapes.add((mention, RDF.type, URIRef(SH + "NodeShape")))
    _p(shapes, mention, "targetClass", URIRef(C_MENTION))
    alt_entity, alt_relation = BNode(), BNode()
    xone_head = BNode()
    Collection(shapes, xone_head, [alt_entity, alt_relation])
    _p(shapes, mention, "xone", xone_head)
    _min_count(shapes, alt_entity, P_MENTION_OF_ENTITY, 1, "证据必须指向实体")
    _min_count(shapes, alt_relation, P_MENTION_OF_RELATION, 1, "证据必须指向关系")

    # MergeAudit：source/target 完备 + reversed ∈ {true,false}
    audit = BNode()
    shapes.add((audit, RDF.type, URIRef(SH + "NodeShape")))
    _p(shapes, audit, "targetClass", URIRef(C_MERGE_AUDIT))
    _min_count(shapes, audit, P_AUDIT_SOURCE, 1, "审计必须记录 source")
    _min_count(shapes, audit, P_AUDIT_TARGET, 1, "审计必须记录 target")
    ps = BNode()
    _p(shapes, audit, "property", ps)
    _p(shapes, ps, "path", URIRef(P_AUDIT_REVERSED))
    values_head = BNode()
    Collection(shapes, values_head, [Literal("true"), Literal("false")])
    _p(shapes, ps, "in", values_head)
    _severity(shapes, ps, "auditReversed 必须是 true/false")

    return shapes


def _to_rdflib_term(term):  # noqa: ANN001 - pyoxigraph Term → rdflib
    if isinstance(term, BNode):
        return BNode(term.value)
    if type(term).__name__ == "NamedNode":
        return URIRef(term.value)
    return Literal(term.value)


def _asserted_graph(store: OxStore) -> Graph:
    data = Graph()
    for quad in store._store.quads_for_pattern(None, None, None, None):
        if quad.graph_name.value != ASSERTED_GRAPH:
            continue
        data.add((_to_rdflib_term(quad.subject), _to_rdflib_term(quad.predicate), _to_rdflib_term(quad.object)))
    return data


def _one(graph: Graph, subject, predicate: str) -> str | None:  # noqa: ANN001
    for value in graph.objects(subject, URIRef(predicate)):
        return str(value)
    return None


def run_shacl(store: OxStore, registry: Registry) -> ValidationReport:
    """断言图 vs shapes；结构化报告（国标 §5.3 形态）。"""
    started = time.perf_counter()
    conforms, results_graph, _ = validate(
        _asserted_graph(store),
        shacl_graph=compile_shapes(registry),  # pyshacl 0.40 参数名：shacl_graph（shapes_graph 会被静默吞掉）
        inference="none",
        advanced=True,
    )
    violations: list[dict] = []
    vr = URIRef(SH + "ValidationResult")
    for result in results_graph.subjects(RDF.type, vr):
        violations.append(
            {
                "focusNode": _one(results_graph, result, SH + "focusNode"),
                "path": _one(results_graph, result, SH + "resultPath"),
                "message": _one(results_graph, result, SH + "resultMessage"),
                "severity": _one(results_graph, result, SH + "resultSeverity"),
                "source": _one(results_graph, result, SH + "sourceConstraintComponent"),
            }
        )
    return ValidationReport(
        conforms=bool(conforms),
        violations=violations,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
