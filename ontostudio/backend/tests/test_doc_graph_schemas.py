"""doc_graph 抽取 schema 测试——extra=forbid fail-closed 与交叉引用/谓词角色校验."""

import copy
import inspect
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from app.doc_graph import schemas
from app.doc_graph.ingest import ingest_extraction
from app.doc_graph.schemas import BidExtraction, EiaExtraction, ExtractionPayload

_MIN_ENT = {
    "etype": "project",
    "name": "横城煤矿东翼回风大巷工程",
    "mention": {"document_id": "doc-001", "quote": "横城煤矿东翼回风大巷工程施工招标"},
}


def _payload(**over):
    base = {
        "domain": "bid",
        "entities": [copy.deepcopy(_MIN_ENT), {"etype": "bidder", "name": "山西煤机集团", "confidence": 0.9, "mention": {"document_id": "doc-001"}}],
        "relations": [{"predicate": "bidder_of_project", "subject": "山西煤机集团", "object": "横城煤矿东翼回风大巷工程", "mention": {"document_id": "doc-001"}}],
    }
    base.update(over)
    return base


def test_valid_roundtrip():
    p = BidExtraction.model_validate(_payload())
    assert len(p.entities) == 2 and len(p.relations) == 1


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(_payload(unknown_field=1))


def test_unknown_etype_rejected():
    bad = _payload()
    bad["entities"][0]["etype"] = "company"
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


def test_confidence_out_of_range_rejected():
    bad = _payload()
    bad["entities"][1]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


def test_relation_refers_undeclared_entity_rejected():
    bad = _payload()
    bad["relations"][0]["object"] = "不存在的实体"
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


def test_empty_entities_rejected():
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(_payload(entities=[]))


@pytest.mark.parametrize("level", ["mention", "entity", "relation", "extraction"])
def test_nested_extra_field_rejected(level):
    p = _payload()
    if level == "mention":
        p["entities"][0]["mention"]["unknown_field"] = 1
    elif level == "entity":
        p["entities"][0]["unknown_field"] = 1
    elif level == "relation":
        p["relations"][0]["unknown_field"] = 1
    else:
        p["unknown_field"] = 1
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(p)


def test_quote_over_2000_rejected():
    bad = _payload()
    bad["entities"][0]["mention"]["quote"] = "字" * 2001
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


def test_predicate_etype_inversion_rejected():
    bad = _payload()
    bad["relations"][0]["predicate"] = "project_won_by_bidder"  # 期望 (project, bidder)，实际 (bidder, project)
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


def test_empty_relations_valid():
    p = BidExtraction.model_validate(_payload(relations=[]))
    assert p.relations == []


# --- eia 域（基类 ExtractionPayload 通用化）---


def _eia_payload(**over):
    base = {
        "domain": "eia",
        "entities": [
            {"etype": "project", "name": "横城矿区总体规划（修编）环评", "mention": {"document_id": "eia-sample:hengcheng"}},
            {"etype": "mine", "name": "横城煤矿", "mention": {"document_id": "eia-sample:hengcheng"}},
            {"etype": "org", "name": "中煤科工集团北京华宇工程有限公司", "mention": {"document_id": "eia-sample:hengcheng"}},
            {"etype": "place", "name": "宁夏回族自治区", "mention": {"document_id": "eia-sample:hengcheng"}},
            {"etype": "sensitive_point", "name": "宁夏灵武白芨滩国家级自然保护区", "mention": {"document_id": "eia-sample:hengcheng"}},
        ],
        "relations": [
            {"predicate": "org_compiles_project", "subject": "中煤科工集团北京华宇工程有限公司", "object": "横城矿区总体规划（修编）环评", "mention": {"document_id": "eia-sample:hengcheng"}},
        ],
    }
    base.update(over)
    return base


def test_eia_valid_roundtrip():
    p = EiaExtraction.model_validate(_eia_payload())
    assert p.domain == "eia" and len(p.entities) == 5


def test_eia_unknown_etype_rejected():
    bad = _eia_payload()
    bad["entities"][0]["etype"] = "bidder"  # bid 域枚举不可混入 eia
    with pytest.raises(ValidationError):
        EiaExtraction.model_validate(bad)


def test_eia_role_mismatch_rejected():
    bad = _eia_payload()
    bad["relations"][0]["subject"] = "横城煤矿"
    bad["relations"][0]["object"] = "横城矿区总体规划（修编）环评"  # mine→project 不满足 org→project 角色
    with pytest.raises(ValidationError):
        EiaExtraction.model_validate(bad)


