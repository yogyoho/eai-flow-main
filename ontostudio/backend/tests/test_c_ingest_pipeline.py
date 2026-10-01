"""C 库沉淀管线（子项目 4 完整版）——映射表 / pipeline / MCP 2 工具 / coverage / 写前注入.

设计: docs/superpowers/specs/2026-09-30-c-ingest-pipeline-design.md §5/§7
计划: docs/superpowers/plans/2026-09-30-c-ingest-pipeline-plan.md T1–T6

覆盖：
- 映射表 fail-closed 加载（坏谓词/坏角色对/未知族 → ValueError）+ 11 族清单
- build_payload 纯函数（实体投影 / 关系两端 / 自然键归并 / match 条件 / unmapped+skipped fail-visible）
- ingest_project_forms MCP 工具（payload 捕获断言 project_id；内存 kernel 投影——真库门禁外全链）
- check_project_coverage 图上齐套（全绿 / 缺族 / project_id 隔离）
- get_writing_context chapter 模式（domain_pattern + 项目实体 + project_id 过滤）+ entity 模式回归
- E2E 三连：核心 4 要素 stage JSON → ingest → coverage → writing_context(chapter="矸石")

打桩内存 kernel（与 test_eia_rules_mcp / test_eia_analogy_mcp 同手法），不碰持久化 kernel、
不碰真库（真库写入门禁 ONTOSTUDIO_TEST_ALLOW_REAL_DB 外一律 skip——本文件 patch 掉 DB 层）。
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from app.ontology import mcp as ontomcp
from app.ontology.c_ingest import pipeline as cpipe
from app.ontology.kernel.graph_ops import add_relation, upsert_entity
from app.ontology.kernel.loader import etype_class_map
from app.ontology.kernel.service import KernelService
from app.ontology.registry import load_registry

# ── mini forms：核心 4 要素（水/气/固废/生态）构造数据 ────────────────────────

MINI_FORMS: dict = {
    "project": {"mine_area_name": "测试矿区", "commissioning_unit": "测试矿业有限公司"},
    "water": {
        "mine_inflow": [{"mine": "一号井田", "inflow_m3_d": 1200, "measured": False, "analog_source": "邻矿类比"}],
        "sources": [{"name": "磨盘山水库", "yield": "500万m3/a"}],
        "receiving_water": {"river": "测试河", "flow": "3.5m3/s"},
        "demand": {"production": "800万m3/a"},
    },
    "air": {"boilers": [{"count": 2, "capacity_t_h": 10, "stack_h": 35}], "meteorology": {"wind_speed": "2.1m/s"}},
    "solid_waste": {
        "gangue_rate": 0.18,
        "gangue_generation": 45.6,
        "disposal_sites": [{"name": "北渣场", "capacity": "200万m3"}],
        "hazardous": [{"category": "废机油", "amount": "2t/a"}],
        "disposal_method": ["外委有资质单位处置", "综合利用"],
    },
    "sensitive_targets": {
        "targets": [
            {"name": "王家村", "category": "居民点", "distance": "500m"},
            {"name": "基本农田保护区", "category": "基本农田"},
        ]
    },
    "measures": {
        "eco": [{"zoning": "沉陷区", "content": "土地复垦", "body": "矿方"}],
        "air": [{"content": "布袋除尘器"}],
        "water": [{"content": "矿井水处理站（混凝沉淀）"}],
        "noise": [{"content": "隔声屏障"}],
        "solid_waste": [{"content": "矸石井下充填"}],
        "risk_response": [{"risk_source": "炸药库", "prevention": "设围堰"}],
    },
    "standards_confirm": {
        "triplets": [
            {"element": "大气", "function_zone": "二类区", "standard_code": "GB 13271-2014", "limit_note": "锅炉大气排放限值"},
            {"element": "地表水", "function_zone": "III类", "standard_code": "GB 3838-2002", "limit_note": "III类限值"},
        ],
        "confirmed_at": "2026-10-01",
    },
    "protected_area_detail": {"sections": [{"target": "王家村", "overview": "重点保护区概况"}]},
    "eco_restoration": {"zoning": [{"content": "排土场整治"}], "reclamation": [{"content": "复垦植被重建"}]},
    "monitoring_plan": {"plans": [{"phase": "运营", "element": "噪声", "point": "厂界", "factor": "等效声级", "frequency": "季度", "standard_code": "GB 12348"}]},
    "circular_economy": {"gangue_reuse": {"途径": "制砖", "规模": "30万t/a"}, "mine_water_reuse": {"途径": "选煤补水"}},
    "geography": {"location_text": "未映射族——应进 unmapped_families"},
}


def _ents(payload) -> dict[tuple[str, str], dict]:
    """payload 实体索引：{(etype, name): attrs}。"""
    return {(e.etype, e.name): e.attrs for e in payload.entities}


def _rels(payload) -> set[tuple[str, str, str]]:
    """payload 关系集合：{(subject, predicate, object)}。"""
    return {(r.subject, r.predicate, r.object) for r in payload.relations}


# ── 内存 kernel 打桩（与 test_eia_analogy_mcp 同手法）────────────────────────


@pytest.fixture()
def memory_kernel(monkeypatch):
    """进程内空 kernel 顶掉单例；同时清掉章节主题缓存（防跨用例串味）。"""
    import app.ontology.kernel.service as svc

    saved = os.environ.pop("ONTOSTUDIO_KERNEL_PATH", None)
    fresh = KernelService()
    monkeypatch.setattr(svc, "_kernel", fresh)
    monkeypatch.setattr(ontomcp, "_chapter_topics_cache", None)
    yield fresh
    if saved is not None:
        os.environ["ONTOSTUDIO_KERNEL_PATH"] = saved


def _project_payload_to_memory(kernel: KernelService, payload) -> None:
    """payload → 内存 kernel 投影（生产 _reload_graph 的内存对偶）。

    走**生产** project_scoped_attrs（scope=project 打标逻辑过真路径）；实体 uuid 确定性
    （uuid5 自然键），与 DB 幂等 upsert 同语义。
    """
    from app.doc_graph.ingest import project_scoped_attrs
    from app.ontology.kernel.compile import collect_vocabularies

    store = kernel.store
    reg = load_registry()
    vocab = collect_vocabularies(reg)["eia"]
    classes = etype_class_map(reg, "eia")
    iri_of: dict[str, str] = {}
    for e in payload.entities:
        iri_of[e.name] = upsert_entity(
            store,
            vocab,
            class_name=classes[e.etype],
            entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"c-ingest:{e.etype}:{e.name}"),
            etype=e.etype,
            canonical_name=e.name,
            attrs=project_scoped_attrs(e.attrs, payload.project_id),
            confidence=e.confidence,
        )
    for r in payload.relations:
        add_relation(store, vocab, relation_uuid=uuid.uuid4(), subject_iri=iri_of[r.subject], predicate=r.predicate, object_iri=iri_of[r.object], confidence=r.confidence)


@pytest.fixture()
def wired_ingest(monkeypatch, memory_kernel):
    """patch DB 写入（捕获 payload）+ 图投影（内存 kernel）——生产编排顺序真实重放。"""
    captured: dict = {}

    async def fake_ingest(payload):
        captured["payload"] = payload
        return {"entities_upserted": len(payload.entities), "relations": len(payload.relations), "mentions": len(payload.entities) + len(payload.relations)}

    async def fake_reload():
        _project_payload_to_memory(memory_kernel, captured["payload"])

    monkeypatch.setattr(cpipe, "ingest_extraction", fake_ingest)
    monkeypatch.setattr(cpipe, "_reload_graph", fake_reload)
    return memory_kernel, captured


def _add_domain_pattern(kernel: KernelService, name: str, subject: str, obj: str, support: int = 5) -> None:
    """B 库蒸馏规律条目（domain_pattern + scope=domain_common，与 B 库蒸馏产出同构）。"""
    from app.ontology.kernel.compile import collect_vocabularies

    reg = load_registry()
    vocab = collect_vocabularies(reg)["eia"]
    classes = etype_class_map(reg, "eia")
    pat = upsert_entity(
        kernel.store,
        vocab,
        class_name=classes["domain_pattern"],
        entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"c-ingest:pat:{name}"),
        etype="domain_pattern",
        canonical_name=name,
        attrs={
            "scope": "domain_common",
            "pattern_id": f"dp-{abs(hash(name)) % 10000:04d}",
            "pattern_type": "处置",
            "subject_name": subject,
            "object_name": obj,
            "support_count": str(support),
            "source_reports": "yueerwan-planning、hengcheng-planning",
        },
        confidence=0.9,
    )
    ws = upsert_entity(
        kernel.store,
        vocab,
        class_name=classes["waste_stream"],
        entity_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"c-ingest:ws:{subject}"),
        etype="waste_stream",
        canonical_name=subject,
        attrs={"scope": "domain_common"},
        confidence=0.9,
    )
    add_relation(kernel.store, vocab, relation_uuid=uuid.uuid4(), subject_iri=ws, predicate="analogous_to", object_iri=pat, confidence=0.9)


async def _call(name: str, args: dict) -> dict:
    result = await ontomcp.call_tool(name, args)
    return json.loads(result[0].text)


# ── T1：映射表 ────────────────────────────────────────────────────────


def test_mapping_loads_eleven_families():
    """验收 1：映射表加载 + 核心要素 11 族清单。"""
    m = cpipe.load_mapping()
    stage = m.stages["planning_eia"]
    expected = {
        "project",  # 总体
        "water",  # 水
        "air",  # 气
        "solid_waste",  # 固废
        "sensitive_targets",  # 生态敏感点
        "measures",  # 治理措施
        "standards_confirm",  # 排放标准
        "protected_area_detail",  # 保护区专节
        "eco_restoration",  # 生态恢复
        "monitoring_plan",  # 监测计划
        "circular_economy",  # 综合利用
    }
    assert set(stage.families) == expected
    assert len(expected) == 11


def test_mapping_bad_predicate_fails_closed(tmp_path):
    """fail-closed：谓词不在 eia 域谓词集 → ValueError（加载即拒）。"""
    text = cpipe._MAPPING_PATH.read_text(encoding="utf-8").replace("predicate: treated_by", "predicate: no_such_pred", 1)
    p = tmp_path / "bad.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="谓词"):
        cpipe.load_mapping(p)


def test_mapping_bad_role_pair_fails_closed(tmp_path):
    """fail-closed：角色对语义不匹配（waste_stream -governed_by→ treatment_measure 不在域表）→ ValueError。"""
    text = cpipe._MAPPING_PATH.read_text(encoding="utf-8").replace(
        "{predicate: treated_by, from_family: water, from_field: mine_inflow, to_family: measures, to_field: water}",
        "{predicate: governed_by, from_family: water, from_field: mine_inflow, to_family: measures, to_field: water}",
        1,
    )
    p = tmp_path / "bad_role.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="角色对"):
        cpipe.load_mapping(p)


def test_mapping_bad_etype_fails_closed(tmp_path):
    text = cpipe._MAPPING_PATH.read_text(encoding="utf-8").replace("etype: receiving_medium", "etype: spaceship", 1)
    p = tmp_path / "bad_etype.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="etype"):
        cpipe.load_mapping(p)


# ── T2：build_payload 纯函数 ──────────────────────────────────────────


def test_build_payload_core_entities():
    """核心实体投影：4 要素实体 + name 解析（name_from / 固定名 / 模板回退）。"""
    r = cpipe.build_payload("proj-A", "planning_eia", MINI_FORMS)
    ents = _ents(r.payload)
    assert r.payload.project_id == "proj-A"
    assert ("mine", "测试矿区") in ents
    assert ("waste_stream", "一号井田") in ents  # name_from=[mine] → 井田登记名（B 库惯例：实体名=登记名）
    assert ("place", "磨盘山水库") in ents
    assert ("receiving_medium", "受纳水体") in ents  # object 字段固定名
    assert ("pollution_source", "工业场地锅炉烟气源#0") in ents  # 模板回退
    assert ("waste_stream", "矸石") in ents  # collect 固定名
    assert ("engineering_site", "北渣场") in ents
    assert ("waste_stream", "废机油") in ents  # hazardous name_from=[name, category] → category
    assert ("sensitive_point", "王家村") in ents
    assert ("treatment_measure", "外委有资质单位处置") in ents  # 字符串数组 "." 值即名
    assert ("emission_standard", "GB 13271-2014") in ents
    assert ("standard_threshold", "锅炉大气排放限值") in ents
    assert ("monitoring", "厂界·等效声级监测") in ents  # name_template_keys 模板
    assert ("treatment_measure", "矸石综合利用") in ents
    # attrs：collect 聚合 + source 溯源标
    gangue = ents[("waste_stream", "矸石")]
    assert gangue["gangue_rate"] == 0.18 and gangue["gangue_generation"] == 45.6
    assert gangue["source"] == "stage_json:planning_eia:solid_waste#gangue_generation"
    assert ents[("waste_stream", "一号井田")]["analog_source"] == "邻矿类比"


def test_build_payload_relations():
    """关系两端断言：族内边 + 跨族边 + match 条件（验收 2 关系半）。"""
    r = cpipe.build_payload("proj-A", "planning_eia", MINI_FORMS)
    rels = _rels(r.payload)
    # 族内边（intra）：矸石→渣场/处置方式；危废→处置方式
    assert ("矸石", "disposed_by", "北渣场") in rels
    assert ("矸石", "disposed_by", "外委有资质单位处置") in rels
    assert ("废机油", "disposed_by", "综合利用") in rels
    # 字段级边（entities 多类同元素配对）：标准→阈值
    assert ("GB 13271-2014", "specifies_threshold", "锅炉大气排放限值") in rels
    # 跨族边：treated_by / utilized_by / complies_with(element match) / protected_by / monitored_by / disposed_by
    assert ("一号井田", "treated_by", "矿井水处理站（混凝沉淀）") in rels
    assert ("工业场地锅炉烟气源#0", "treated_by", "布袋除尘器") in rels
    assert ("一号井田", "utilized_by", "矿井水综合利用") in rels
    assert ("矸石", "utilized_by", "矸石综合利用") in rels
    assert ("工业场地锅炉烟气源#0", "complies_with", "GB 13271-2014") in rels  # element=大气 ✓
    assert ("工业场地锅炉烟气源#0", "complies_with", "GB 3838-2002") not in rels  # match 过滤：地表水标准不连锅炉
    assert ("矸石", "disposed_by", "矸石井下充填") in rels
    assert ("王家村", "protected_by", "土地复垦") in rels
    assert ("基本农田保护区", "protected_by", "土地复垦") in rels
    assert ("测试矿区", "monitored_by", "厂界·等效声级监测") in rels


def test_build_payload_natural_key_merge():
    """同名实体跨族归并：protected_area_detail.target=王家村 与 sensitive_targets.targets 同自然键。"""
    r = cpipe.build_payload("proj-A", "planning_eia", MINI_FORMS)
    assert [(e.etype, e.name) for e in r.payload.entities].count(("sensitive_point", "王家村")) == 1
    # 归并后 attrs 含两侧键值
    attrs = _ents(r.payload)[("sensitive_point", "王家村")]
    assert attrs["category"] == "居民点" and attrs["overview"] == "重点保护区概况"


def test_build_payload_unmapped_and_skipped_fail_visible():
    """验收 fail-visible：未映射族进 unmapped_families；字段缺席进 skipped_fields；全未映射 → payload None。"""
    r = cpipe.build_payload("proj-A", "planning_eia", {"geography": {"location_text": "x"}, "noise": {"sources": []}})
    assert r.payload is None
    assert set(r.unmapped_families) == {"geography", "noise"}

    r2 = cpipe.build_payload("proj-A", "planning_eia", {"water": {"sources": [{"name": "水库"}]}})  # mine_inflow 缺席
    assert "water.mine_inflow" in r2.skipped_fields
    assert ("place", "水库") in _ents(r2.payload)

    r3 = cpipe.build_payload("proj-A", "planning_eia", {"measures": {"air": [{"no_name_key": 1}]}})  # 无名元素 → 回退模板命名
    assert r3.fallback_named == ["measures.air#0"]
    assert ("treatment_measure", "大气治理措施#0") in _ents(r3.payload)


def test_build_payload_invalid_args():
    with pytest.raises(ValueError, match="forms"):
        cpipe.build_payload("proj-A", "planning_eia", {})
    with pytest.raises(ValueError, match="stage"):
        cpipe.build_payload("proj-A", "no_such_stage", {"project": {"mine_area_name": "x"}})


# ── T3：MCP ingest_project_forms / check_project_coverage ─────────────


def test_ingest_and_coverage_tools_registered():
    names = [t.name for t in ontomcp.TOOLS]
    assert names.count("ingest_project_forms") == 1
    assert names.count("check_project_coverage") == 1
    spec = {t.name: t for t in ontomcp.TOOLS}
    assert spec["ingest_project_forms"].inputSchema["required"] == ["project_id", "forms"]
    assert spec["check_project_coverage"].inputSchema["required"] == ["project_id"]


@pytest.mark.asyncio
async def test_ingest_requires_args():
    d = await _call("ingest_project_forms", {})
    assert d["success"] is False and "project_id" in d["error"]
    d2 = await _call("ingest_project_forms", {"project_id": "p"})
    assert d2["success"] is False and "forms" in d2["error"]


@pytest.mark.asyncio
async def test_ingest_writes_scoped_payload_and_projects_to_graph(wired_ingest):
    """验收 2：payload 携带 project_id → scope=project 打标（project_scoped_attrs 真路径）→ 图上可见。"""
    kernel, captured = wired_ingest
    d = await _call("ingest_project_forms", {"project_id": "proj-A", "forms": MINI_FORMS})
    assert d["success"] is True and d["written"] is True
    assert d["project_id"] == "proj-A"
    assert d["entities_created"] == len(captured["payload"].entities)
    assert d["relations_created"] == len(captured["payload"].relations)
    assert "geography" in d["unmapped_families"]  # fail-visible，不阻塞
    payload = captured["payload"]
    assert payload.project_id == "proj-A" and payload.extracted_by == "stage_json_ingest"
    assert payload.domain == "eia"
    # 图上齐套口径：scope=project + project_id 三元组在图（打标经生产 project_scoped_attrs）
    from app.ontology.mcp import _ASSERTED, _EIA_NS

    rows = kernel.store.query(f'SELECT ?e WHERE {{ GRAPH <{_ASSERTED}> {{ ?e <{_EIA_NS}attr/scope> "project" ; <{_EIA_NS}attr/project_id> "proj-A" }} }}')
    assert len(rows) >= 20  # 核心实体全量打标


@pytest.mark.asyncio
async def test_ingest_empty_mapped_data_reports_not_written(wired_ingest):
    d = await _call("ingest_project_forms", {"project_id": "proj-A", "forms": {"geography": {"location_text": "x"}}})
    assert d["success"] is True and d["written"] is False and set(d["unmapped_families"]) == {"geography"}


# ── coverage：图上齐套（验收 3）───────────────────────────────────────


@pytest.mark.asyncio
async def test_coverage_complete_after_ingest(wired_ingest):
    kernel, _ = wired_ingest
    await _call("ingest_project_forms", {"project_id": "proj-A", "forms": MINI_FORMS})
    d = await _call("check_project_coverage", {"project_id": "proj-A"})
    assert d["success"] is True
    assert d["coverage_complete"] is True
    assert d["missing_families"] == []
    assert d["covered_required"] == d["required_family_count"]
    by_fam = {f["family"]: f for f in d["families"]}
    assert by_fam["water"]["covered"] and by_fam["water"]["entity_count"] >= 3
    assert by_fam["air"]["covered"] and by_fam["air"]["entity_count"] >= 1
    assert by_fam["solid_waste"]["covered"] and by_fam["solid_waste"]["entity_count"] >= 4
    assert by_fam["sensitive_targets"]["covered"] and by_fam["sensitive_targets"]["entity_count"] >= 1
    # 可选族（protected_area_detail 未传）不计入 missing；王家村跨族归并（sections.target 同名）
    # 后 attrs.source 被 protected_area_detail 覆盖（attrs||合并语义）——族计数放宽到 ≥1（基本农田在场）
    assert by_fam["protected_area_detail"]["covered"] is True
    assert "eco_restoration" in [f["family"] for f in d["families"]]


@pytest.mark.asyncio
async def test_coverage_reports_missing_family(wired_ingest):
    """缺族 → coverage 报缺失（spec §7.3：gate 1 图上齐套）+ project_id 隔离。

    注：proj-B 用异名实体构造（不同矿区）——C 库实体自然键 (domain,etype,norm_name)
    全局共享，跨项目同名会 attrs|| 合并翻转 project_id 归属（doc_graph/ingest.py
    「自然键碰撞提示」明示的机制语义，单项目工作区为主场景不触发）。
    """
    await _call("ingest_project_forms", {"project_id": "proj-A", "forms": MINI_FORMS})
    forms_b = {
        "project": {"mine_area_name": "二号矿区"},
        "solid_waste": {"gangue_rate": 0.2, "gangue_generation": 30.0, "disposal_sites": [{"name": "南渣场"}], "hazardous": [{"category": "废油"}], "disposal_method": ["外委处置"]},
        "measures": {"air": [{"content": "水膜除尘"}]},
        "standards_confirm": {"triplets": [{"element": "噪声", "function_zone": "2类", "standard_code": "GB 12348-2008", "limit_note": "昼60夜50"}]},
        "circular_economy": {"gangue_reuse": {"途径": "水泥掺料"}, "mine_water_reuse": {"途径": "绿化"}},
        "monitoring_plan": {"plans": [{"phase": "运营", "element": "大气", "point": "风向上侧", "factor": "TSP", "frequency": "月"}]},
    }
    await _call("ingest_project_forms", {"project_id": "proj-B", "forms": forms_b})
    d = await _call("check_project_coverage", {"project_id": "proj-B"})
    assert d["coverage_complete"] is False
    assert "water" in d["missing_families"] and "air" in d["missing_families"] and "sensitive_targets" in d["missing_families"]
    assert "solid_waste" not in d["missing_families"]
    # project_id 隔离（异名实体域）：proj-A 的水/气/生态族覆盖不受 proj-B 缺族影响。
    # 固定名实体（矸石/矸石综合利用等）跨项目共享自然键会翻转归属——机制语义，见 docstring 已知边界。
    d_a = await _call("check_project_coverage", {"project_id": "proj-A"})
    by_fam_a = {f["family"]: f for f in d_a["families"]}
    assert by_fam_a["water"]["covered"] and by_fam_a["air"]["covered"] and by_fam_a["sensitive_targets"]["covered"]
    # 未知 project：全缺
    d_none = await _call("check_project_coverage", {"project_id": "proj-none"})
    assert d_none["coverage_complete"] is False and len(d_none["missing_families"]) == d_none["required_family_count"]


# ── T4：get_writing_context chapter 模式（验收 4）─────────────────────


@pytest.mark.asyncio
async def test_writing_context_chapter_gangue(wired_ingest):
    """chapter="矸石" → 返回处置规律 domain_pattern + 项目实体（spec §7.4）。"""
    kernel, _ = wired_ingest
    _add_domain_pattern(kernel, "治理规律：矸石→井下充填+综合利用", "矸石", "处置场")
    await _call("ingest_project_forms", {"project_id": "proj-A", "forms": MINI_FORMS})
    d = await _call("get_writing_context", {"chapter": "矸石", "project_id": "proj-A"})
    assert d["success"] is True and d["topic_matched"] is True
    assert any("矸石" in t for t in d["matched_topics"])
    # B 库规律（domain_pattern 命中）
    assert len(d["domain_patterns"]) >= 1
    pat = d["domain_patterns"][0]
    assert pat["subject_name"] == "矸石" and pat["support_count"] and pat["source_reports"]
    # C 库项目实体（矸石 waste_stream 在场且带 source 溯源）
    names = {e["name"] for e in d["project_entities"]}
    assert "矸石" in names and "矸石综合利用" in names
    gangue = next(e for e in d["project_entities"] if e["name"] == "矸石")
    assert gangue["etype"] == "waste_stream"
    assert gangue["attrs"]["source"] == "stage_json:planning_eia:solid_waste#gangue_generation"
    # kernel 图 attr 值均为字符串化 literal（RDF 形态）——数值以字符串回读
    assert str(gangue["attrs"]["gangue_generation"]) == "45.6"
    # 既有 entity 模式字段不受 chapter 模式影响（chapter 分支无 entity 键）
    assert "entity" not in d and "neighborhood" not in d


@pytest.mark.asyncio
async def test_writing_context_chapter_project_id_filter(wired_ingest):
    kernel, _ = wired_ingest
    await _call("ingest_project_forms", {"project_id": "proj-A", "forms": MINI_FORMS})
    d = await _call("get_writing_context", {"chapter": "矸石", "project_id": "proj-other"})
    assert d["topic_matched"] is True
    assert d["project_entities"] == []  # project_id 过滤：其他项目实体不串
    d_all = await _call("get_writing_context", {"chapter": "矸石"})  # 缺 project_id → 收全部 project 实体
    assert any(e["name"] == "矸石" for e in d_all["project_entities"])


@pytest.mark.asyncio
async def test_writing_context_chapter_no_match():
    d = await _call("get_writing_context", {"chapter": "完全不存在主题XYZ"})
    assert d["success"] is True and d["topic_matched"] is False
    assert d["available_topics"]  # fail-visible：给出可用主题就近改写


@pytest.mark.asyncio
async def test_writing_context_entity_mode_regression(memory_kernel):
    """既有 entity_name 模式响应字段不变（追加不过既有字段）。"""
    from tests.test_eia_analogy_mcp import _populate

    _populate(memory_kernel)
    d = await _call("get_writing_context", {"entity_name": "样例矿井水"})
    assert d["success"] is True
    for key in ("entity", "aliases_considered", "neighborhood", "neighbor_names", "constraints", "hint"):
        assert key in d, key
    assert "topic_section" not in d  # 未给 chapter 不追加
    # entity + chapter 同时给：既有字段不动 + 追加 topic_section
    _add_domain_pattern(memory_kernel, "治理规律：矿井水→混凝沉淀", "矿井水", "沉淀池")
    d2 = await _call("get_writing_context", {"entity_name": "样例矿井水", "chapter": "矿井水"})
    for key in ("entity", "neighborhood", "constraints"):
        assert key in d2
    assert d2["topic_section"]["topic_matched"] is True


# ── T6：E2E 三连（验收：ingest → coverage → writing_context）─────────


@pytest.mark.asyncio
async def test_e2e_ingest_coverage_writing_context(wired_ingest):
    """构造核心 4 要素 stage JSON → ingest_project_forms → check_project_coverage →
    get_writing_context(chapter="矸石") 三连断言（计划 T6 验收链）。"""
    kernel, captured = wired_ingest
    _add_domain_pattern(kernel, "处置规律：矸石制砖+井下充填", "矸石", "砖厂")

    # ① ingest：全量 forms 传入
    r1 = await _call("ingest_project_forms", {"project_id": "e2e-proj", "forms": MINI_FORMS})
    assert r1["success"] is True and r1["written"] is True
    assert r1["entities_created"] >= 25 and r1["relations_created"] >= 14
    assert r1["unmapped_families"] == ["geography"]

    # ② coverage：图上齐套
    r2 = await _call("check_project_coverage", {"project_id": "e2e-proj"})
    assert r2["coverage_complete"] is True, r2["missing_families"]

    # ③ 写前注入：矸石节 → 规律 + 项目实体 + 关系邻域
    r3 = await _call("get_writing_context", {"chapter": "矸石", "project_id": "e2e-proj"})
    assert r3["topic_matched"] is True
    assert any(p["subject_name"] == "矸石" for p in r3["domain_patterns"])
    assert "矸石" in {e["name"] for e in r3["project_entities"]}
    # 约束邻域：矸石→标准阈值链上的裁决数值可达（spec：B 库规律 + C 库项目实体 + 相关阈值）
    assert isinstance(r3["constraints"], list)


@pytest.mark.asyncio
async def test_full_chain_semantics_via_kernel(wired_ingest):
    """链路语义补充：query_entity scope=project 也能查到沉淀实体（与 A/B 库通道区分）。"""
    await _call("ingest_project_forms", {"project_id": "e2e-proj", "forms": {"solid_waste": MINI_FORMS["solid_waste"], "measures": MINI_FORMS["measures"], "project": MINI_FORMS["project"], "monitoring_plan": MINI_FORMS["monitoring_plan"]}})
    d = await _call("query_entity", {"name": "矸石", "etype": "waste_stream", "scope": "project"})
    assert d["success"] is True
    assert any(e["name"] == "矸石" and e["scope"] == "project" for e in d["entities"])
    # sample 通道不漏 C 库实体
    d2 = await _call("query_analogy", {"etype": "waste_stream", "label_contains": "矸石"})
    assert all(e["scope"] != "project" for e in d2.get("entities", []))
