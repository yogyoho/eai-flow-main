"""kernel 服务门面（P5）——REST/MCP 统一入口.

进程内单例：OxStore（ONTOSTUDIO_KERNEL_PATH 持久化，缺省内存）+ registry 热重载 +
规则集（YAML + 内置链规则 + sameAs 传播）。
refresh() 编排：schema 重编 → owlrl 闭包 → CONSTRUCT 派生（防抖由调用方负责）。
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict

from app.ontology.kernel.infer import InferStats, compute_entailment, refresh_schema
from app.ontology.kernel.loader import load_doc_graph_rows
from app.ontology.kernel.rules import (
    BUILTIN_SAMEAS_PROPAGATION,
    builtin_chain_rules,
    load_rules,
    run_all_rules,
)
from app.ontology.kernel.store import OxStore
from app.ontology.registry import get_registry


class KernelService:
    def __init__(self) -> None:
        path = os.environ.get("ONTOSTUDIO_KERNEL_PATH")
        self.store = OxStore(path) if path else OxStore()

    def refresh(self, min_confidence: float = 0.7) -> InferStats:
        """schema 重编 → 闭包 → 派生全量重算。"""
        registry = get_registry()
        refresh_schema(self.store, registry)
        stats = compute_entailment(self.store, min_confidence=min_confidence)
        rules = load_rules() + builtin_chain_rules(registry) + [BUILTIN_SAMEAS_PROPAGATION]
        stats.rule_counts = run_all_rules(self.store, rules)
        return stats

    def validate(self) -> dict:
        """SHACL 报告 + 国标五项符合性（校验中心页数据源）。"""
        from app.ontology.kernel.conformance import run_conformance
        from app.ontology.kernel.validate import run_shacl

        registry = get_registry()
        report = run_shacl(self.store, registry)
        conformance = run_conformance(self.store, registry, shacl_report=report)
        return {
            "shacl": {"conforms": report.conforms, "violations": report.violations, "duration_ms": report.duration_ms},
            "conformance": [asdict(c) for c in conformance],
        }

    def export(self, fmt: str = "turtle", graphs: str = "all") -> str | dict:
        """图真源 → 标准序列化（国标 §5.3 交付物）。graphs: all|schema|asserted|entailment。"""

        from rdflib import Graph

        from app.ontology.kernel.export import to_jsonld, to_turtle

        wanted = {"graph:schema", "graph:asserted", "graph:entailment"} if graphs == "all" else {graphs}
        g = Graph()
        for quad in self.store._store.quads_for_pattern(None, None, None, None):
            if quad.graph_name.value in wanted:
                g.add(_rdflib_triple(quad))
        if fmt == "json-ld":
            return to_jsonld(g)
        return to_turtle(g)

    def load_from_sql(self, dsn: str | None = None, domain: str | None = None) -> dict:
        """SQL 测试数据装载（兼任主系统桥接器）。"""
        from app.config import DatabaseConfig
        from app.ontology.kernel.loader import read_doc_graph_rows

        dsn = dsn or DatabaseConfig.from_env().sync_url
        entity_rows, relation_rows, mention_rows = read_doc_graph_rows(dsn)
        stats = load_doc_graph_rows(
            self.store,
            get_registry(),
            entity_rows=entity_rows,
            relation_rows=relation_rows,
            mention_rows=mention_rows,
            domain=domain,
        )
        return asdict(stats)


def _rdflib_triple(quad) -> tuple:  # noqa: ANN001
    from pyoxigraph import BlankNode, NamedNode
    from pyoxigraph import Literal as OxLiteral
    from rdflib import BNode, Literal, URIRef

    def conv(term):  # noqa: ANN001
        if isinstance(term, NamedNode):
            return URIRef(term.value)
        if isinstance(term, BlankNode):
            return BNode(term.value)
        if isinstance(term, OxLiteral):
            if term.language is not None:
                return Literal(term.value, lang=term.language)
            datatype = URIRef(term.datatype.value) if term.datatype is not None else None
            return Literal(term.value, datatype=datatype)
        return Literal(term.value)

    return conv(quad.subject), conv(quad.predicate), conv(quad.object)


_kernel: KernelService | None = None
_lock = threading.Lock()


def get_kernel() -> KernelService:
    global _kernel
    with _lock:
        if _kernel is None:
            _kernel = KernelService()
        return _kernel