def test_ingest_accepts_eia_payload_type():
    """ingest_extraction 签名放宽后应引用两域共同基类（from __future__ annotations 下注解为裸名字符串）。"""
    sig = inspect.signature(ingest_extraction)
    assert sig.parameters["payload"].annotation == "ExtractionPayload"
    assert issubclass(BidExtraction, ExtractionPayload) and issubclass(EiaExtraction, ExtractionPayload)  # 通用化前提: 两域模型均为基类子类


def test_base_payload_direct_instantiation_rejected():
    """基类直接实例化必须 fail-closed（域表空集）——域收紧不可经基类绕过。"""
    with pytest.raises(ValidationError):
        ExtractionPayload.model_validate(_payload())


@pytest.mark.parametrize(
    ("model", "payload", "foreign_pred"),
    [
        (BidExtraction, _payload(), "org_compiles_project"),
        (EiaExtraction, _eia_payload(), "bidder_of_project"),
    ],
    ids=["bid-rejects-eia-pred", "eia-rejects-bid-pred"],
)
def test_foreign_domain_predicate_rejected(model, payload, foreign_pred):
    """跨域谓词双向拒收——域谓词集把共享 payload 的全枚举 Literal 收紧回本域。"""
    bad = copy.deepcopy(payload)
    bad["relations"][0]["predicate"] = foreign_pred
    with pytest.raises(ValidationError):
        model.model_validate(bad)


def test_literal_and_domain_tables_consistent():
    """全枚举 Literal 必须恰等于两域域表并集——防域表键 typo 产生静默死条目。"""
    assert set(get_args(schemas._ETYPE)) == BidExtraction.domain_etypes | EiaExtraction.domain_etypes
    assert set(get_args(schemas._PREDICATE)) == BidExtraction.domain_predicates | EiaExtraction.domain_predicates


# --- 多角色对（2026-09-29 数据驱动改造：_EIA_PREDICATE_ROLES 值 = tuple[tuple[str,str], ...]）---


def test_role_tables_uniform_pair_tuple_shape():
    """两域角色表值统一为 tuple[tuple[str, str], ...]（单对谓词包单元素元组）——converter 侧按成员判定。"""
    for table in (schemas._PREDICATE_ROLES, schemas._EIA_PREDICATE_ROLES):
        for pred, pairs in table.items():
            assert isinstance(pairs, tuple) and pairs, f"{pred} 角色对集为空或非元组"
            for pair in pairs:
                assert isinstance(pair, tuple) and len(pair) == 2, f"{pred} 角色对形态非法: {pair!r}"
                assert all(isinstance(s, str) for s in pair)


def test_bid_single_pair_behavior_unchanged():
    """bid 域铁律：单对语义原样——合法对过、反转仍拒。"""
    assert schemas._PREDICATE_ROLES["bidder_of_project"] == (("bidder", "project"),)
    assert BidExtraction.model_validate(_payload())
    bad = _payload()
    bad["relations"][0]["predicate"] = "project_won_by_bidder"
    with pytest.raises(ValidationError):
        BidExtraction.model_validate(bad)


# 17 个数据驱动新增对（支持数 = 1564 条候选 raw 三元组计数, 见各对 schemas.py 行尾注释）
_NEW_PAIRS = [
    ("located_in", "evidence_artifact", "mine_field"),
    ("located_in", "mine", "place"),
    ("located_in", "treatment_measure", "mine"),
    ("located_in", "place", "place"),
    ("located_in", "sensitive_point", "place"),
    ("located_in", "monitoring", "aquifer"),
    ("located_in", "sensitive_point", "mine_field"),
    ("located_in", "mine", "mining_district"),
    ("located_in", "engineering_site", "place"),
    ("located_in", "engineering_site", "project"),
    ("complies_with", "waste_stream", "emission_standard"),
    ("complies_with", "pollution_source", "emission_standard"),
    ("regulated_by", "org", "regulation_clause"),
    ("treated_by", "engineering_site", "treatment_measure"),
    ("monitored_by", "engineering_site", "monitoring"),
    ("causes", "engineering_site", "impact_result"),
    ("disposed_by", "waste_stream", "engineering_site"),
]


