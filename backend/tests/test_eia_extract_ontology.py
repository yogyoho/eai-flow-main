"""四类目标抽取 golden 测试（extract_ontology, EAI-CUSTOM 2026-09-20）.

用户需求四条 → 确定性抽取器逐条验收：
② 上下文逻辑链条：治理合规链 treated_by/governed_by/monitored_by + 影响链 emitted_as/threatens/impact_to
③ 标准阈值/法规条款：GB 标准号 + 限值（pollutant/op/value/unit）+ 《法》第X条
④ 佐证需求：表/图/公式/附件/流程图 引用
（① 章节结构由既有 extract_outline 覆盖，见 test_eia_samples.py）
"""

from __future__ import annotations

import pytest

from app.extensions.eia_samples.extract_ontology import extract_ontology

SAMPLE = """第四章 大气环境影响评价
4.2 治理措施可行性
锅炉烟气采用双碱法脱硫塔处理，执行GB 13223-2011标准，SO2排放浓度不超过50 mg/m3，见表3-2。
项目废水排放二氧化硫污染物威胁桑干河水源保护区。
依据《中华人民共和国大气污染防治法》第二十六条要求，治理工艺流程图见附件1。"""


@pytest.fixture()
def ontology():
    return extract_ontology(SAMPLE)


def _names(d, etype):
    return [e["name"] for e in d["entities"] if e["etype"] == etype]


def _rels(d, pred):
    return [(r["subject"], r["object"]) for r in d["relations"] if r["predicate"] == pred]


def test_standard_extracted(ontology):
    assert "GB13223" in _names(ontology, "emission_standard")


def test_threshold_with_attrs(ontology):
    ths = [e for e in ontology["entities"] if e["etype"] == "standard_threshold"]
    assert ths, "阈值实体必须抽出"
    attrs = ths[0]["attrs"]
    assert attrs["pollutant"] == "SO2" and attrs["value"] == "50" and attrs["unit"] == "mg/m3"
    assert any(r["predicate"] == "specifies_threshold" and r["object"] == ths[0]["name"] for r in ontology["relations"])


def test_regulation_clause(ontology):
    assert any("大气污染防治法" in n and "第二十六条" in n for n in _names(ontology, "regulation_clause"))


def test_logic_chain(ontology):
    assert ("锅炉烟气", "脱硫塔") in _rels(ontology, "treated_by")
    assert ("脱硫塔", "GB13223") in _rels(ontology, "governed_by")


def test_impact_chain(ontology):
    assert ("废水", "二氧化硫污染物") in _rels(ontology, "emitted_as")
    assert ("二氧化硫污染物", "桑干河水源保护区") in _rels(ontology, "threatens")
    assert ("废水", "桑干河水源保护区") in _rels(ontology, "impact_to")


def test_evidence_requirements(ontology):
    names = _names(ontology, "evidence_requirement")
    assert "见表3-2" in names
    assert "附件1" in names
    kinds = {e["name"]: e["attrs"]["evidence_type"] for e in ontology["entities"] if e["etype"] == "evidence_requirement"}
    assert kinds["见表3-2"] == "table"
    assert kinds["附件1"] == "appendix"


def test_entity_dedup(ontology):
    keys = [(e["etype"], e["name"]) for e in ontology["entities"]]
    assert len(keys) == len(set(keys)), "跨函数 (etype,name) 不得重复"
