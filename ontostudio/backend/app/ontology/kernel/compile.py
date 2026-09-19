"""registry → OWL 本体图编译（kernel P1）.

输入：ontology.registry.load_registry() 的不可变快照。
输出：rdflib Graph（schema 层：类/标签/层次/公理），供 export 与 store 装载。

- 类来源：ObjectType.etype_classes 显式映射；未声明 v2 段的对象类型按 etype 枚举
  合成 PascalCase 类（保证存量 YAML 零改动即可编译）。
- formal 段公理 → OWL 2 RL 三元组：subClassOf / equivalentClass / hasKey /
  propertyChainAxiom / TransitiveProperty / inverseOf / AllDisjointClasses。
- 编译失败 fail-closed 抛 CompileError（引用键不存在等），绝不半编译。
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from app.ontology.kernel.iri import IriScheme, domain_namespace, etype_to_class_name
from app.ontology.registry import Registry


class CompileError(Exception):
    """本体编译失败（fail-closed）。"""


class DomainVocabulary:
    """单域编译产物：命名空间 + 类/谓词局部名 → 完整 IRI。"""

    def __init__(self, domain: str, namespace: str, class_names: set[str], predicates: set[str]) -> None:
        self.domain = domain
        self.scheme = IriScheme(namespace)
        self.class_names = class_names
        self.predicates = predicates

    def class_ref(self, name: str) -> URIRef:
        if name not in self.class_names:
            raise CompileError(f"域 {self.domain}: 未声明类 '{name}'（formal 段只能引用本域类局部名）")
        return URIRef(self.scheme.class_iri(name))

    def predicate_ref(self, name: str) -> URIRef:
        if name not in self.predicates:
            raise CompileError(f"域 {self.domain}: 未声明谓词 '{name}'")
        return URIRef(_predicate_iri(self.scheme, name))


def _predicate_iri(scheme: IriScheme, name: str) -> str:
    return f"{scheme.namespace}predicate/{name}"


def collect_vocabularies(registry: Registry) -> dict[str, DomainVocabulary]:
    """按域聚合：类名（etype_classes 显式 ∪ etype 合成）与谓词名（谓词枚举）。"""
    domains: dict[str, DomainVocabulary] = {}
    for ot in registry.object_types.values():
        vocab = domains.get(ot.domain)
        if vocab is None:
            vocab = DomainVocabulary(
                domain=ot.domain,
                namespace=domain_namespace(ot.domain, registry.namespaces_by_domain.get(ot.domain)),
                class_names=set(),
                predicates=set(),
            )
            domains[ot.domain] = vocab

        etype_prop = next((p for p in ot.properties if p.name == "etype" and p.enum), None)
        if etype_prop is not None:
            for etype in etype_prop.enum:
                mapping = (ot.etype_classes or {}).get(etype)
                vocab.class_names.add(mapping.class_name if mapping and mapping.class_name else etype_to_class_name(etype))

        # 谓词：name=predicate 的枚举属性（关系类型对象上，如 doc_graph 的 graph_relation——
        # 注意关系对象无 etype 属性，不能因此跳过谓词收集）
        pred_prop = next((p for p in ot.properties if p.name == "predicate" and p.enum), None)
        if pred_prop is not None:
            vocab.predicates.update(pred_prop.enum)

    # formal 段引用的谓词（派生/传递/逆）自动入词表——派生谓词是推理产物，
    # 不应要求出现在抽取枚举里
    for domain, formal in registry.formal_by_domain.items():
        if domain not in domains:
            continue
        vocab = domains[domain]
        for axiom in formal.property_chains:
            vocab.predicates.add(axiom.derived)
            vocab.predicates.update(axiom.chain)
        vocab.predicates.update(formal.transitive)
        for pair in formal.inverse:
            vocab.predicates.update(pair.pair)
    return domains


def compile_schema_graph(registry: Registry) -> Graph:
    """编译本体 schema 图：类层次 + 标签/定义 + formal 段公理。"""
    graph = Graph()
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)

    vocabs = collect_vocabularies(registry)

    # Pass 1：类声明 + 标签/定义（国标附录 A：IRI/Name/Label/Definition）
    for ot in registry.object_types.values():
        vocab = vocabs[ot.domain]
        etype_prop = next((p for p in ot.properties if p.name == "etype" and p.enum), None)
        if etype_prop is None:
            continue
        for etype in etype_prop.enum:
            mapping = (ot.etype_classes or {}).get(etype)
            class_name = mapping.class_name if mapping and mapping.class_name else etype_to_class_name(etype)
            subject = vocab.class_ref(class_name)
            graph.add((subject, RDF.type, OWL.Class))
            graph.add((subject, RDFS.label, Literal(mapping.label if mapping and mapping.label else etype, lang="zh")))
            if mapping and mapping.definition:
                graph.add((subject, RDFS.comment, Literal(mapping.definition, lang="zh")))

    # Pass 2：etype_classes 显式映射的层次/等价/键
    for ot in registry.object_types.values():
        if not ot.etype_classes:
            continue
        vocab = vocabs[ot.domain]
        for etype, mapping in ot.etype_classes.items():
            class_name = mapping.class_name or etype_to_class_name(etype)
            subject = vocab.class_ref(class_name)
            for parent in mapping.sub_class_of:
                graph.add((subject, RDFS.subClassOf, vocab.class_ref(parent)))
            for equivalent in mapping.equivalent_class:
                graph.add((subject, OWL.equivalentClass, URIRef(equivalent)))
            if mapping.has_key:
                # 路径形式（类 IRI 已含 #，追加 # 会产生非法双 # IRI——pyoxigraph 严格校验）
                key_node = URIRef(f"{vocab.scheme.namespace}axiom/hasKey/{class_name}")
                items = [URIRef(f"{vocab.scheme.namespace}attr/{column}") for column in mapping.has_key]
                Collection(graph, key_node, items)  # 规范 RDF collection（first/rest 链）
                graph.add((subject, OWL.hasKey, key_node))

    # Pass 3：域级 formal 段公理
    for domain, formal in registry.formal_by_domain.items():
        _compile_formal(graph, vocabs[domain], formal)

    return graph


def _compile_formal(graph: Graph, vocab: DomainVocabulary, formal) -> None:  # noqa: ANN001
    for name in formal.transitive:
        pred = vocab.predicate_ref(name)
        graph.add((pred, RDF.type, OWL.TransitiveProperty))

    for pair in formal.inverse:
        left = vocab.predicate_ref(pair.pair[0])
        right = vocab.predicate_ref(pair.pair[1])
        graph.add((left, OWL.inverseOf, right))

    if formal.disjoint:
        members = [vocab.class_ref(name) for name in formal.disjoint]
        if len(members) >= 2:
            blank = URIRef(f"{vocab.scheme.namespace}axiom/disjoint/{abs(hash(tuple(formal.disjoint)))}")
            graph.add((blank, RDF.type, OWL.AllDisjointClasses))
            for member in members:
                graph.add((blank, OWL.members, member))

    for axiom in formal.property_chains:
        derived = vocab.predicate_ref(axiom.derived)
        graph.add((derived, RDF.type, OWL.ObjectProperty))
        # 链表节点用路径形式（谓词 IRI 已含 #，双 # 非法 IRI——pyoxigraph 严格校验）
        chain_node = URIRef(f"{_predicate_iri(vocab.scheme, axiom.derived)}/chain")
        Collection(graph, chain_node, [vocab.predicate_ref(step) for step in axiom.chain])
        graph.add((derived, OWL.propertyChainAxiom, chain_node))


__all__ = [
    "CompileError",
    "DomainVocabulary",
    "compile_schema_graph",
    "collect_vocabularies",
]