@pytest.mark.parametrize(
    ("pred", "subj_etype", "obj_etype"),
    _NEW_PAIRS,
    ids=[f"{p}-{s}-{o}" for p, s, o in _NEW_PAIRS],
)
def test_new_pair_accepts(pred, subj_etype, obj_etype):
    """每个新增对逐条验证 accept（同名实体 names 须唯一, 自引用对用双实体构造）。"""
    s_name, o_name = ("S实体", "O实体") if subj_etype != obj_etype else ("S实体", "O实体2")
    payload = EiaExtraction(
        domain="eia",
        entities=[{"etype": subj_etype, "name": s_name, "mention": {"document_id": "d"}}, {"etype": obj_etype, "name": o_name, "mention": {"document_id": "d"}}],
        relations=[{"predicate": pred, "subject": s_name, "object": o_name, "mention": {"document_id": "d"}}],
    )
    assert len(payload.relations) == 1


def test_multi_pair_any_legal_pair_accepts():
    """多对谓词：同一谓词的两个不同合法对在同一 payload 内共存通过。"""
    payload = EiaExtraction(
        domain="eia",
        entities=[
            {"etype": "pollution_source", "name": "锅炉烟气", "mention": {"document_id": "d"}},
            {"etype": "engineering_site", "name": "工业场地", "mention": {"document_id": "d"}},
            {"etype": "treatment_measure", "name": "隔声屏障", "mention": {"document_id": "d"}},
        ],
        relations=[
            {"predicate": "treated_by", "subject": "锅炉烟气", "object": "隔声屏障", "mention": {"document_id": "d"}},
            {"predicate": "treated_by", "subject": "工业场地", "object": "隔声屏障", "mention": {"document_id": "d"}},
        ],
    )
    assert {r.subject for r in payload.relations} == {"锅炉烟气", "工业场地"}


def test_multi_pair_illegal_pair_still_rejected():
    """多对谓词：非法对仍拒——(pollutant, treatment_measure) 不在 treated_by 对集（数据中亦无此用法）。"""
    with pytest.raises(ValidationError, match="要求"):
        EiaExtraction(
            domain="eia",
            entities=[{"etype": "pollutant", "name": "悬浮物", "mention": {"document_id": "d"}}, {"etype": "treatment_measure", "name": "隔声屏障", "mention": {"document_id": "d"}}],
            relations=[{"predicate": "treated_by", "subject": "悬浮物", "object": "隔声屏障", "mention": {"document_id": "d"}}],
        )


def test_data_insufficient_predicates_held_back():
    """pollutes/precedes 数据不足（最大组合支持 4/1 < 5 门槛）不入契约——Literal 与域表均无, converter 仍丢弃。"""
    for held in ("pollutes", "precedes"):
        assert held not in get_args(schemas._PREDICATE)
        assert held not in EiaExtraction.domain_predicates


def test_registry_new_predicates_in_literal_and_domain():
    """registry 37 谓词中数据支撑的 3 个新谓词须同时进 Literal 与 eia 域表（Invariant: Literal=两域域表并集）。"""
    for pred in ("located_in", "complies_with", "regulated_by"):
        assert pred in get_args(schemas._PREDICATE)
        assert pred in EiaExtraction.domain_predicates


# --- 多角色对 R2（2026-09-29 下午：解除范围限制, 既有谓词 ≥5 支持域内对全量补齐, 逐对引文抽查）---
_NEW_PAIRS_R2 = [
    ("method_of", "mine", "mining_method"),
    ("treated_by", "waste_stream", "treatment_measure"),
    ("disposed_by", "waste_stream", "org"),
    ("disposed_by", "waste_stream", "place"),
    ("treated_by", "mine", "treatment_measure"),
    ("mines", "mine", "coal_seam"),
    ("causes", "pollutant", "impact_result"),
    ("causes", "pollution_process_concept", "impact_result"),
    ("monitored_by", "mine", "monitoring"),
    ("part_of", "mine", "mining_district"),
    ("part_of", "mine_field", "mining_district"),
    ("causes", "mine", "impact_result"),
    ("part_of", "stratigraphic_unit", "stratigraphic_unit"),
    ("treated_by", "pollution_source", "measure_process_concept"),
    ("utilized_by", "waste_stream", "measure_process_concept"),
    ("causes", "impact_result", "impact_result"),
    ("causes", "mining_method", "impact_result"),
    ("drains_to", "receiving_medium", "receiving_medium"),
    ("emitted_as", "waste_stream", "pollutant"),
    ("protected_by", "sensitive_point", "measure_spec"),
    ("specifies_threshold", "planning_scheme", "standard_threshold"),
    ("utilized_by", "waste_stream", "org"),
]


