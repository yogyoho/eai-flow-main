"""kernel P1 golden 测试（spec 2026-09-18 §6 P1）：编译/序列化/IRI/存储.

- 真实 registry 编译 → Turtle round-trip（P1 验收判据）
- mini formal 段 YAML → OWL 2 RL 公理三元组（propertyChain/transitive/inverse/disjoint/hasKey）
- IRI 机械可逆；OxStore named-graph 装载/查询/导出
纯单元：无外部服务依赖（内存 OxStore + 临时目录）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pyoxigraph as ox
import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from app.ontology.kernel import export as kernel_export
from app.ontology.kernel.compile import compile_schema_graph
from app.ontology.kernel.iri import IriScheme, domain_namespace, etype_to_class_name
from app.ontology.kernel.store import SCHEMA_GRAPH, OxStore
from app.ontology.registry import load_registry

MINI_YAML = """\
namespaces:
  ex: "https://example.org/mini#"
object_types:
  - api_name: thing
    display_name: 事物
    description: 测试对象
    domain: mini
    access: { path: postgres_ext, table: mini_things }
    pk: { column: id, api_name: id, type: uuid }
    properties:
      - { name: id, api_name: id, type: uuid, description: 主键 }
      - { name: etype, api_name: etype, type: string, description: 类型, enum: [project, org, activity] }
      - { name: predicate, api_name: predicate, type: string, description: 谓词, enum: [part_of, owned_by, compiled_by, parent_of, in_ecosystem] }
    etype_classes:
      project: { class: Project, subClassOf: [Activity], hasKey: [norm_name] }
      org: { class: Org, label: 机构, definition: 参与标准化活动的组织实体 }
formal:
  transitive: [part_of]
  inverse: [{ pair: [compiled_by, parent_of] }]
  disjoint: [Project, Org]
  property_chains:
    - { derived: in_ecosystem, chain: [part_of, owned_by] }
