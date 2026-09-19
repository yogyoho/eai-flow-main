"""OWL 2 RL 闭包推理（kernel P3）——graph:entailment 物化.

推理空间 = graph:schema（本体公理）∪ graph:asserted（置信度 ≥ 门限的业务断言）
∪ graph:alignment（sameAs 候选覆盖层，spec §3）。
owlrl 在内存 rdflib 图上展开闭包；物化 = 闭包 − 输入，写入 graph:entailment。
低置信度实体（< 门限）的三元组不入推理空间。
失败降级：owlrl 异常时保留旧物化并记录 errors，绝不阻塞读路径（spec §4）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import owlrl
from pyoxigraph import BlankNode, NamedNode, Quad
from pyoxigraph import Literal as OxLiteral
from rdflib import BNode, Graph, Literal, URIRef

from app.ontology.kernel.compile import compile_schema_graph
from app.ontology.kernel.store import (
    ALIGNMENT_GRAPH,
    ASSERTED_GRAPH,
    ENTAILMENT_GRAPH,
    SCHEMA_GRAPH,
    OxStore,
)
from app.ontology.kernel.vocab import P_CONFIDENCE
from app.ontology.registry import Registry

REASONING_GRAPHS = (SCHEMA_GRAPH, ASSERTED_GRAPH, ALIGNMENT_GRAPH)


@dataclass
class InferStats:
    input_triples: int = 0
    filtered_low_confidence: int = 0
    entailment_triples: int = 0
    duration_ms: int = 0
    rule_counts: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _term_to_rdflib(term) -> URIRef | BNode | Literal:  # noqa: ANN001 - pyoxigraph Term
    if isinstance(term, NamedNode):
        return URIRef(term.value)
    if isinstance(term, BlankNode):
        return BNode(term.value)
    if isinstance(term, OxLiteral):
        # RDF 1.1：带语言的字面量 datatype 恒为 rdf:langString——rdflib 只接受 lang 单独传
        if term.language is not None:
            return Literal(term.value, lang=term.language)
        datatype = URIRef(term.datatype.value) if term.datatype is not None else None
        return Literal(term.value, datatype=datatype)
    raise TypeError(f"未知 pyoxigraph term 类型: {type(term).__name__}")  # pragma: no cover


def _triple_to_quad(s, p, o, graph_name: str = ENTAILMENT_GRAPH) -> Quad:  # noqa: ANN001 - rdflib terms
    def conv(term):  # noqa: ANN001
        if isinstance(term, URIRef):
            return NamedNode(str(term))
        if isinstance(term, BNode):
            return BlankNode(str(term))
        if term.datatype is not None:
            return OxLiteral(str(term), datatype=NamedNode(str(term.datatype)))
        if term.language is not None:
            return OxLiteral(str(term), language=term.language)
        return OxLiteral(str(term))

    return Quad(conv(s), conv(p), conv(o), NamedNode(graph_name))


def low_confidence_entities(store: OxStore, threshold: float) -> set[str]:
    """置信度 < 门限的实体 IRI 集合（字符串拼接建查询，规避 f-string 花括号）。

    confidence 以普通字面量存储（P2 契约），比较前显式 xsd:double 转型。
    """
    query = "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>SELECT ?e WHERE { GRAPH <" + ASSERTED_GRAPH + "> { ?e <" + P_CONFIDENCE + "> ?c } FILTER(xsd:double(?c) < " + repr(float(threshold)) + ") }"
    return {row["e"] for row in store.query(query) if row.get("e")}


def build_inference_graph(store: OxStore, *, min_confidence: float = 0.7) -> tuple[Graph, int]:
    """推理空间 → 内存 rdflib 图；返回 (图, 被门限过滤掉的三元组数)。"""
    low = low_confidence_entities(store, min_confidence)
    graph = Graph()
    filtered = 0
    for quad in store._store.quads_for_pattern(None, None, None, None):
        graph_name = quad.graph_name.value
        if graph_name not in REASONING_GRAPHS:
            continue
        # 字面量不入推理空间：分类/链/传递全在 IRI 结构上，字面量（标签/数值）只会
        # 拖慢 owlrl（实测 5k 场景 ~2x）；SHACL 校验路径仍读完整断言图
        if isinstance(quad.object, OxLiteral):
            continue
        if graph_name == ASSERTED_GRAPH and low:
            subject_iri = quad.subject.value if isinstance(quad.subject, NamedNode) else None
            object_iri = quad.object.value if isinstance(quad.object, NamedNode) else None
            if (subject_iri and subject_iri in low) or (object_iri and object_iri in low):
                filtered += 1
                continue
        graph.add((_term_to_rdflib(quad.subject), _term_to_rdflib(quad.predicate), _term_to_rdflib(quad.object)))
    return graph, filtered


def compute_entailment(store: OxStore, *, min_confidence: float = 0.7) -> InferStats:
    """全量重算 graph:entailment（清空重写；owlrl 失败 → 保留旧物化并记 errors）。"""
    stats = InferStats()
    started = time.perf_counter()
    input_graph, filtered = build_inference_graph(store, min_confidence=min_confidence)
    stats.input_triples = len(input_graph)
    stats.filtered_low_confidence = filtered

    input_snapshot = set(input_graph)  # expand 原地变换 → 先快照输入，物化 = 闭包 − 输入
    try:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(input_graph)
    except Exception as e:  # noqa: BLE001 - 推理器任何异常都降级
        stats.errors.append(f"owlrl 展开失败（保留旧物化）: {e}")
        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    entailment = [t for t in input_graph if t not in input_snapshot]
    store.clear_graph(ENTAILMENT_GRAPH)
    skipped = 0
    for s, p, o in entailment:
        # RDF 合法性守卫：owlrl 字面量推理可能产生 Literal 主体的"三元组"（非合法 RDF），跳过
        if isinstance(s, Literal) or not isinstance(p, URIRef):
            skipped += 1
            continue
        store._store.add(_triple_to_quad(s, p, o))
    stats.entailment_triples = len(entailment) - skipped
    stats.duration_ms = int((time.perf_counter() - started) * 1000)
    return stats


def refresh_schema(store: OxStore, registry: Registry) -> None:
    """registry 重编 → graph:schema 清空重载（SHA 变化时调用）。"""
    store.clear_graph(SCHEMA_GRAPH)
    for s, p, o in compile_schema_graph(registry):
        store._store.add(_triple_to_quad(s, p, o, SCHEMA_GRAPH))
