"""EIA 校验规则集（子项目 3）：注册表 schema / 执行器 / ``/rules`` REST 暴露面.

设计: docs/superpowers/specs/2026-09-30-eia-rules-mcp-design.md §3/§5/§8

覆盖四块：
① yaml schema 校验（12 条、id/severity 与 spec §4 清单一致、fail-closed）
② 执行器：空图全 0 违规、构造数据精确触发（A 档三条命名规则 ≥1，平衡样本不误报）
③ message_template 渲染（绑定变量替换、缺变量不抛）
④ REST：鉴权门槛（401/403 带 detail 断言，镜像 test_actions_rest 纪律）、清单、
   execute（ids 过滤/未知 id 422/limit 截断但计数真实）——kernel 单例打桩为内存图，
   全程不碰持久化 kernel、不碰真库。
"""

from __future__ import annotations

import os
import uuid

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.ontology.kernel.graph_ops import upsert_entity
from app.ontology.kernel.loader import etype_class_map
from app.ontology.kernel.service import KernelService
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.kernel.vocab import nn
from app.ontology.registry import load_registry
from app.ontology.rules_executor import RuleDefinition, execute_rule, execute_rules, load_rules, render_message

EXECUTE = "/api/extensions/ontology/rules/execute"
LIST = "/api/extensions/ontology/rules"

# spec §4 清单（12 条 id→severity）——注册表漂移即本测试红
SPEC_RULES = {
    "rule_water_balance": "error",
    "rule_prep_zero_discharge": "error",
    "rule_gangue_closure": "error",
    "rule_series_efficiency": "warn",
    "rule_limit_standard_fit": "warn",
    "rule_mine_water_dual": "warn",
    "rule_gas_tier": "warn",
    "rule_subsidence_params": "error",
    "rule_sensitive_coverage": "error",
    "rule_emission_monitoring": "warn",
    "rule_planning_compliance": "error",
    "rule_entity_naming": "warn",
}

PRED = "https://ontology.eai-flow.com/eia#predicate/"


# ── 装置 ─────────────────────────────────────────────────────────────


@pytest.fixture()
def eia_store():
    """真实 registry + 内存图（镜像 test_kernel_eia_v2_golden 的 eia_env）。"""
    registry = load_registry()
    store = OxStore()
    yield store, registry, etype_class_map(registry, "eia")
    store.close()


def _ent(store, vocab, classes, tag: str, etype: str, name: str, attrs: dict | None = None) -> str:
    return upsert_entity(
        store,
        vocab,
        class_name=classes[etype],
        entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"eia-rules-test-{tag}"),
        etype=etype,
        canonical_name=name,
        norm_name=name,
        attrs=attrs or {},
        confidence=0.95,
    )


def _edge(store, s: str, pred: str, o: str) -> None:
    from pyoxigraph import Quad

    store._store.add(Quad(nn(s), nn(PRED + pred), nn(o), nn(ASSERTED_GRAPH)))


def _derived_coverage(store, src_iri: str) -> None:
    """手工放置推理产物（chain_covered_by_monitoring 三段链结论）——镜像 infer 输出形态。"""
    from pyoxigraph import Quad

    mon = "https://ontology.eai-flow.com/eia#instance/test-monitor"
    store._store.add(Quad(nn(src_iri), nn(PRED + "covered_by_monitoring"), nn(mon), nn("graph:derived:chain_covered_by_monitoring")))


def _populate_store(store: OxStore) -> None:
    """构造数据触发三条命名规则（gangue/sensitive/emission_monitoring 各 ≥1）+ 不误报的平衡样本。"""
    registry = load_registry()
    vocab = collect_vocabularies_eia()
    classes = etype_class_map(registry, "eia")

    ws_bad = _ent(store, vocab, classes, "ws-bad", "waste_stream", "规则测试矸石未闭合")
    ws_ok = _ent(store, vocab, classes, "ws-ok", "waste_stream", "规则测试矸石已闭合")
    mine = _ent(store, vocab, classes, "mine", "mine", "规则测试矿")
    brickyard = _ent(store, vocab, classes, "sink", "org", "规则测试砖厂")
    _edge(store, mine, "generates_waste", ws_bad)
    _edge(store, mine, "generates_waste", ws_ok)
    _edge(store, ws_ok, "disposed_by", brickyard)

    _ent(store, vocab, classes, "sp", "sensitive_point", "规则测试敏感村")

    ps_uncovered = _ent(store, vocab, classes, "ps-u", "pollution_source", "规则测试矿井水")
    ep_uncovered = _ent(store, vocab, classes, "ep-u", "emission_point", "规则测试外排口1")
    _edge(store, ps_uncovered, "emitted_via", ep_uncovered)
    ps_covered = _ent(store, vocab, classes, "ps-c", "pollution_source", "规则测试已覆盖源")
    ep_covered = _ent(store, vocab, classes, "ep-c", "emission_point", "规则测试外排口2")
    _edge(store, ps_covered, "emitted_via", ep_covered)
    _derived_coverage(store, ps_covered)


