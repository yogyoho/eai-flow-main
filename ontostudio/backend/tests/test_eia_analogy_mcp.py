"""query_analogy MCP 工具（子项目 4 spec §4 + 子项目 5 扩展）：类比通道查询语义.

设计: docs/superpowers/specs/2026-09-30-coal-eia-mcp-integration-design.md §4

覆盖：sample 命中（含未打标缺省归属）/ B 库 domain_common（子项目 5：etype=domain_pattern
蒸馏规律条目入类比通道）/ C 库 project 不命中 / etype 过滤 / limit / source_report+邻接边
出参契约。打桩内存 kernel（与 test_eia_rules_mcp 同手法），不碰持久化 kernel、不碰真库。
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


@pytest.fixture()
def memory_kernel(monkeypatch):
    """进程内空 kernel 顶掉单例（与 test_eia_rules_mcp 同手法）。"""
    import app.ontology.kernel.service as svc

    saved = os.environ.pop("ONTOSTUDIO_KERNEL_PATH", None)
    fresh = KernelService()
    monkeypatch.setattr(svc, "_kernel", fresh)
    yield fresh
    if saved is not None:
        os.environ["ONTOSTUDIO_KERNEL_PATH"] = saved


def _populate(kernel: KernelService) -> None:
    """sample 类比链（矿井水→沉淀池→阈值）+ project/domain_common 排除组 + 未打标缺省组."""
    from app.ontology.kernel.compile import collect_vocabularies

    store = kernel.store
    vocab = collect_vocabularies(load_registry())["eia"]
    classes = etype_class_map(load_registry(), "eia")

    def ent(tag: str, etype: str, name: str, attrs: dict | None = None) -> str:
        return upsert_entity(
            store,
            vocab,
            class_name=classes[etype],
            entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"eia-analogy-{tag}"),
            etype=etype,
            canonical_name=name,
            norm_name=name,
            attrs=attrs or {},
            confidence=0.95,
        )

    def rel(s: str, pred: str, o: str) -> None:
        add_relation(store, vocab, relation_uuid=uuid.uuid4(), subject_iri=s, predicate=pred, object_iri=o, confidence=0.9)

    ws = ent("ws", "waste_stream", "样例矿井水", {"scope": "sample", "source_report": "yueerwan-planning", "quality": "SS超标"})
    tm = ent("tm", "treatment_measure", "样例沉淀池", {"scope": "sample", "source_report": "yueerwan-planning", "process": "混凝沉淀"})
    st = ent("st", "standard_threshold", "样例悬浮物阈值", {"scope": "sample", "source_report": "yueerwan-planning", "max": "70", "unit": "mg/L"})
    rel(ws, "treated_by", tm)
    rel(tm, "specified_by", st)
    # B 库蒸馏条目（子项目 5）：domain_pattern + analogous_to 实例→模式边，scope=domain_common 入类比通道
    pat = ent(
        "pat",
        "domain_pattern",
        "治理规律：样例矿井水→样例沉淀池",
        {"scope": "domain_common", "pattern_id": "dp-test0001", "pattern_type": "治理", "subject_name": "样例矿井水", "object_name": "样例沉淀池", "support_count": "5", "source_reports": "yueerwan-planning、hengcheng-planning"},
    )
    rel(ws, "analogous_to", pat)
    rel(tm, "analogous_to", pat)
    # C 库 project 归属：query_analogy 不得命中（走 query_entity scope=project）
    ent("pj", "waste_stream", "项目矿井水", {"scope": "project", "source_report": "current-project"})
    # 未打标 → 缺省按 sample 归属，命中
    ent("un", "mine", "无标样例矿", None)
    ent("m1", "mine", "样例矿甲", {"scope": "sample", "source_report": "r1"})
    ent("m2", "mine", "样例矿乙", {"scope": "sample", "source_report": "r2"})


async def _call(name: str, args: dict) -> dict:
    result = await ontomcp.call_tool(name, args)
    return json.loads(result[0].text)


# ── 注册与接线 ────────────────────────────────────────────────────────


def test_query_analogy_registered():
    names = [t.name for t in ontomcp.TOOLS]
    assert names.count("query_analogy") == 1
    spec = {t.name: t for t in ontomcp.TOOLS}["query_analogy"]
    assert spec.inputSchema["required"] == []
    assert set(spec.inputSchema["properties"]) == {"etype", "label_contains", "limit"}


# ── 查询语义 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_etype_or_label(memory_kernel):
    d = await _call("query_analogy", {})
    assert d["success"] is False and "至少" in d["error"]


@pytest.mark.asyncio
async def test_unknown_etype_rejected(memory_kernel):
    d = await _call("query_analogy", {"etype": "no_such_etype"})
    assert d["success"] is False and "未知 etype" in d["error"]


@pytest.mark.asyncio
async def test_sample_hit_with_source_report_and_adjacency(memory_kernel):
    """sample 命中：source_report 必带 + 邻接边带谓词/对端名/对端属性（含 B 库 analogous_to 边）。"""
    _populate(memory_kernel)
    d = await _call("query_analogy", {"label_contains": "样例矿井水"})
    # 名称子串同时命中样例实体与其 B 库规律条目（「治理规律：样例矿井水→…」）——按 etype 取目标行
    assert d["success"] is True and d["scope"] == "sample+domain_common" and d["count"] == 2
    ent = next(e for e in d["entities"] if e["etype"] == "waste_stream")
    assert ent["label"] == "样例矿井水"
    assert ent["source_report"] == "yueerwan-planning"  # 类比值溯源到"哪份报告"
    out_edges = ent["adjacency"]["out"]
    edge = next(e for e in out_edges if e["predicate"] == "treated_by")
    assert edge["peer_name"] == "样例沉淀池" and edge["peer_etype"] == "treatment_measure"
    assert edge["peer_attrs"]["process"] == "混凝沉淀"
    pat_edge = next(e for e in out_edges if e["predicate"] == "analogous_to")
    assert pat_edge["peer_etype"] == "domain_pattern"  # 实例→模式边在邻接出参可见
    # 身份/归属属性不混入业务 attrs
    assert "source_report" not in ent["attrs"] and "scope" not in ent["attrs"]
    assert ent["attrs"]["quality"] == "SS超标"


@pytest.mark.asyncio
async def test_pattern_entry_via_etype_and_label(memory_kernel):
    """B 库蒸馏条目（子项目 5）：etype=domain_pattern / label_contains 均可查到 scope=domain_common 条目。"""
    _populate(memory_kernel)
    for args in ({"etype": "domain_pattern"}, {"label_contains": "治理规律"}):
        d = await _call("query_analogy", args)
        assert d["success"] is True and d["count"] == 1, args
        ent = d["entities"][0]
        assert ent["etype"] == "domain_pattern" and ent["scope"] == "domain_common"
        assert ent["source_report"] == "yueerwan-planning、hengcheng-planning"  # B 库条目 source_reports 回退溯源字段
        assert ent["attrs"]["pattern_type"] == "治理" and ent["attrs"]["support_count"] == "5"
        assert ent["attrs"]["pattern_id"] == "dp-test0001"
        # 模式节点邻接：实例→模式边回填对端名/对端类型
        in_peers = {e["peer_name"]: e["peer_etype"] for e in ent["adjacency"]["in"] if e["predicate"] == "analogous_to"}
        assert in_peers == {"样例矿井水": "waste_stream", "样例沉淀池": "treatment_measure"}


@pytest.mark.asyncio
async def test_project_scope_still_excluded(memory_kernel):
    """C 库 project 仍不命中（走 query_entity scope=project）；未打标按缺省归属 sample 命中。"""
    _populate(memory_kernel)
    d = await _call("query_analogy", {"etype": "waste_stream"})
    names = {e["label"] for e in d["entities"]}
    assert names == {"样例矿井水"}  # 项目矿井水（project）排除
    d2 = await _call("query_analogy", {"label_contains": "无标样例矿"})
    assert d2["count"] == 1 and d2["entities"][0]["scope"] == "sample"
    assert d2["entities"][0]["source_report"] == "unknown"  # 未打标 fallback unknown，字段必在场


@pytest.mark.asyncio
async def test_etype_filter(memory_kernel):
    _populate(memory_kernel)
    d = await _call("query_analogy", {"etype": "standard_threshold"})
    assert d["count"] == 1
    ent = d["entities"][0]
    assert ent["label"] == "样例悬浮物阈值" and ent["source_report"] == "yueerwan-planning"
    assert ent["attrs"]["max"] == "70" and ent["attrs"]["unit"] == "mg/L"


@pytest.mark.asyncio
async def test_limit(memory_kernel):
    _populate(memory_kernel)
    # label_contains "样例矿" 命中 5 条（样例矿井水/无标样例矿/样例矿甲/样例矿乙 + B 库规律条目「治理规律：样例矿井水→…」）
    full = await _call("query_analogy", {"label_contains": "样例矿"})
    assert full["count"] == 5
    capped = await _call("query_analogy", {"label_contains": "样例矿", "limit": 1})
    assert capped["count"] == 1


@pytest.mark.asyncio
async def test_no_hit_empty_result(memory_kernel):
    _populate(memory_kernel)
    d = await _call("query_analogy", {"label_contains": "不存在的实体XYZ"})
    assert d["success"] is True and d["count"] == 0 and d["entities"] == []
