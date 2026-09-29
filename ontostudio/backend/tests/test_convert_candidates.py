"""convert_candidates 单测：幻觉过滤/角色校验丢弃/同名多etype消解/pending置信度。

计划勘误（2026-09-29）：计划原文 test_same_name_conflicting_etype_resolved 用谓词 located_in，
该谓词不在 EiaExtraction.predicate_roles（schemas.py 契约表，v2 定型 35 谓词无 located_in），
原测试数据必然被角色校验丢弃、同名冲突根本无法构造——改用契约内谓词构造 2:1 多数决。
勘误勘误（2026-09-29 多对改造）：located_in/complies_with/regulated_by 已数据驱动入契约表
（多角色对），角色校验从等值改为成员判定。
"""

from pathlib import Path

from app.doc_graph.schemas import EiaExtraction

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


# --- 多角色对改造（2026-09-29）：located_in/complies_with 候选不再丢弃 + engineering_site 对齐 ---


def test_multi_pair_located_in_and_complies_with_kept():
    """真实数据样式：located_in (mine,place) 与 complies_with (waste_stream,emission_standard) 不再 role_dropped。"""
    m = _load()
    rows = [
        {"report": "r1", "subject": "城梁矿井", "subject_type": "mine", "predicate": "located_in",
         "object": "鄂尔多斯市", "object_type": "place", "evidence_quote": "城梁矿井位于鄂尔多斯市达拉特旗境内"},
        {"report": "r1", "subject": "矸石", "subject_type": "waste_stream", "predicate": "complies_with",
         "object": "GB8978一级标准", "object_type": "emission_standard",
         "evidence_quote": "矸石浸出液中各污染物的浓度均未超过GB8978一级标准限值"},
    ]
    full = "城梁矿井位于鄂尔多斯市达拉特旗境内 矸石浸出液中各污染物的浓度均未超过GB8978一级标准限值"
    out = m.convert(rows, fulltext_getter=lambda s: full, source="r1.docx")
    assert out.stats["role_dropped"] == 0 and out.stats["kept"] == 2
    kept_preds = {r["predicate"] for r in out.payloads[0]["relations"]}
    assert kept_preds == {"located_in", "complies_with"}


def test_engineering_site_pairs_kept():
    """engineering_site 对齐（候选 x14/x6 真实样式）：场地经治理、固废处置于排土场。"""
    m = _load()
    rows = [
        {"report": "r1", "subject": "工业场地", "subject_type": "engineering_site", "predicate": "treated_by",
         "object": "隔声屏障", "object_type": "treatment_measure",
         "evidence_quote": "工业场地噪声经隔声屏障治理后厂界达标"},
        {"report": "r1", "subject": "土岩剥离物", "subject_type": "waste_stream", "predicate": "disposed_by",
         "object": "外排土场", "object_type": "engineering_site", "evidence_quote": "土岩剥离物全部排至外排土场"},
    ]
    full = "工业场地噪声经隔声屏障治理后厂界达标 土岩剥离物全部排至外排土场"
    out = m.convert(rows, fulltext_getter=lambda s: full, source="r1.docx")
    assert out.stats["role_dropped"] == 0 and out.stats["kept"] == 2
    payload = out.payloads[0]
    EiaExtraction.model_validate(payload)  # 产物整体过 fail-closed 硬门（Task5 ingest 同门）
    assert {(r["subject"], r["predicate"]) for r in payload["relations"]} == {
        ("工业场地", "treated_by"), ("土岩剥离物", "disposed_by")}


def test_data_insufficient_predicate_still_dropped():
    """pollutes 数据不足未入契约（最大组合支持 4 < 5）——convert 仍按 role_dropped 丢弃。"""
    m = _load()
    rows = [{"report": "r1", "subject": "矿井水", "subject_type": "pollution_source", "predicate": "pollutes",
             "object": "-nil-", "object_type": "receiving_medium", "evidence_quote": "矿井水排入受纳水体"}]
    out = m.convert(rows, fulltext_getter=lambda s: "矿井水排入受纳水体", source="r1.docx")
    assert out.stats["role_dropped"] == 1 and not out.payloads
