"""EiaExtraction 四类目标域表验收（ontostudio doc_graph schema, EAI-CUSTOM 2026-09-20）.

抽取器（主后端 eia_samples.extract_ontology）输出的四类目标 payload 必须通过
EiaExtraction 校验（域枚举/交叉引用/谓词角色），才能经 ingest_extraction 落 dg_* 表。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.doc_graph.schemas import EiaExtraction

# 与主后端 extract_ontology 真实输出同构的最小四类目标 payload
# （①章节 ②治理链+影响链 ③阈值+法规条款 ④佐证）
MENTION = {"document_id": "doc-1"}

FOUR_TARGET_PAYLOAD = {
    "domain": "eia",
    "extracted_by": "eia-extract-ontology/v1",
    "entities": [
        {"etype": "report", "name": "横城煤矿环评报告书", "mention": {"document_id": "doc-1"}},
        {"etype": "chapter", "name": "第五章 大气环境影响评价", "mention": {"document_id": "doc-1"}},
        {"etype": "section", "name": "5.2 治理措施可行性", "mention": {"document_id": "doc-1"}},
        {"etype": "pollution_source", "name": "锅炉烟气", "mention": {"document_id": "doc-1"}},
        {"etype": "treatment_measure", "name": "双碱法脱硫塔", "mention": {"document_id": "doc-1"}},
        {"etype": "emission_standard", "name": "GB13223", "mention": {"document_id": "doc-1"}},
        {"etype": "monitoring", "name": "GB13223 监测", "mention": {"document_id": "doc-1"}},
        {"etype": "pollutant", "name": "二氧化硫", "mention": {"document_id": "doc-1"}},
        {"etype": "sensitive_point", "name": "桑干河水源保护区", "mention": {"document_id": "doc-1"}},
        {"etype": "standard_threshold", "name": "SO2不超过50mg/m3", "mention": {"document_id": "doc-1"}},
        {"etype": "regulation_clause", "name": "大气污染防治法第二十六条", "mention": {"document_id": "doc-1"}},
        {"etype": "evidence_requirement", "name": "见表3-2", "mention": {"document_id": "doc-1"}},
    ],
    "relations": [
        {"predicate": "has_chapter", "subject": "横城煤矿环评报告书", "object": "第五章 大气环境影响评价", "mention": MENTION},
        {"predicate": "has_subsection", "subject": "第五章 大气环境影响评价", "object": "5.2 治理措施可行性", "mention": MENTION},
        {"predicate": "treated_by", "subject": "锅炉烟气", "object": "双碱法脱硫塔", "mention": MENTION},
        {"predicate": "governed_by", "subject": "双碱法脱硫塔", "object": "GB13223", "mention": MENTION},
        {"predicate": "monitored_by", "subject": "GB13223", "object": "GB13223 监测", "mention": MENTION},
        {"predicate": "emitted_as", "subject": "锅炉烟气", "object": "二氧化硫", "mention": MENTION},
        {"predicate": "threatens", "subject": "二氧化硫", "object": "桑干河水源保护区", "mention": MENTION},
        {"predicate": "impact_to", "subject": "锅炉烟气", "object": "桑干河水源保护区", "mention": MENTION},
        {"predicate": "specifies_threshold", "subject": "GB13223", "object": "SO2不超过50mg/m3", "mention": MENTION},
        {"predicate": "cites_clause", "subject": "横城煤矿环评报告书", "object": "大气污染防治法第二十六条", "mention": MENTION},
        {"predicate": "requires_evidence", "subject": "双碱法脱硫塔", "object": "见表3-2", "mention": MENTION},
    ],
}


def test_four_target_payload_passes_domain_validation():
    payload = EiaExtraction.model_validate(FOUR_TARGET_PAYLOAD)
    assert payload.domain == "eia"
    assert len(payload.entities) == 12
    assert len(payload.relations) == 11


def test_unknown_etype_rejected():
    bad = {
        **FOUR_TARGET_PAYLOAD,
        "entities": [{"etype": "ufo", "name": "x", "mention": {"document_id": "d"}}],
    }
    with pytest.raises(ValidationError):
        EiaExtraction.model_validate(bad)


def test_role_mismatch_rejected():
    bad = {
        **FOUR_TARGET_PAYLOAD,
        "relations": [{"predicate": "treated_by", "subject": "双碱法脱硫塔", "object": "锅炉烟气", "mention": MENTION}],
    }
    with pytest.raises(ValidationError, match="要求"):
        EiaExtraction.model_validate(bad)