"""


@pytest.fixture(scope="module")
def real_registry():
    return load_registry()


@pytest.fixture(scope="module")
def real_graph(real_registry):
    return compile_schema_graph(real_registry)


# ---- IRI 策略（国标 §5.4）----


def test_etype_to_class_name():
    assert etype_to_class_name("project") == "Project"
    assert etype_to_class_name("sensitive_point") == "SensitivePoint"


def test_domain_namespace_prefers_declared():
    assert domain_namespace("doc_graph", {"dg": "https://example.org/dg#"}) == "https://example.org/dg#"
    assert domain_namespace("doc_graph") == "https://ontology.eai-flow.com/doc_graph#"
    # W3C 标准命名空间不作为域空间
    assert domain_namespace("x", {"rdfs": "http://www.w3.org/2000/01/rdf-schema#"}) == "https://ontology.eai-flow.com/x#"


def test_instance_iri_roundtrip():
    scheme = IriScheme("https://example.org/mini#")
    entity_uuid = uuid.uuid4()
    iri = scheme.instance_iri(entity_uuid)
    assert iri == f"https://example.org/mini#id/{entity_uuid}"
    assert scheme.parse_instance(iri) == entity_uuid


def test_parse_instance_rejects_foreign_iri():
    scheme = IriScheme("https://example.org/mini#")
    with pytest.raises(ValueError, match="非本域"):
        scheme.parse_instance("https://other.org/id/abc")
    with pytest.raises(ValueError):
        scheme.parse_instance("https://example.org/mini#id/not-a-uuid")


# ---- 真实 registry 编译（P1 验收判据）----


def test_compile_real_registry_emits_classes(real_graph):
    ns = "https://ontology.eai-flow.com/doc_graph#"
    project = URIRef(f"{ns}Project")
    assert (project, RDF.type, OWL.Class) in real_graph
    labels = list(real_graph.objects(project, RDFS.label))
    assert labels and labels[0].language == "zh"


def test_compile_real_registry_turtle_roundtrip(real_graph):
    ttl = kernel_export.to_turtle(real_graph)
    parsed = kernel_export.parse_turtle(ttl)
    assert kernel_export.graphs_isomorphic(real_graph, parsed), "Turtle round-trip 必须同构"


def test_compile_real_registry_jsonld(real_graph):
    doc = kernel_export.to_jsonld(real_graph)
    # rdflib json-ld：顶层可能为节点数组（无 @graph 包裹），两种形态都合法
    assert "@graph" in doc or "@context" in doc or isinstance(doc, list)
    iris = json.dumps(doc)
    assert "doc_graph#" in iris
    assert "owl#Class" in iris


# ---- mini formal 段：OWL 2 RL 公理编译 ----


@pytest.fixture()
def mini_graph(tmp_path: Path):
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    return compile_schema_graph(load_registry(tmp_path))


def test_formal_subclass_and_key(mini_graph):
    ex = "https://example.org/mini#"
    assert (URIRef(f"{ex}Project"), RDFS.subClassOf, URIRef(f"{ex}Activity")) in mini_graph
    # hasKey → RDF list（norm_name 单元素）；键节点用路径形式（类 IRI 已含 #，双 # 非法）
    key_node = URIRef(f"{ex}axiom/hasKey/Project")
    assert (URIRef(f"{ex}Project"), OWL.hasKey, key_node) in mini_graph
    assert (key_node, RDF.first, URIRef(f"{ex}attr/norm_name")) in mini_graph
    assert (key_node, RDF.rest, RDF.nil) in mini_graph


def test_formal_class_metadata(mini_graph):
    ex = "https://example.org/mini#"
    org = URIRef(f"{ex}Org")
    labels = list(mini_graph.objects(org, RDFS.label))
    assert labels and str(labels[0]) == "机构"


def test_formal_axioms(mini_graph):
    ex = "https://example.org/mini#"
    part_of = URIRef(f"{ex}predicate/part_of")
    assert (part_of, RDF.type, OWL.TransitiveProperty) in mini_graph
    assert (URIRef(f"{ex}predicate/compiled_by"), OWL.inverseOf, URIRef(f"{ex}predicate/parent_of")) in mini_graph

    # propertyChain：derived + 规范 RDF collection [part_of, owned_by]
    derived = URIRef(f"{ex}predicate/in_ecosystem")
    chains = list(mini_graph.objects(derived, OWL.propertyChainAxiom))
    assert len(chains) == 1
    first = mini_graph.value(chains[0], RDF.first)
    rest = mini_graph.value(chains[0], RDF.rest)
    assert first == part_of
    assert mini_graph.value(rest, RDF.first) == URIRef(f"{ex}predicate/owned_by")

    # AllDisjointClasses
    disjoint_nodes = list(mini_graph.subjects(RDF.type, OWL.AllDisjointClasses))
    assert len(disjoint_nodes) == 1


def test_formal_unknown_predicate_fails_closed(tmp_path: Path):
    bad = MINI_YAML.replace("chain: [part_of, owned_by]", "chain: [part_of, nonexistent_pred]")
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(bad, encoding="utf-8")
    from app.ontology.kernel.compile import CompileError

    with pytest.raises(CompileError, match="nonexistent_pred"):
        compile_schema_graph(load_registry(tmp_path))


# ---- OxStore（pyoxigraph 真源骨架）----


def test_store_named_graph_roundtrip(tmp_path: Path, real_graph):
    ttl = kernel_export.to_turtle(real_graph)
    with OxStore(tmp_path / "store") as store:
        store.load_turtle(ttl, SCHEMA_GRAPH)
        assert store.count_quads(SCHEMA_GRAPH) == len(real_graph)

        dumped = store.dump_turtle(SCHEMA_GRAPH)
        assert kernel_export.graphs_isomorphic(real_graph, kernel_export.parse_turtle(dumped))

        rows = store.query("SELECT ?c WHERE { GRAPH <graph:schema> { ?c a <http://www.w3.org/2002/07/owl#Class> } }")
        assert any(str(row["c"]).endswith("#Project") for row in rows)


def test_store_memory_mode_isolation():
    with OxStore() as store:
        store.load_turtle("<https://example.org/a> <https://example.org/b> 'c' .", SCHEMA_GRAPH)
        assert store.count_quads(SCHEMA_GRAPH) == 1
    # 独立内存实例不串数据
    with OxStore() as other:
        assert other.count_quads(SCHEMA_GRAPH) == 0


def test_pyoxigraph_term_types():
    # 直接验证 _term_to_python 的输入假设（Literal/NamedNode 取 .value）
    assert ox.NamedNode("https://example.org/x").value == "https://example.org/x"
    assert ox.Literal("c").value == "c"
    assert isinstance(Literal("c"), Literal)
