"""批二十 M1-h AI 附件索引测试(EAI-CUSTOM 2026-11-13)——需求×素材→索引行:
命中=ready/未命中=待补+负证据随行(CMN-005 面)/待补行页码指纹锚点齐备(AI-004/
006/007 面)/volumes 分册行/编号唯一/待补词只在 status 列。"""

from app.extensions.bid_write.generate.attachment_index import build_attachment_index

_REQS = [
    {"no": "1", "name": "营业执照", "clause": "3.1", "mandatory": "★", "min_count": 1},
    {"no": "2", "name": "矿用产品安全标志证书", "clause": "3.2", "mandatory": "必需", "min_count": 1},
]
_VOLS = [{"name": "商务卷", "min_copies": 2}, {"name": "技术卷", "min_copies": 1}]
_ENTITIES = {"ent:license": {"type": "营业执照", "name": "营业执照"}}
_SECS = [{"code": "sec:1", "title": "1 商务卷", "level": 1}, {"code": "sec:2", "title": "2 资格证明", "level": 1}]


def _build(material=None, page_estimates=None):
    return build_attachment_index(_REQS, _VOLS, material if material is not None else {"entities": _ENTITIES}, _SECS, page_estimates=page_estimates)


def test_hit_ready_and_miss_pending():
    """命中实体→ready;未命中→待补占位行(不静默省略,漏报直接相关设计点)。"""
    idx = _build()
    items = idx["items"]
    assert [i["no"] for i in items] == ["1", "2", "V1", "V2"]
    assert items[0]["status"] == "ready" and items[0]["type_fingerprint"] == "营业执照"
    assert items[1]["status"] == "待补"
    # 待补行负证据随行(CMN-005 面:检索范围/匹配键/最近候选全非空)
    pend = idx["pending_items"]
    assert len(pend) == 1 and pend[0]["item"] == "矿用产品安全标志证书"
    ev = pend[0]["negative_evidence"]
    assert ev and all(str(v).strip() for v in ev.values())


def test_pending_row_fully_anchored():
    """待补行 page/fingerprint/source 齐备(AI-004 页码/AI-006 指纹≠unknown/AI-007 锚点面)。"""
    items = _build()["items"]
    row = items[1]
    assert isinstance(row["page"], int) and row["page"] >= 1
    assert row["type_fingerprint"] not in ("", "unknown_type")
    assert row["source"]
    # 待补词只出现在 status 列,不进名称列(AI 铁律)
    assert "待补" not in row["name"]


def test_req_coverage_and_unique_nos():
    """要求逐项有索引行(AI-002 面);编号唯一(AI-001 面);volumes copies=min_copies(AI-005 面)。"""
    idx = _build()
    items = idx["items"]
    nos = [i["no"] for i in items]
    assert len(nos) == len(set(nos))
    names = {i["name"] for i in items}
    assert {"营业执照", "矿用产品安全标志证书", "商务卷", "技术卷"} <= names
    by_name = {i["name"]: i for i in items}
    assert by_name["商务卷"]["copies"] == 2 and by_name["技术卷"]["copies"] == 1


def test_toc_body_consistent_and_body_refs_resolve():
    """目录=正文标题逐条一致(AI-008 面);正文附件引用全可解析(AI-003 面)。"""
    idx = _build()
    assert idx["toc_titles"] == idx["body_headings"]
    nos = {i["no"] for i in idx["items"]}
    import re

    for m in re.finditer(r"见附件([0-9A-Za-z]{1,8})", idx["body_text"]):
        assert m.group(1) in nos


def test_pages_from_estimates_and_total():
    """page_estimates 面注入:页码取估值;total_pages≥最大页(AI-004 面)。"""
    idx = _build(page_estimates={"1": 3, "2": 5})
    by_no = {i["no"]: i for i in idx["items"]}
    assert by_no["1"]["page"] == 3 and by_no["2"]["page"] == 5
    assert idx["total_pages"] >= 5


def test_no_entities_all_pending():
    """素材全缺→全部待补(诚实伪零同律),负证据逐行随行。"""
    idx = _build(material={})
    assert all(i["status"] == "待补" for i in idx["items"] if not i["no"].startswith("V"))
    assert len(idx["pending_items"]) == 2


def test_deterministic():
    assert _build() == _build()
