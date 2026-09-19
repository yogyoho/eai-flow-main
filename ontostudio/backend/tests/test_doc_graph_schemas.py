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


def test_registry_yaml_enums_superset_of_schemas_literals():
    """registry 各域 yaml 枚举并集必须 ⊇ schemas 全枚举 Literal——防 schemas 增益而 yaml 未跟的静默死规则。

    schemas._ETYPE/_PREDICATE 是跨域全集（doc_graph + eia 等），逐域 yaml 只持本域切片；
    校验基准 = 全部域 yaml 的并集。
    """
    registry_dir = Path(__file__).resolve().parents[1] / "app" / "ontology" / "registry"
    yaml_etypes: set[str] = set()
    yaml_preds: set[str] = set()
    for yml in sorted(registry_dir.glob("*.yaml")):
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
