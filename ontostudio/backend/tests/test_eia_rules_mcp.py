"""EIA MCP 消费通道（子项目 3）：query_entity / check_consistency / get_writing_context / get_rule_violations.

设计: docs/superpowers/specs/2026-09-30-eia-rules-mcp-design.md §6

覆盖接线自己：工具注册（名字/required/枚举）、handler 分派、打桩内存 kernel 上的
查询语义（实体解析/邻域/两跳约束/违规过滤/负路径）。不碰持久化 kernel、不碰真库。
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from app.ontology import mcp as ontomcp
from app.ontology.kernel.graph_ops import add_relation, upsert_entity
from app.ontology.kernel.loader import etype_class_map
from app.ontology.kernel.service import KernelService
from app.ontology.registry import load_registry

PRED = "https://ontology.eai-flow.com/eia#predicate/"


@pytest.fixture()
def memory_kernel(monkeypatch):
    """进程内空 kernel 顶掉单例（与 test_eia_rules 同手法）。"""
    import app.ontology.kernel.service as svc

    saved = os.environ.pop("ONTOSTUDIO_KERNEL_PATH", None)
    fresh = KernelService()
    monkeypatch.setattr(svc, "_kernel", fresh)
    yield fresh
    if saved is not None:
        os.environ["ONTOSTUDIO_KERNEL_PATH"] = saved


def _populate(kernel: KernelService) -> None:
    """矸石流（未闭合→rule_gangue_closure 抓 1）+ 敏感村→沉淀池→阈值（写作上下文两跳约束）。"""
    store = kernel.store
    registry = load_registry()

    def ent(tag: str, etype: str, name: str, attrs: dict | None = None) -> str:
        return upsert_entity(
            store,
            vocab,
            class_name=classes[etype],
            entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"eia-mcp-{tag}"),
            etype=etype,
            canonical_name=name,
            norm_name=name,
            attrs=attrs or {},
            confidence=0.95,
        )

    def rel(s: str, pred: str, o: str) -> None:
        add_relation(store, vocab, relation_uuid=uuid.uuid4(), subject_iri=s, predicate=pred, object_iri=o, confidence=0.9)

    from app.ontology.kernel.compile import collect_vocabularies

    vocab = collect_vocabularies(registry)["eia"]
    classes = etype_class_map(registry, "eia")

    ws = ent("ws", "waste_stream", "MCP矸石流")
    mine = ent("mine", "mine", "MCP矿")
    rel(mine, "generates_waste", ws)

    sp = ent("sp", "sensitive_point", "MCP敏感村")
    tm = ent("tm", "treatment_measure", "MCP沉淀池")
    st = ent("st", "standard_threshold", "MCP悬浮物阈值", attrs={"max": "70", "unit": "mg/L"})
    rel(sp, "protected_by", tm)
    rel(tm, "specified_by", st)


async def _call(name: str, args: dict) -> dict:
    result = await ontomcp.call_tool(name, args)
    return json.loads(result[0].text)


# ── 注册与接线 ────────────────────────────────────────────────────────


def test_four_eia_tools_registered():
    names = [t.name for t in ontomcp.TOOLS]
    for tool in ("query_entity", "check_consistency", "get_writing_context", "get_rule_violations"):
        assert names.count(tool) == 1, tool
    spec = {t.name: t for t in ontomcp.TOOLS}
    # EAI-CUSTOM(子项目 4): get_writing_context 扩展 chapter 模式——entity_name/chapter 至少一个，
    # 校验移入 handler（schema required 放开为 []）。
    assert spec["get_writing_context"].inputSchema["required"] == []
    assert spec["get_rule_violations"].inputSchema["properties"]["severity"]["enum"] == ["error", "warn", "info"]
    assert spec["query_entity"].inputSchema["required"] == []


@pytest.mark.asyncio
async def test_unknown_tool_still_reports():
    result = await ontomcp.call_tool("no_such_tool", {})
    assert result[0].text.startswith("Unknown tool: no_such_tool")


# ── query_entity ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_entity_requires_name_or_etype():
    d = await _call("query_entity", {})
    assert d["success"] is False and "至少" in d["error"]


@pytest.mark.asyncio
async def test_query_entity_unknown_etype_lists_hint():
    d = await _call("query_entity", {"etype": "no_such_etype"})
    assert d["success"] is False and "未知 etype" in d["error"]


@pytest.mark.asyncio
async def test_query_entity_by_name_with_neighborhood(memory_kernel):
    _populate(memory_kernel)
    d = await _call("query_entity", {"name": "MCP"})
    assert d["success"] is True and d["count"] >= 4
    mine = next(e for e in d["entities"] if e["name"] == "MCP矿")
    assert mine["etype"] == "mine"
    out_edges = mine["neighborhood"]["out"]
    assert any(e["predicate"] == "generates_waste" and e["target_name"] == "MCP矸石流" for e in out_edges)


@pytest.mark.asyncio
async def test_query_entity_by_etype_only(memory_kernel):
    _populate(memory_kernel)
    d = await _call("query_entity", {"etype": "standard_threshold"})
    assert d["success"] is True and d["count"] == 1
    assert d["entities"][0]["name"] == "MCP悬浮物阈值"


# ── check_consistency ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_consistency_reports_counts_and_samples(memory_kernel):
    _populate(memory_kernel)
    d = await _call("check_consistency", {})
    assert d["success"] is True
    assert d["total_violations"] >= 1
    assert d["by_severity"]["error"] >= 1
    gangue = next(r for r in d["results"] if r["rule_id"] == "rule_gangue_closure")
    assert gangue["violation_count"] == 1
    assert gangue["samples"] and "MCP矸石流" in gangue["samples"][0]


@pytest.mark.asyncio
async def test_check_consistency_empty_graph_zero(memory_kernel):
    d = await _call("check_consistency", {})
    assert d["success"] is True and d["total_violations"] == 0
    assert len(d["results"]) == 12


# ── get_writing_context ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_writing_context_requires_entity_name():
    # EAI-CUSTOM(子项目 4): entity_name/chapter 至少一个——空参仍结构化报错
    d = await _call("get_writing_context", {})
    assert d["success"] is False and "至少" in d["error"]


@pytest.mark.asyncio
async def test_writing_context_unknown_entity():
    d = await _call("get_writing_context", {"entity_name": "不存在的实体XYZ"})
    assert d["success"] is False and "未找到" in d["message"]


@pytest.mark.asyncio
async def test_writing_context_includes_two_hop_constraints(memory_kernel):
    """敏感村→沉淀池→阈值：裁决数值隔一层措施也应进 constraints（两跳扫描）。"""
    _populate(memory_kernel)
    d = await _call("get_writing_context", {"entity_name": "MCP敏感村"})
    assert d["success"] is True
    assert d["entity"]["etype"] == "sensitive_point"
    constraints = d["constraints"]
    assert len(constraints) == 1
    assert constraints[0]["etype"] == "standard_threshold"
    assert constraints[0]["attrs"]["max"] == "70"
    assert any(e["predicate"] == "protected_by" for e in d["neighborhood"]["out"])


# ── get_rule_violations ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rule_violations_filter_by_severity(memory_kernel):
    _populate(memory_kernel)
    d = await _call("get_rule_violations", {"severity": "error"})
    assert d["success"] is True
    assert d["matching_violations"] >= 1
    assert all(r["severity"] == "error" for r in d["results"])
    assert all(r["violation_count"] > 0 for r in d["results"])


# ── scope 归属库过滤（子项目 3.5 §2）──────────────────────────────────


def _populate_scopes(kernel: KernelService) -> None:
    """三归属实体（sample 显式 / project 显式 / 无标→缺省 sample）+ project 矸石流闭合违规。

    矸石流须有产生源而无去向（1!=0 过 HAVING）才有违规行——全空 (0==0) 不触发。
    """
    from app.ontology.kernel.compile import collect_vocabularies

    store = kernel.store
    vocab = collect_vocabularies(load_registry())["eia"]
    classes = etype_class_map(load_registry(), "eia")

    def ent(tag: str, etype: str, name: str, attrs: dict | None) -> str:
        return upsert_entity(store, vocab, class_name=classes[etype], entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"eia-scope-{tag}"), etype=etype, canonical_name=name, norm_name=name, attrs=attrs or {}, confidence=0.95)

    p = ent("p", "mine", "项目矿P", {"scope": "project"})
    ent("s", "mine", "样例矿S", {"scope": "sample"})
    ent("u", "mine", "无标矿U", None)
    ws = ent("ws", "waste_stream", "项目矸石流W", {"scope": "project"})
    add_relation(store, vocab, relation_uuid=uuid.uuid4(), subject_iri=p, predicate="generates_waste", object_iri=ws, confidence=0.9)
    # 跨 etype 重名对（org+place，避开 mine 查询断言）→ rule_entity_naming 违规行（按归一名分组，行内无实体 IRI）
    ent("n1", "org", "重名共享X", {"scope": "sample"})
    ent("n2", "place", "重名共享X", {"scope": "project"})


@pytest.mark.asyncio
async def test_query_entity_scope_sample_hits_sample_and_untagged(memory_kernel):
    """scope=sample：显式 sample + 未打标（缺省归属 sample）命中，project 不命中。"""
    _populate_scopes(memory_kernel)
    d = await _call("query_entity", {"etype": "mine", "scope": "sample"})
    names = {e["name"] for e in d["entities"]}
    assert names == {"样例矿S", "无标矿U"}
    assert all(e["scope"] == "sample" for e in d["entities"])


@pytest.mark.asyncio
async def test_query_entity_scope_project_only_explicit_rows(memory_kernel):
    """scope=project：只回显式 project 行；未打标语料（缺省 sample）不混入；B 库未填充 → domain_common 空。"""
    _populate_scopes(memory_kernel)
    d = await _call("query_entity", {"etype": "mine", "scope": "project"})
    assert [e["name"] for e in d["entities"]] == ["项目矿P"]
    d2 = await _call("query_entity", {"etype": "mine", "scope": "domain_common"})
    assert d2["success"] is True and d2["count"] == 0  # mine etype 无 B 库条目 → 空


def _populate_pattern(kernel: KernelService) -> None:
    """B 库已填充态（子项目 5）：一条 domain_pattern 蒸馏条目（scope=domain_common）。"""
    from app.ontology.kernel.compile import collect_vocabularies

    store = kernel.store
    vocab = collect_vocabularies(load_registry())["eia"]
    classes = etype_class_map(load_registry(), "eia")
    upsert_entity(
        store,
        vocab,
        class_name=classes["domain_pattern"],
        entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, "eia-scope-pat"),
        etype="domain_pattern",
        canonical_name="治理规律：矿井水→沉淀池",
        norm_name="治理规律：矿井水→沉淀池",
        attrs={"scope": "domain_common", "pattern_type": "治理", "support_count": "5"},
        confidence=0.95,
    )


@pytest.mark.asyncio
async def test_query_entity_scope_domain_common_hits_pattern(memory_kernel):
    """scope=domain_common：B 库 domain_pattern 条目按 etype/名称可查（子项目 5 蒸馏入图后的查询通道）。"""
    _populate_pattern(memory_kernel)
    d = await _call("query_entity", {"etype": "domain_pattern", "scope": "domain_common"})
    assert d["success"] is True and d["count"] == 1
    assert d["entities"][0]["name"] == "治理规律：矿井水→沉淀池" and d["entities"][0]["scope"] == "domain_common"
    d2 = await _call("query_entity", {"name": "治理规律", "scope": "domain_common"})
    assert d2["count"] == 1
    d3 = await _call("query_entity", {"etype": "domain_pattern", "scope": "sample"})
    assert d3["count"] == 0  # B 库条目不混入 sample 视角


@pytest.mark.asyncio
async def test_query_entity_scope_all_and_default_full(memory_kernel):
    """scope 缺省与显式 all 同义：三归属全量，不过滤。"""
    _populate_scopes(memory_kernel)
    d0 = await _call("query_entity", {"etype": "mine"})
    d1 = await _call("query_entity", {"etype": "mine", "scope": "all"})
    assert {e["name"] for e in d0["entities"]} == {e["name"] for e in d1["entities"]} == {"样例矿S", "项目矿P", "无标矿U"}
    assert d0["scope"] == "all" and d1["scope"] == "all"


@pytest.mark.asyncio
async def test_query_entity_scope_invalid_rejected(memory_kernel):
    _populate_scopes(memory_kernel)
    d = await _call("query_entity", {"etype": "mine", "scope": "bogus"})
    assert d["success"] is False and "scope" in d["error"]


@pytest.mark.asyncio
async def test_check_consistency_scope_post_filters_violations(memory_kernel):
    """违规行按涉事节点 scope 后置过滤：project 矸石流违规在 sample 视角被滤除、project/all 视角保留。"""
    _populate_scopes(memory_kernel)
    gangue_id = "rule_gangue_closure"

    sample_view = await _call("check_consistency", {"scope": "sample"})
    g_sample = next(r for r in sample_view["results"] if r["rule_id"] == gangue_id)
    assert g_sample["violation_count"] == 0

    project_view = await _call("check_consistency", {"scope": "project"})
    g_project = next(r for r in project_view["results"] if r["rule_id"] == gangue_id)
    assert g_project["violation_count"] == 1

    all_view = await _call("check_consistency", {})
    g_all = next(r for r in all_view["results"] if r["rule_id"] == gangue_id)
    assert g_all["violation_count"] == 1 and all_view["scope"] == "all"
    assert sample_view["total_violations"] <= all_view["total_violations"]  # 过滤视角总量单调不增


@pytest.mark.asyncio
async def test_check_consistency_scope_keeps_unattributable_rows(memory_kernel):
    """无 IRI 绑定的违规行（rule_entity_naming 按归一名分组）不可归属任何库——任何 scope 视角都保留。"""
    _populate_scopes(memory_kernel)
    naming_id = "rule_entity_naming"
    for scope in (None, "sample", "project", "domain_common"):
        args = {"scope": scope} if scope else {}
        view = await _call("check_consistency", args)
        row = next(r for r in view["results"] if r["rule_id"] == naming_id)
        assert row["violation_count"] == 1, (scope, row["violation_count"])


@pytest.mark.asyncio
async def test_check_consistency_scope_invalid_rejected(memory_kernel):
    d = await _call("check_consistency", {"scope": "nope"})
    assert d["success"] is False and "scope" in d["error"]


@pytest.mark.asyncio
async def test_rule_violations_filter_by_rule_id(memory_kernel):
    _populate(memory_kernel)
    d = await _call("get_rule_violations", {"rule_id": "rule_gangue_closure"})
    assert [r["rule_id"] for r in d["results"]] == ["rule_gangue_closure"]
    violation = d["results"][0]["violations"][0]
    assert violation["wsName"] == "MCP矸石流"
    assert "message" in violation


@pytest.mark.asyncio
async def test_rule_violations_empty_when_no_match(memory_kernel):
    _populate(memory_kernel)
    d = await _call("get_rule_violations", {"severity": "info"})
    assert d["matching_violations"] == 0 and d["results"] == []
