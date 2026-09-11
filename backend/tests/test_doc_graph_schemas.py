"""doc_graph 抽取 schema 测试——extra=forbid fail-closed 与交叉引用校验."""

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
        "entities": [dict(_MIN_ENT), {"etype": "bidder", "name": "山西煤机集团", "confidence": 0.9, "mention": {"document_id": "doc-001"}}],
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
