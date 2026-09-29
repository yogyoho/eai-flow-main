"""eia v2 schema golden 测试（正式 registry：链物化/共享节点/时效/类比/词表 + CQ 执行器）.

Task 11 已将 eia.yaml 替换为 v2（用户 2026-09-28 GATE2/3 定型），fixture 直接
load_registry() 加载真实 registry。helper/查询写法镜像 test_kernel_p5.py /
test_kernel_rules_two_seg.py（upsert_entity 返回 str IRI、边直写 graph:asserted、
链结论查 graph:derived:chain_<derived>、SPARQL 一律带 GRAPH 子句——bug-3403）。

六组 golden：
① 沉陷影响链 [causes,affects] → chain_impact_on_receptor
② 疏干链 [causes,drawdown_of] → chain_aquifer_impact
③ 同一 impact_result(导水裂缝带) 实例被两链共享 ⇒ 两规则各派 1（spec §六 共享节点要点）
④ standard_threshold 时效裁决（kp:validFrom/validTo + xsd:dateTime 转型——bug-3404）
⑤ analogy_case attrs.scenario_tags 检索命中
⑥ pollutant_concept attrs.aliases 别名归一到规范名
加 CQ 验收集执行器：Task 7 的 12 条 .rq 对 draft schema 可执行即过（语义正确性归 Task 11 人工核）。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.graph_ops import upsert_entity
from app.ontology.kernel.infer import compute_entailment, refresh_schema
from app.ontology.kernel.rules import builtin_chain_rules, load_rules, run_all_rules
from app.ontology.kernel.store import OxStore
from app.ontology.registry import load_registry

EIA = "https://ontology.eai-flow.com/eia#"
PRED = EIA + "predicate/"
ATTR = EIA + "attr/"
KP = "https://ontology.eai-flow.com/kernel#"
DERIVED_RECEPTOR = "graph:derived:chain_impact_on_receptor"
DERIVED_AQUIFER = "graph:derived:chain_aquifer_impact"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CQ_DIR = BACKEND_ROOT / "scripts" / "eia_schema_mining" / "cq"


def _uid(tag: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eia-v2golden-{tag}"))


@pytest.fixture()
def eia_env():
    """正式 registry（v2 eia.yaml）+ 空 store——镜像 test_kernel_p5.py 的 eia_env。"""
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


def _infer_and_run(store, registry) -> dict[str, int]:
    stats = compute_entailment(store)
    assert not stats.errors
    return run_all_rules(store, load_rules() + builtin_chain_rules(registry))


# ---- ① 沉陷影响链 ----


def test_subsidence_chain_materializes(eia_env):
    """工作面→causes→影响结果(subsidence)→affects→敏感点 ⇒ chain_impact_on_receptor 物化。"""
    store, registry, vocab = eia_env
    wf = _entity(store, vocab, "wf", "WorkingFace", "working_face", "首采区203工作面")
    ir = _entity(store, vocab, "ir-sub", "ImpactResult", "impact_result", "地表沉陷预测R1")
    sp = _entity(store, vocab, "sp", "SensitivePoint", "sensitive_point", "跃泉村居民点")
    _edge(store, wf, "causes", ir, "wf-ir")
    _edge(store, ir, "affects", sp, "ir-sp")

    counts = _infer_and_run(store, registry)

    assert counts.get("chain_impact_on_receptor") == 1, counts
    rows = store.query(f"SELECT ?s WHERE {{ GRAPH <{DERIVED_RECEPTOR}> {{ ?s <{PRED}impact_on_receptor> <{sp}> }} }}")
    assert {r["s"] for r in rows} == {wf}


# ---- ② 疏干链 ----


def test_aquifer_chain_materializes(eia_env):
    """工作面→causes→疏干影响→drawdown_of→含水层 ⇒ chain_aquifer_impact 物化。"""
    store, registry, vocab = eia_env
    wf = _entity(store, vocab, "wf2", "WorkingFace", "working_face", "首采区203工作面")
    ir = _entity(store, vocab, "ir-dd", "ImpactResult", "impact_result", "含水层水位降深预测")
    aq = _entity(store, vocab, "aq", "Aquifer", "aquifer", "萨拉乌苏组含水层")
    _edge(store, wf, "causes", ir, "wf-ir")
    _edge(store, ir, "drawdown_of", aq, "ir-aq")

    counts = _infer_and_run(store, registry)

    assert counts.get("chain_aquifer_impact") == 1, counts
    rows = store.query(f"SELECT ?s WHERE {{ GRAPH <{DERIVED_AQUIFER}> {{ ?s <{PRED}aquifer_impact> <{aq}> }} }}")
    assert {r["s"] for r in rows} == {wf}


# ---- ③ 共享节点（spec §六 要点）----


def test_shared_water_conducting_zone_node(eia_env):
    """同一 impact_result(导水裂缝带) 实例被沉陷链(affects)与疏干链(drawdown_of)两链引用
    ⇒ 两规则各派 1 条，工作面节点挂两条 derived 出边（互不干扰）。"""
    store, registry, vocab = eia_env
    wf = _entity(store, vocab, "wf3", "WorkingFace", "working_face", "首采区203工作面")
    ir = _entity(store, vocab, "ir-wcz", "ImpactResult", "impact_result", "导水裂缝带发育高度预测")
    sp = _entity(store, vocab, "sp3", "SensitivePoint", "sensitive_point", "跃泉村居民点")
    aq = _entity(store, vocab, "aq3", "Aquifer", "aquifer", "萨拉乌苏组含水层")
    _edge(store, wf, "causes", ir, "wf-ir")
    _edge(store, ir, "affects", sp, "ir-sp")
    _edge(store, ir, "drawdown_of", aq, "ir-aq")

    counts = _infer_and_run(store, registry)

    assert counts.get("chain_impact_on_receptor") == 1, counts
    assert counts.get("chain_aquifer_impact") == 1, counts
    rows = store.query(f"SELECT ?s WHERE {{ GRAPH <{DERIVED_RECEPTOR}> {{ ?s <{PRED}impact_on_receptor> <{sp}> }} }}")
    assert {r["s"] for r in rows} == {wf}
    rows = store.query(f"SELECT ?s WHERE {{ GRAPH <{DERIVED_AQUIFER}> {{ ?s <{PRED}aquifer_impact> <{aq}> }} }}")
    assert {r["s"] for r in rows} == {wf}


# ---- ④ 阈值时效裁决 ----


def test_threshold_temporal_query(eia_env):
    """同一标准下两个 standard_threshold 有效期不同期：基准日 2025-06-30 只命中在位版本。

    bug-3404：kp:validFrom/validTo 是无类型字面量，比较前须 xsd:dateTime 转型。
    """
    store, registry, vocab = eia_env
    std = _entity(store, vocab, "std", "EmissionStandard", "emission_standard", "GB 20426-2017")
    th_old = upsert_entity(
        store,
        vocab,
        class_name="StandardThreshold",
        entity_uuid=_uid("th-old"),
        etype="standard_threshold",
        canonical_name="SO2 排放限值(2020版)",
        confidence=0.9,
        valid_from="2020-01-01T00:00:00",
        valid_to="2024-12-31T23:59:59",
    )
    th_cur = upsert_entity(
        store,
        vocab,
        class_name="StandardThreshold",
        entity_uuid=_uid("th-cur"),
        etype="standard_threshold",
        canonical_name="SO2 排放限值(2025版)",
        confidence=0.9,
        valid_from="2025-01-01T00:00:00",
        valid_to="2027-12-31T23:59:59",
    )
    _edge(store, th_old, "part_of", std, "th-old-std")
    _edge(store, th_cur, "part_of", std, "th-cur-std")

    rows = store.query(
        f"""
        PREFIX pred: <{PRED}>
        PREFIX kp: <{KP}>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT ?th WHERE {{
          GRAPH <graph:asserted> {{
            ?th pred:part_of <{std}> .
            OPTIONAL {{ ?th kp:validFrom ?vfrom }}
            OPTIONAL {{ ?th kp:validTo ?vto }}
          }}
          FILTER((!BOUND(?vfrom) || xsd:dateTime(?vfrom) <= "2025-06-30T00:00:00"^^xsd:dateTime)
              && (!BOUND(?vto)   || xsd:dateTime(?vto)   >= "2025-06-30T00:00:00"^^xsd:dateTime))
        }}
        """
    )
    assert {r["th"] for r in rows} == {th_cur}


# ---- ⑤ 类比案例标签检索 ----


def test_analogy_case_tag_query(eia_env):
    """analogy_case attrs.scenario_tags=["重介","5.0Mt/a"]：按工艺+规模标签检索命中。"""
    store, registry, vocab = eia_env
    case = upsert_entity(
        store,
        vocab,
        class_name="AnalogyCase",
        entity_uuid=_uid("case"),
        etype="analogy_case",
        canonical_name="同类矿井类比案例A",
        confidence=0.9,
        attrs={"scenario_tags": ["重介", "5.0Mt/a"], "source_report": "类比矿井X环评报告书"},
    )

    rows = store.query(
        f"""
        PREFIX attr: <{ATTR}>
        SELECT ?case WHERE {{
          GRAPH <graph:asserted> {{
            ?case attr:scenario_tags ?tags .
            FILTER(CONTAINS(?tags, "重介") && CONTAINS(?tags, "5.0Mt/a"))
          }}
        }}
        """
    )
    assert {r["case"] for r in rows} == {case}


# ---- ⑥ 受控词表别名归一 ----


def test_alias_vocab_normalization(eia_env):
    """pollutant_concept attrs.aliases 含 "NH3-N"：按别名检索归一到规范名 "氨氮"。"""
    store, registry, vocab = eia_env
    pc = upsert_entity(
        store,
        vocab,
        class_name="PollutantConcept",
        entity_uuid=_uid("nh3"),
        etype="pollutant_concept",
        canonical_name="氨氮",
        confidence=0.9,
        attrs={"aliases": ["NH3-N", "氨氮(NH3-N)"], "code": "HJ524"},
    )

    rows = store.query(
        f"""
        PREFIX attr: <{ATTR}>
        SELECT ?name WHERE {{
          GRAPH <graph:asserted> {{
            ?pc attr:aliases ?aliases .
            FILTER(CONTAINS(?aliases, "NH3-N"))
            ?pc attr:canonical_name ?name .
          }}
        }}
        """
    )
    assert len(rows) == 1, rows
    assert rows[0]["name"] == "氨氮"


# ---- CQ 验收集执行器（Task 7 的 12 条 .rq）----


def test_cq_collection_executes_on_draft(eia_env):
    """12 条 CQ 对 draft schema 可执行即过（解析+求值不抛异常；语义正确性归 Task 11 人工核）。"""
    store, registry, vocab = eia_env
    rq_files = sorted(CQ_DIR.glob("*.rq"))
    assert len(rq_files) == 12, f"CQ 验收集应 12 条，实得 {len(rq_files)}: {rq_files}"
    for rq in rq_files:
        # 可执行性 = store.query 不抛异常（语法/图名/前缀错误即失败）；
        # 空库确定性命中 0 行（CQ 全为无聚合 SELECT），顺带断言防意外命中。
        rows = store.query(rq.read_text(encoding="utf-8"))
        assert len(rows) == 0, f"{rq.name}: 空库意外命中 {len(rows)} 行"
