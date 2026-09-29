"""convert_candidates 单测：幻觉过滤/角色校验丢弃/同名多etype消解/pending置信度。

计划勘误（2026-09-29）：计划原文 test_same_name_conflicting_etype_resolved 用谓词 located_in，
该谓词不在 EiaExtraction.predicate_roles（schemas.py 契约表，v2 定型 33 谓词无 located_in），
原测试数据必然被角色校验丢弃、同名冲突根本无法构造——改用契约内谓词构造 2:1 多数决。
"""

from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eia_schema_mining" / "convert_candidates.py"


def _load():
    import importlib.util

    spec = importlib.util.spec_from_file_location("cc", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_hallucination_dropped():
    m = _load()
    rows = [{"report": "r1", "subject": "锅炉", "subject_type": "pollution_source",
             "predicate": "treated_by", "object": "脱硫塔", "object_type": "treatment_measure",
             "evidence_quote": "这句话不在原文里"}]
    out = m.convert(rows, fulltext_getter=lambda s: "锅炉烟气经脱硫塔处理后排放", source="r1.docx")
    assert out.stats["hallu_dropped"] == 1 and not out.payloads


def test_role_violation_dropped():
    m = _load()
    rows = [{"report": "r1", "subject": "3号煤层", "subject_type": "coal_seam",
             "predicate": "causes", "object": "沉陷", "object_type": "impact_result",
             "evidence_quote": "3号煤层开采导致沉陷"}]  # causes 要求 (working_face, impact_result)
    out = m.convert(rows, fulltext_getter=lambda s: "3号煤层开采导致沉陷", source="r1.docx")
    assert out.stats["role_dropped"] == 1 and not out.payloads


def test_same_name_conflicting_etype_resolved():
    m = _load()
    # 处理站 出现 3 次：2 次 treatment_measure + 1 次 pollution_source → 多数决取 treatment_measure
    rows = [
        {"report": "r1", "subject": "矿井水", "subject_type": "pollution_source", "predicate": "treated_by",
         "object": "处理站", "object_type": "treatment_measure", "evidence_quote": "矿井水经处理站处理"},
        {"report": "r1", "subject": "处理站", "subject_type": "treatment_measure", "predicate": "governed_by",
         "object": "一级标准", "object_type": "emission_standard", "evidence_quote": "处理站执行一级标准"},
        {"report": "r1", "subject": "处理站", "subject_type": "pollution_source", "predicate": "emitted_as",
         "object": "悬浮物", "object_type": "pollutant", "evidence_quote": "处理站排放悬浮物"},
    ]
    out = m.convert(rows, fulltext_getter=lambda s: "矿井水经处理站处理 处理站执行一级标准 处理站排放悬浮物", source="r1.docx")
    ents = out.payloads[0]["entities"]
    assert len(ents) == 4  # 矿井水/处理站/一级标准/悬浮物 各一次
    assert {e["name"]: e["etype"] for e in ents}["处理站"] == "treatment_measure"  # 多数决 2:1
    assert out.stats["dup_entities_merged"] >= 1


def test_resolved_role_conflict_relation_dropped():
    m = _load()
    # 同名消解把 处理站 定为 treatment_measure（2:1 多数）后，emitted_as 要求 subject=pollution_source
    # 失配 → 该关系丢弃并计入 resolved_role_dropped；实体保留（文本已核验）。
    # 保证 convert 产物可整体通过 EiaExtraction.model_validate（Task5 ingest 硬门 fail-closed）。
    rows = [
        {"report": "r1", "subject": "矿井水", "subject_type": "pollution_source", "predicate": "treated_by",
         "object": "处理站", "object_type": "treatment_measure", "evidence_quote": "矿井水经处理站处理"},
        {"report": "r1", "subject": "处理站", "subject_type": "treatment_measure", "predicate": "governed_by",
         "object": "一级标准", "object_type": "emission_standard", "evidence_quote": "处理站执行一级标准"},
        {"report": "r1", "subject": "处理站", "subject_type": "pollution_source", "predicate": "emitted_as",
         "object": "悬浮物", "object_type": "pollutant", "evidence_quote": "处理站排放悬浮物"},
    ]
    out = m.convert(rows, fulltext_getter=lambda s: "矿井水经处理站处理 处理站执行一级标准 处理站排放悬浮物", source="r1.docx")
    payload = out.payloads[0]
    assert out.stats["resolved_role_dropped"] == 1
    assert [(r["predicate"], r["object"]) for r in payload["relations"]] == [("treated_by", "处理站"), ("governed_by", "一级标准")]
    assert {e["name"] for e in payload["entities"]} == {"矿井水", "处理站", "一级标准", "悬浮物"}


def test_all_pending_confidence():
    m = _load()
    rows = [{"report": "r1", "subject": "锅炉", "subject_type": "pollution_source", "predicate": "treated_by",
             "object": "脱硫塔", "object_type": "treatment_measure", "evidence_quote": "锅炉烟气经脱硫塔处理后排放"}]
    out = m.convert(rows, fulltext_getter=lambda s: "锅炉烟气经脱硫塔处理后排放", source="r1.docx")
    assert out.payloads[0]["entities"][0]["confidence"] < 0.7
    assert out.payloads[0]["entities"][0]["mention"]["quote"] == "锅炉烟气经脱硫塔处理后排放"