@pytest.mark.parametrize(
    ("pred", "subj_etype", "obj_etype"),
    _NEW_PAIRS_R2,
    ids=[f"{p}-{s}-{o}" for p, s, o in _NEW_PAIRS_R2],
)
def test_new_pair_r2_accepts(pred, subj_etype, obj_etype):
    """R2 每对逐条 accept（引文抽查通过, 支持数注记见 schemas.py 各行尾）。"""
    s_name, o_name = ("S实体", "O实体") if subj_etype != obj_etype else ("S实体", "O实体2")
    payload = EiaExtraction(
        domain="eia",
        entities=[{"etype": subj_etype, "name": s_name, "mention": {"document_id": "d"}}, {"etype": obj_etype, "name": o_name, "mention": {"document_id": "d"}}],
        relations=[{"predicate": pred, "subject": s_name, "object": o_name, "mention": {"document_id": "d"}}],
    )
    assert len(payload.relations) == 1


@pytest.mark.parametrize(
    ("pred", "subj_etype", "obj_etype"),
    [
        ("specifies_threshold", "pollutant", "standard_threshold"),  # x29 主宾倒置: "Na+标准限值≤200"限值属于标准
        ("specifies_threshold", "engineering_site", "standard_threshold"),  # x6 主宾倒置: 场地是达标方非规定方
        ("cites_clause", "regulation_clause", "chapter"),  # x11 主宾倒置: 引文实为章节引用法律
        ("monitored_by", "monitoring", "monitoring"),  # x7 表结构自指噪声: "环境噪声受噪声监测"语义空洞
    ],
    ids=["specifies-pollutant", "specifies-site", "cites-inverted", "monitored-selfref"],
)
def test_semantic_rejected_pairs_still_rejected(pred, subj_etype, obj_etype):
    """语义抽查拒收的对（支持数达标但主宾倒置/自指）必须仍被拒——防数据噪声倒灌契约。"""
    s_name, o_name = ("S实体", "O实体") if subj_etype != obj_etype else ("S实体", "O实体2")
    with pytest.raises(ValidationError, match="要求"):
        EiaExtraction(
            domain="eia",
            entities=[{"etype": subj_etype, "name": s_name, "mention": {"document_id": "d"}}, {"etype": obj_etype, "name": o_name, "mention": {"document_id": "d"}}],
            relations=[{"predicate": pred, "subject": s_name, "object": o_name, "mention": {"document_id": "d"}}],
        )


def test_registry_yaml_enums_superset_of_schemas_literals():
    """registry 各域 yaml 枚举并集必须 ⊇ schemas 全枚举 Literal——防 schemas 增益而 yaml 未跟的静默死规则。

    schemas._ETYPE/_PREDICATE 是跨域全集（doc_graph + eia 等），逐域 yaml 只持本域切片；
    校验基准 = 全部域 yaml 的并集。
    EAI-CUSTOM（计划 Task 9, 2026-09-28）：eia v2 期间 schemas 先行扩容（EiaExtraction v2），
    registry/eia.yaml 仍为 v1、待 Task 11 用户建模器定型后替换——过渡期把已 APPROVED 的
    v2 草案（scripts/eia_schema_mining/eia_v2_draft.yaml）并入校验基准，不变式语义不变。
    """
    registry_dir = Path(__file__).resolve().parents[1] / "app" / "ontology" / "registry"
    yaml_files = sorted(registry_dir.glob("*.yaml"))
    v2_draft = Path(__file__).resolve().parents[1] / "scripts" / "eia_schema_mining" / "eia_v2_draft.yaml"
    if v2_draft.exists():  # Task 11 定型替换后草案可退役，此扫描自动收窄回 registry
        yaml_files.append(v2_draft)
    yaml_etypes: set[str] = set()
    yaml_preds: set[str] = set()
    for yml in yaml_files:
        doc = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        for ot in doc.get("object_types", []):
            for prop in ot.get("properties", []):
                if prop.get("name") == "etype" and prop.get("enum"):
                    yaml_etypes.update(prop["enum"])
                if prop.get("name") == "predicate" and prop.get("enum"):
                    yaml_preds.update(prop["enum"])
    assert set(get_args(schemas._ETYPE)) <= yaml_etypes
    assert set(get_args(schemas._PREDICATE)) <= yaml_preds
    assert "org_involved_in" in yaml_preds  # 推理派生谓词（不落库, 仅事实空间）
