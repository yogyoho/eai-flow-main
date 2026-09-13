"""doc_graph 抽取 schema 测试——extra=forbid fail-closed 与交叉引用/谓词角色校验."""

import copy

import pytest
from pydantic import ValidationError

from app.extensions.ontology.doc_graph.schemas import BidExtraction

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
    from app.extensions.ontology.doc_graph.schemas import EiaExtraction

    p = EiaExtraction.model_validate(_eia_payload())
    assert p.domain == "eia" and len(p.entities) == 5


def test_eia_unknown_etype_rejected():
    import pytest
    from pydantic import ValidationError

    from app.extensions.ontology.doc_graph.schemas import EiaExtraction

    bad = _eia_payload()
    bad["entities"][0]["etype"] = "bidder"  # bid 域枚举不可混入 eia
    with pytest.raises(ValidationError):
        EiaExtraction.model_validate(bad)


def test_eia_role_mismatch_rejected():
    import pytest
    from pydantic import ValidationError

    from app.extensions.ontology.doc_graph.schemas import EiaExtraction

    bad = _eia_payload()
    bad["relations"][0]["subject"] = "横城煤矿"
    bad["relations"][0]["object"] = "横城矿区总体规划（修编）环评"  # mine→project 不满足 org→project 角色
    with pytest.raises(ValidationError):
        EiaExtraction.model_validate(bad)


def test_ingest_accepts_eia_payload_type():
    """ingest_extraction 签名放宽后应引用两域共同基类。"""
    import inspect

    from app.extensions.ontology.doc_graph.ingest import ingest_extraction
    from app.extensions.ontology.doc_graph.schemas import EiaExtraction, ExtractionPayload

    sig = inspect.signature(ingest_extraction)
    assert "ExtractionPayload" in str(sig.parameters["payload"].annotation)
    assert issubclass(BidExtraction, ExtractionPayload) and issubclass(EiaExtraction, ExtractionPayload)  # 通用化前提: 两域模型均为基类子类