@pytest.fixture()
def memory_kernel(monkeypatch):
    """进程内空 kernel 顶掉单例——REST 集成不碰持久化 kernel 路径。"""
    import app.ontology.kernel.service as svc

    saved = os.environ.pop("ONTOSTUDIO_KERNEL_PATH", None)
    fresh = KernelService()
    monkeypatch.setattr(svc, "_kernel", fresh)
    yield fresh
    if saved is not None:
        os.environ["ONTOSTUDIO_KERNEL_PATH"] = saved


def collect_vocabularies_eia():
    from app.ontology.kernel.compile import collect_vocabularies

    return collect_vocabularies(load_registry())["eia"]


# ── ① 注册表 schema ──────────────────────────────────────────────────


def test_registry_has_12_rules_matching_spec():
    rules = load_rules()
    assert {r.id: r.severity for r in rules} == SPEC_RULES
    assert len(rules) == 12


def test_every_rule_sparql_is_valid_and_empty_graph_gives_zero():
    """每条 SPARQL 对空图可执行（语法成立）且 0 违规——验收「逐条 pyoxigraph 试跑」钉进回归。"""
    store = OxStore()
    try:
        out = execute_rules(store)
        assert out["total_violations"] == 0
        assert {r["rule_id"] for r in out["results"]} == set(SPEC_RULES)
        assert all(r["violation_count"] == 0 for r in out["results"])
    finally:
        store.close()


def test_load_rules_fail_closed(tmp_path):
    base = {"id": "r1", "name": "n", "severity": "error", "description": "d", "data_requirements": "dr", "sparql": "SELECT 1", "message_template": "m"}
    cases = [
        ("缺字段", [{k: v for k, v in base.items() if k != "sparql"}]),
        ("severity 非法", [{**base, "severity": "fatal"}]),
        ("id 重复", [base, {**base, "message_template": "m2"}]),
        ("顶层非列表", {"rules": [base]}),
    ]
    for label, data in cases:
        p = tmp_path / "rules.yaml"
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError, match=".+"):
            load_rules(p)
        # 变异检验：每个坏用例的标签仅用于失败定位
        assert label


def _rule(**over) -> RuleDefinition:
    fields = {"id": "r", "name": "n", "severity": "warn", "description": "d", "data_requirements": "dr", "sparql": "SELECT ?x WHERE {}", "message_template": "m"}
    return RuleDefinition(**(fields | over))


def test_render_message_binds_and_keeps_missing_placeholder():
    assert render_message("流 {wsName} 去 {outN}", {"wsName": "矸石", "outN": "0"}) == "流 矸石 去 0"
    assert render_message("流 {wsName} 缺 {nope}", {"wsName": "矸石"}) == "流 矸石 缺 {nope}"


def test_execute_rule_truncates_but_counts_true_total(eia_store):
    """limit 只截断返回列表，violation_count 恒为真实总数（基线数字不被 limit 污染）。"""
    store, _, _ = eia_store
    rule = _rule(id="count_rule", sparql="SELECT ?x WHERE { GRAPH <graph:asserted> { ?x <https://ontology.eai-flow.com/eia#predicate/generates_waste> ?y } }")
    out = execute_rules(store, rules=[rule])
    assert out["results"][0]["violation_count"] == 0 and not out["results"][0]["truncated"]
    vocab = collect_vocabularies_eia()
    classes = etype_class_map(load_registry(), "eia")
    mine = _ent(store, vocab, classes, "m", "mine", "计数矿")
    for i in range(3):
        ws = _ent(store, vocab, classes, f"ws{i}", "waste_stream", f"计数矸石{i}")
        _edge(store, mine, "generates_waste", ws)
    res = execute_rule(store, rule, limit=2)
    assert res["violation_count"] == 3
    assert len(res["violations"]) == 2
    assert res["truncated"] is True


# ── ② 执行器语义（构造数据，验收核心）─────────────────────────────


