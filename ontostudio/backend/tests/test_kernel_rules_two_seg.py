"""bug 修复反例：2 段链在链首(derived)属性无任何既有三元组时仍必须物化。

owlrl prp-spo2 只在链首属性已在图中出现时触发（OWLRL.py:348），
链首无实例 → 静默零推断。修复后 2 段链走 CONSTRUCT 规则（独立 derived 图），
不再依赖 owlrl。helper/查询写法镜像 test_kernel_p5.py。
"""

from __future__ import annotations

import uuid

import pytest

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.graph_ops import upsert_entity
from app.ontology.kernel.infer import compute_entailment, refresh_schema
from app.ontology.kernel.rules import builtin_chain_rules, load_rules, run_all_rules
from app.ontology.kernel.store import OxStore
from app.ontology.registry import load_registry

EIA = "https://ontology.eai-flow.com/eia#"
PRED = EIA + "predicate/"
DERIVED_STANDARD = "graph:derived:chain_covered_by_standard"


def _uid(tag: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eia-2seg-{tag}"))


@pytest.fixture(scope="module")
def eia_env():
    """真实 registry（含 eia.yaml formal 段）+ 空 store。"""
    registry = load_registry()
    store = OxStore()
    refresh_schema(store, registry)
    yield store, registry, collect_vocabularies(registry)["eia"]
    store.close()


def _entity(store, vocab, tag: str, class_name: str, etype: str, name: str, confidence: float = 0.9) -> str:
    return upsert_entity(store, vocab, class_name=class_name, entity_uuid=_uid(tag), etype=etype, canonical_name=name, confidence=confidence)


def _edge(store, s: str, pred: str, o: str, tag: str):
    from pyoxigraph import Quad

    from app.ontology.kernel.store import ASSERTED_GRAPH
    from app.ontology.kernel.vocab import nn

    store._store.add(Quad(nn(s), nn(PRED + pred), nn(o), nn(ASSERTED_GRAPH)))


def test_two_seg_chain_materializes_without_head_seed(eia_env):
    """covered_by_standard = [treated_by, governed_by]，图中无任何 covered_by_standard 三元组。"""
    store, registry, vocab = eia_env
    src = _entity(store, vocab, "src", "PollutionSource", "pollution_source", "锅炉烟气A")
    mez = _entity(store, vocab, "mez", "TreatmentMeasure", "treatment_measure", "双碱法脱硫A")
    std = _entity(store, vocab, "std", "EmissionStandard", "emission_standard", "GB 13223-2011A")
    _edge(store, src, "treated_by", mez, "e1")
    _edge(store, mez, "governed_by", std, "e2")

    stats = compute_entailment(store)
    assert not stats.errors
    counts = run_all_rules(store, load_rules() + builtin_chain_rules(registry))

    # 修复前：counts 无 chain_covered_by_standard（被 <=2 continue 跳过），物化为 0
    assert counts.get("chain_covered_by_standard") == 1, counts
    # 物化落在独立 derived 图（与 3 段链同路径）
    rows = store.query(f"SELECT ?s WHERE {{ GRAPH <{DERIVED_STANDARD}> {{ ?s <{PRED}covered_by_standard> ?o }} }}")
    assert {r["s"] for r in rows} == {src}
