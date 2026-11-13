"""批二十 M1-g RT 装配测试(EAI-CUSTOM 2026-11-13)——矩阵行→响应表:三类行源
过滤(attachment/clause 收,aggregate 不收)/★透传/参数化应答零禁用词/摘录透传。"""

from bid_write_exec_fixtures import green_ctx

from app.extensions.bid_write.executor.wordscan import scan_text, words_for
from app.extensions.bid_write.generate.response_table import build_response_table

_ROWS = [
    {"clause_id": "att:1", "kind": "attachment", "requirement": "no=1、营业执照、★、3.1", "star": True, "evidence_refs": [{"path": "sec:4", "quote": "营业执照", "page": 3}]},
    {"clause_id": "att:2", "kind": "attachment", "requirement": "no=2、矿用产品安全标志证书、必需、3.2", "star": False, "evidence_refs": []},
    {"clause_id": "deposit", "kind": "aggregate", "requirement": "投标保证金:100000", "star": False, "evidence_refs": []},
    {"clause_id": "decl:1", "kind": "clause", "requirement": "投标人须承诺投标文件真实合法。", "star": False, "evidence_refs": []},
]


def test_rows_filtered_and_ordered():
    """aggregate 行不收;attachment/clause 保序;deviation 对缺省 None。"""
    rt = build_response_table(_ROWS)
    assert [r["clause_id"] for r in rt["rows"]] == ["att:1", "att:2", "decl:1"]
    assert rt["matrix_star_clause_ids"] == ["att:1"]
    assert all(r["deviation_reason"] is None and r["replacement_plan"] is None for r in rt["rows"])
    assert all(r["conclusion"] == "完全响应" for r in rt["rows"])
    assert rt["pending_items"] == []


def test_star_and_passthrough():
    rt = build_response_table(_ROWS)
    by_id = {r["clause_id"]: r for r in rt["rows"]}
    assert by_id["att:1"]["star"] is True and by_id["att:2"]["star"] is False
    assert by_id["att:1"]["requirement_excerpt"] == "no=1、营业执照、★、3.1"
    assert by_id["att:1"]["evidence_refs"] == [{"path": "sec:4", "quote": "营业执照", "page": 3}]


def test_empty_evidence_synthesized_tender_anchor():
    """证据缺位→引用招标条款锚点(RT-007 非空面;引用要求自身非伪造素材)。"""
    bare = [{"clause_id": "att:9", "kind": "attachment", "requirement": "x", "star": False, "evidence_refs": [], "source_path": "tender.attachment_requirements"}]
    rt = build_response_table(bare)
    assert rt["rows"][0]["evidence_refs"] == [{"path": "tender.attachment_requirements", "quote": "x"}]


def test_response_text_zero_forbidden_hits():
    """参数化应答 6 桶零命中(空应答词「满足招标文件要求」类被钉死,模板必须绕开)。"""
    rt = build_response_table(_ROWS)
    all_words = words_for("placeholder", "absolute", "redline", "vague", "price_vague", "empty_answer")
    for r in rt["rows"]:
        assert scan_text(r["response_text"], all_words) == [], (r["clause_id"], r["response_text"])
    # 与 green 夹具行同键形(执行器消费面零漂移)
    green_keys = set(green_ctx()["products"]["response_table"]["rows"][0])
    assert set(rt["rows"][0]) == green_keys


def test_empty_matrix_honest_zero():
    rt = build_response_table([])
    assert rt == {"matrix_star_clause_ids": [], "rows": [], "pending_items": []}


def test_deterministic():
    assert build_response_table(_ROWS) == build_response_table(_ROWS)
