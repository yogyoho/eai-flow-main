"""kernel 服务门面（P5）——REST/MCP 统一入口.

进程内单例：OxStore（ONTOSTUDIO_KERNEL_PATH 持久化，缺省内存）+ registry 热重载 +
规则集（YAML + 内置链规则 + sameAs 传播）。
refresh() 编排：schema 重编 → owlrl 闭包 → CONSTRUCT 派生（防抖由调用方负责）。
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import asdict

from app.ontology.kernel.cq import load_cqs, run_cqs
from app.ontology.kernel.infer import InferStats, compute_entailment, refresh_schema
from app.ontology.kernel.loader import load_doc_graph_rows
from app.ontology.kernel.rules import (
    BUILTIN_SAMEAS_PROPAGATION,
    builtin_chain_rules,
    load_rules,
    run_all_rules,
)
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.registry import get_registry

# 合法 IRI（防注入：溯源端点把 s/p/o 直接拼进 SPARQL 尖括号字面量）
_IRI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s<>\"{}|^`\\]*$")


class KernelService:
    def __init__(self) -> None:
        path = os.environ.get("ONTOSTUDIO_KERNEL_PATH")
        self.store = OxStore(path) if path else OxStore()

    def refresh(self, min_confidence: float = 0.7) -> InferStats:
        """schema 重编 → 闭包 → 派生全量重算。"""
        registry = get_registry()
        refresh_schema(self.store, registry)
        stats = compute_entailment(self.store, min_confidence=min_confidence)
        stats.rule_counts = run_all_rules(self.store, self._all_rules(registry))
        return stats

    def _all_rules(self, registry) -> list:  # noqa: ANN001 - Registry
        """规则全集 = YAML + registry 链生成 + 内置 sameAs（refresh 与溯源共用）。"""
        return load_rules() + builtin_chain_rules(registry) + [BUILTIN_SAMEAS_PROPAGATION]

    def load_ontology(self, payload: dict, domain: str = "eia") -> dict:
        """四类目标抽取结果（extract_ontology 输出形态）写入断言图.

        entities: [{etype, name, attrs?, confidence?}]；relations: [{predicate, subject, object}]；
        可选 chapters 树 + report_name（① 章节结构实体化）。实体 uuid = uuid5 确定性，重复装载幂等。
        """
        import uuid as uuid_mod

        from app.ontology.kernel.compile import collect_vocabularies
        from app.ontology.kernel.graph_ops import add_relation, upsert_entity
        from app.ontology.kernel.loader import etype_class_map

        registry = get_registry()
        vocab = collect_vocabularies(registry)[domain]
        classes = etype_class_map(registry, domain)

        name_iri: dict[str, str] = {}
        entities = list(payload.get("entities", []))
        chapter_rels: list[dict] = []
        report_name = payload.get("report_name")
        if report_name:
            report_iri = upsert_entity(
                self.store,
                vocab,
                class_name="Report",
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-report:" + report_name),
                etype="report",
                canonical_name=report_name,
                confidence=0.95,
            )
            name_iri[report_name] = report_iri
        for ch in payload.get("chapters", []):
            ch_name = ("第" + str(ch.get("no", "")) + "章 " + str(ch.get("title", ""))).strip()
            ch_iri = upsert_entity(
                self.store,
                vocab,
                class_name="Chapter",
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-chapter:" + ch_name),
                etype="chapter",
                canonical_name=ch_name,
                confidence=0.9,
            )
            name_iri[ch_name] = ch_iri
            entities.append({"etype": "chapter", "name": ch_name})
            if report_name:
                chapter_rels.append({"predicate": "has_chapter", "subject": report_name, "object": ch_name})
            for sec in ch.get("sections", []):
                sec_name = (str(sec.get("no", "")) + " " + str(sec.get("title", ""))).strip()
                sec_iri = upsert_entity(
                    self.store,
                    vocab,
                    class_name="Section",
                    entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia-section:" + sec_name),
                    etype="section",
                    canonical_name=sec_name,
                    confidence=0.9,
                )
                name_iri[sec_name] = sec_iri
                entities.append({"etype": "section", "name": sec_name})
                chapter_rels.append({"predicate": "has_subsection", "subject": ch_name, "object": sec_name})

        inserted = 0
        for e in entities:
            etype = e["etype"]
            if etype not in classes:
                continue
            iri = upsert_entity(
                self.store,
                vocab,
                class_name=classes[etype],
                entity_uuid=uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, "eia:" + etype + ":" + e["name"]),
                etype=etype,
                canonical_name=e["name"],
                confidence=float(e.get("confidence", 0.85)),
                attrs=e.get("attrs"),
            )
            name_iri[e["name"]] = iri
            inserted += 1

        relations = list(payload.get("relations", [])) + chapter_rels
        rel_count = 0
        skipped: list[str] = []
        for r in relations:
            s_iri = name_iri.get(r["subject"])
            o_iri = name_iri.get(r["object"])
            if not s_iri or not o_iri:
                skipped.append(str(r["subject"]) + "->" + str(r["object"]))
                continue
            try:
                add_relation(
                    self.store,
                    vocab,
                    relation_uuid=uuid_mod.uuid4(),
                    subject_iri=s_iri,
                    predicate=r["predicate"],
                    object_iri=o_iri,
                    confidence=float(r.get("confidence", 0.8)),
                )
                rel_count += 1
            except Exception:  # noqa: BLE001 - 单行弹性（谓词越域等历史数据）
                skipped.append(str(r["subject"]) + "->" + str(r["object"]))
        return {"entities": inserted, "relations": rel_count, "skipped": skipped}

    def run_cqs(self) -> list[dict]:
        """CQ 验收（F5）：cq.yaml 逐条 ASK 真跑，FAIL 不阻断（推理工作台页数据源）。"""
        return run_cqs(self.store, load_cqs())

    def rule_derivations(self, name: str, *, limit: int = 200, offset: int = 0) -> dict:
        """graph:derived:<name> 内容（F2 下钻）：派生三元组分页 + 总数。"""
        import re

        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("规则名不合法")
        graph = f"graph:derived:{name}"
        total_rows = self.store.query(
            f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"
        )
        total = int(total_rows[0]["n"] or 0) if total_rows else 0
        rows = self.store.query(
            f"SELECT ?s ?p ?o WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }} "
            f"ORDER BY ?s ?p ?o LIMIT {int(limit)} OFFSET {int(offset)}"
        )
        return {"total": total, "rows": rows}

    def rule_trace(self, name: str, s: str, p: str, o: str) -> dict:
        """F3 溯源：派生三元组 (s, p, o) 的触发基础事实。

        分派：链规则（trace=谓词 IRI 序列）→ 逐段路径查询；qualified_bidder →
        资质满足清单；sameas_propagation → sameAs 链接 + 规范实体事实。
        """
        for iri in (s, p, o):
            if not _IRI_RE.match(iri):
                raise ValueError(f"IRI 不合法: {iri[:60]}")
        rule = next((r for r in self._all_rules(get_registry()) if r.name == name), None)
        if rule is None:
            raise KeyError(name)
        if name == "qualified_bidder":
            return self._trace_requirements(s, o)
        if name == "sameas_propagation":
            return self._trace_sameas(s, p, o)
        trace = rule.trace
        if not trace or len(trace) < 2:
            raise ValueError("该规则未定义溯源链（trace）")
        mids = [f"m{i}" for i in range(len(trace) - 1)]
        patterns = ["<" + s + "> <" + trace[0] + "> ?" + mids[0]]
        for i in range(1, len(trace) - 1):
            patterns.append("?" + mids[i - 1] + " <" + trace[i] + "> ?" + mids[i])
        patterns.append("?" + mids[-1] + " <" + trace[-1] + "> <" + o + ">")
        rows = self.store.query(
            "SELECT " + " ".join("?" + m for m in mids)
            + " WHERE { GRAPH <" + ASSERTED_GRAPH + "> { " + " . ".join(patterns) + " } }"
        )
        evidence: list[dict] = []
        for row in rows:
            nodes = [s] + [row[m] for m in mids] + [o]
            for i, pred in enumerate(trace):
                evidence.append({"s": nodes[i], "p": pred, "o": nodes[i + 1]})
        return {"rule": name, "kind": "chain", "satisfied": bool(rows), "evidence": evidence}

    _P_BIDDER_OF = "https://ontology.eai-flow.com/doc_graph#predicate/bidder_of_project"
    _P_REQUIRES = "https://ontology.eai-flow.com/doc_graph#predicate/requires_qualification"
    _P_HOLDS = "https://ontology.eai-flow.com/doc_graph#predicate/bidder_holds_qualification"

    def _trace_requirements(self, bidder: str, project: str) -> dict:
        """qualified_bidder 溯源：项目资质要求 × 投标人持有 对照清单。"""
        req = self.store.query(
            "SELECT ?q WHERE { GRAPH <" + ASSERTED_GRAPH
            + "> { <" + project + "> <" + self._P_REQUIRES + "> ?q } }"
        )
        held = {
            r["q"]
            for r in self.store.query(
                "SELECT ?q WHERE { GRAPH <" + ASSERTED_GRAPH
                + "> { <" + bidder + "> <" + self._P_HOLDS + "> ?q } }"
            )
        }
        evidence = [{"s": bidder, "p": self._P_BIDDER_OF, "o": project}]
        for r in req:
            evidence.append({"s": project, "p": self._P_REQUIRES, "o": r["q"]})
            if r["q"] in held:
                evidence.append({"s": bidder, "p": self._P_HOLDS, "o": r["q"]})
        satisfied = bool(req) and all(r["q"] in held for r in req)
        return {
            "rule": "qualified_bidder",
            "kind": "requirements",
            "satisfied": satisfied,
            "evidence": evidence,
            "details": [
                {"qualification": r["q"], "held": r["q"] in held} for r in req
            ],
        }

    def _trace_sameas(self, alias: str, p: str, o: str) -> dict:
        """sameas_propagation 溯源：sameAs 链接 + 规范实体的对应事实。"""
        owl_sameas = "http://www.w3.org/2002/07/owl#sameAs"
        rows = self.store.query(
            "SELECT ?canonical WHERE { GRAPH <graph:alignment> { { <" + alias
            + "> <" + owl_sameas + "> ?canonical } UNION { ?canonical <"
            + owl_sameas + "> <" + alias + "> } } }"
        )
        evidence: list[dict] = []
        for r in rows:
            canonical = r["canonical"]
            evidence.append({"s": alias, "p": owl_sameas, "o": canonical})
            facts = self.store.query(
                "SELECT ?f WHERE { GRAPH <" + ASSERTED_GRAPH
                + "> { <" + canonical + "> <" + p + "> <" + o + "> } LIMIT 1 }"
            )
            if facts:
                evidence.append({"s": canonical, "p": p, "o": o})
        return {
            "rule": "sameas_propagation",
            "kind": "sameas",
            "satisfied": bool(evidence),
            "evidence": evidence,
        }

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

        wanted = {"graph:schema", "graph:asserted", "graph:entailment"} if graphs == "all" else {"graph:" + graphs}
        g = Graph()
        for quad in self.store._store.quads_for_pattern(None, None, None, None):
            if quad.graph_name.value in wanted:
                g.add(_rdflib_triple(quad))
        if fmt == "json-ld":
            return to_jsonld(g)
        return to_turtle(g)

    async def load_from_sql(self, dsn: str | None = None, domain: str | None = None) -> dict:
        """SQL 测试数据装载（兼任主系统桥接器）。"""
        from app.config import DatabaseConfig
        from app.ontology.kernel.loader import read_doc_graph_rows

        dsn = dsn or DatabaseConfig.from_env().url
        entity_rows, relation_rows, mention_rows = await read_doc_graph_rows(dsn)
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