def test_constructed_data_fires_three_named_rules(eia_store):
    """rule_gangue_closure / rule_sensitive_coverage / rule_emission_monitoring 各 ≥1，
    且平衡样本与已覆盖源**不**误报（违规内容精确到构造实体）。"""
    store, _, _ = eia_store
    _populate_store(store)
    out = execute_rules(store)
    by_id = {r["rule_id"]: r for r in out["results"]}

    gangue = by_id["rule_gangue_closure"]
    assert gangue["violation_count"] == 1
    assert gangue["violations"][0]["wsName"] == "规则测试矸石未闭合"
    assert "未闭合" in gangue["violations"][0]["message"]

    sensitive = by_id["rule_sensitive_coverage"]
    assert sensitive["violation_count"] == 1
    assert sensitive["violations"][0]["name"] == "规则测试敏感村"

    monitoring = by_id["rule_emission_monitoring"]
    assert monitoring["violation_count"] == 1
    assert monitoring["violations"][0]["epName"] == "规则测试外排口1"

    # 已覆盖源确实进了派生图（防「两边都没查到」的假阳性绿）；IRI 按 _ent 的确定性 uuid5 重建
    ps_covered = f"https://ontology.eai-flow.com/eia#id/{uuid.uuid5(uuid.NAMESPACE_URL, 'eia-rules-test-ps-c')}"
    rows = store.query(f"SELECT ?m WHERE {{ GRAPH <graph:derived:chain_covered_by_monitoring> {{ <{ps_covered}> <{PRED}covered_by_monitoring> ?m }} }}")
    assert len(rows) == 1


# ── ③ REST ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rules_endpoints_require_auth():
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get(LIST)).status_code == 401
        assert (await c.post(EXECUTE, json={})).status_code == 401


@pytest.mark.asyncio
async def test_rules_endpoints_require_system_access(make_token):
    """非管理员 token → 403 且 detail 精确（防路由依赖被摘掉后动作层顺手 403 的假绿）。"""
    from app.main import create_app

    app = create_app()
    headers = {"Authorization": f"Bearer {make_token(roles=('user',))}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=headers) as c:
        r = await c.get(LIST)
    assert r.status_code == 403
    assert r.json()["detail"] == "Permission denied: system:access"


@pytest.mark.asyncio
async def test_list_rules_endpoint(auth_headers):
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.get(LIST)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["count"] == 12
    assert {x["id"]: x["severity"] for x in body["rules"]} == SPEC_RULES
    assert all("data_requirements" in x and "description" in x for x in body["rules"])


@pytest.mark.asyncio
async def test_execute_unknown_id_is_422(auth_headers, memory_kernel):
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(EXECUTE, json={"ids": ["rule_gangue_closure", "no_such_rule"]})
    assert r.status_code == 422
    assert "no_such_rule" in r.json()["detail"]


@pytest.mark.asyncio
async def test_execute_empty_kernel_zero_violations(auth_headers, memory_kernel):
    """空图全 0（验收项）。"""
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(EXECUTE, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["rule_count"] == 12 and body["total_violations"] == 0
    assert body["executed_at"]
    assert all(x["violation_count"] == 0 for x in body["results"])


@pytest.mark.asyncio
async def test_execute_constructed_data_via_endpoint(auth_headers, memory_kernel):
    """端到端：kernel 打桩 + 构造数据 → 三条命名规则各 ≥1（验收项走真实 HTTP 层）。"""
    from app.main import create_app

    _populate_store(memory_kernel.store)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(EXECUTE, json={"ids": ["rule_gangue_closure", "rule_sensitive_coverage", "rule_emission_monitoring"]})
    assert r.status_code == 200
    body = r.json()
    by_id = {x["rule_id"]: x for x in body["results"]}
    assert len(body["results"]) == 3
    assert by_id["rule_gangue_closure"]["violation_count"] >= 1
    assert by_id["rule_sensitive_coverage"]["violation_count"] >= 1
    assert by_id["rule_emission_monitoring"]["violation_count"] >= 1


@pytest.mark.asyncio
async def test_execute_limit_still_reports_true_count(auth_headers, memory_kernel):
    from app.main import create_app

    _populate_store_limit_case(memory_kernel.store)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", headers=auth_headers) as c:
        r = await c.post(EXECUTE, json={"ids": ["rule_gangue_closure"], "limit": 2})
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["violation_count"] == 3 and len(res["violations"]) == 2 and res["truncated"] is True


def _populate_store_limit_case(store: OxStore) -> None:
    vocab = collect_vocabularies_eia()
    classes = etype_class_map(load_registry(), "eia")
    mine = _ent(store, vocab, classes, "lim-m", "mine", "限额测试矿")
    for i in range(3):
        ws = _ent(store, vocab, classes, f"lim-ws{i}", "waste_stream", f"限额矸石{i}")
        _edge(store, mine, "generates_waste", ws)
