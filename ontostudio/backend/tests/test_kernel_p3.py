"""kernel P3 golden 测试：owlrl 闭包 + CONSTRUCT 派生（spec §6 P3 验收）.

三推理场景全绿判据：
① 类层次自动分类（subClassOf → 实例类型提升）
② 属性链/传递推理（propertyChainAxiom 2 段 + TransitiveProperty）
③ 等价/对齐推理（sameAs 候选传播，builtin CONSTRUCT 规则）
另：置信度 ≥0.7 门（低置信实体不入推理空间）。
纯单元零 DB 依赖（复用 P1 mini 词表 + P2 写路径）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pyoxigraph import Quad
from rdflib.namespace import OWL, RDF

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.graph_ops import upsert_entity
from app.ontology.kernel.infer import compute_entailment, refresh_schema
from app.ontology.kernel.rules import (
    BUILTIN_SAMEAS_PROPAGATION,
    DeriveRule,
    load_rules,
    run_all_rules,
    run_rule,
)
from app.ontology.kernel.store import ALIGNMENT_GRAPH, ASSERTED_GRAPH, ENTAILMENT_GRAPH, OxStore
from app.ontology.kernel.vocab import nn
from app.ontology.registry import load_registry
from tests.test_kernel_p1 import MINI_YAML

EX = "https://example.org/mini#"
PRED = EX + "predicate/"
DERIVED_SAMEAS = "graph:derived:sameas_propagation"


@pytest.fixture()
def env(tmp_path: Path):
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    registry = load_registry(tmp_path)
    vocab = collect_vocabularies(registry)["mini"]
    store = OxStore()
    refresh_schema(store, registry)  # schema 图（类层次/公理）入 store
    yield store, vocab, registry
    store.close()


def _e(uuid_: str) -> str:
    return f"{EX}id/{uuid_}"


def _edge(store, s: str, pred: str, o: str):
    store._store.add(Quad(nn(s), nn(PRED + pred), nn(o), nn(ASSERTED_GRAPH)))


def _sameas(store, a: str, b: str):
    store._store.add(Quad(nn(a), nn(str(OWL.sameAs)), nn(b), nn(ALIGNMENT_GRAPH)))


def _has(store, graph: str, s: str, p: str, o: str, *, literal: bool = False) -> bool:
    obj = f'"{o}"' if literal else f"<{o}>"
    rows = store.query(f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ <{s}> <{p}> {obj} }} }}")
    return int(rows[0]["n"] or 0) > 0


# ---- ① 类层次自动分类 ----


def test_scenario1_class_hierarchy(env):
    store, vocab, _ = env
    upsert_entity(store, vocab, class_name="Project", entity_uuid="11111111-1111-1111-1111-111111111111", etype="project", canonical_name="横城煤矿项目", confidence=0.9)
    stats = compute_entailment(store)
    assert not stats.errors
    # Project subClassOf Activity → 实例自动获得 Activity 类型
    assert _has(store, ENTAILMENT_GRAPH, _e("11111111-1111-1111-1111-111111111111"), str(RDF.type), f"{EX}Activity"), "子类实例必须被推导出父类类型"


# ---- ② 属性链 / 传递推理 ----


def test_scenario2_property_chain_and_transitive(env):
    store, vocab, _ = env
    a, b, c, d, e = (_e(u) for u in ("22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333", "44444444-4444-4444-4444-444444444444", "55555555-5555-5555-5555-555555555555", "5a555555-5555-5555-5555-555555555555"))
    # 链：in_ecosystem = part_of ∘ owned_by（mini formal 段，2 段 → owlrl prp-spo2）
    _edge(store, a, "part_of", b)
    _edge(store, b, "owned_by", c)
    # 传递：part_of transitive（mini formal 段）——独立链 x→y→z
    _edge(store, c, "part_of", d)
    _edge(store, d, "part_of", e)
    compute_entailment(store)

    assert _has(store, ENTAILMENT_GRAPH, a, PRED + "in_ecosystem", c), "属性链 2 段必须推出"
    assert _has(store, ENTAILMENT_GRAPH, c, PRED + "part_of", e), "part_of 传递闭包必须推出"


def test_scenario2b_inverse(env):
    store, vocab, _ = env
    x, y = _e("66666666-6666-6666-6666-666666666666"), _e("77777777-7777-7777-7777-777777777777")
    _edge(store, x, "compiled_by", y)
    compute_entailment(store)
    # inverse: compiled_by ⇄ parent_of
    assert _has(store, ENTAILMENT_GRAPH, y, PRED + "parent_of", x), "逆属性必须推出"


# ---- ③ 等价 / 对齐推理（sameAs 候选传播）----


def test_scenario3_sameas_propagation(env):
    store, vocab, _ = env
    canonical = _e("88888888-8888-8888-8888-888888888888")
    alias = _e("99999999-9999-9999-9999-999999999999")
    upsert_entity(store, vocab, class_name="Org", entity_uuid="88888888-8888-8888-8888-888888888888", etype="org", canonical_name="山西煤机集团", confidence=0.95)
    _sameas(store, alias, canonical)  # 候选覆盖层（不做业务合并）

    counts = run_all_rules(store, [BUILTIN_SAMEAS_PROPAGATION])
    assert counts["sameas_propagation"] > 0
    # 候选的断言属性传播到别名（derived 图，断言图不被改写）
    assert _has(store, DERIVED_SAMEAS, alias, f"{EX}attr/canonical_name", "山西煤机集团", literal=True)
    # sameAs 纪律：断言图绝不出现别名属性
    assert not _has(store, ASSERTED_GRAPH, alias, f"{EX}attr/canonical_name", "山西煤机集团", literal=True)


# ---- 置信度 ≥0.7 门 ----


def test_confidence_gate(env):
    store, vocab, _ = env
    upsert_entity(store, vocab, class_name="Project", entity_uuid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", etype="project", canonical_name="低置信实体", confidence=0.5)
    stats = compute_entailment(store)
    assert stats.filtered_low_confidence > 0, "低置信三元组必须被门限过滤"
    assert not _has(store, ENTAILMENT_GRAPH, _e("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), str(RDF.type), f"{EX}Activity"), "低置信实体不得入推理空间"


# ---- 规则装载 / 冒烟 ----


def test_load_builtin_rules_yaml():
    rules = load_rules()  # kernel/rules.yaml（doc_graph 域内置规则）
    names = {r.name for r in rules}
    assert {"org_in_ecosystem", "qualified_bidder"} <= names


def test_run_rule_smoke_empty_store(env):
    store, vocab, _ = env
    rule = DeriveRule(
        name="smoke",
        construct=f"CONSTRUCT {{ ?a ?b ?c }} WHERE {{ GRAPH <{ASSERTED_GRAPH}> {{ ?a ?b ?c }} }}",
    )
    assert run_rule(store, rule) == 0
    counts = run_all_rules(store, [rule])
    assert counts == {"smoke": 0}
