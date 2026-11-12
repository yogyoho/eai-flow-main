"""批十九 T3 装配器 golden:纯服务端零 LLM,同输入同输出(确定性);三类行源、
★标红、blocked 低置信、缺路径不造行、摘录截断。"""

from pathlib import Path

import yaml

from app.extensions.bid_write import contracts, matrix

CASES_WRITE = Path(contracts.__file__).parent / "golden" / "cases-write" / "p0-matrix.yaml"


def _fields(**overrides):
    base = {
        "tender.attachment_requirements": [
            {"no": "1", "name": "营业执照", "mandatory": "★", "clause": "3.1", "min_count": 1},
            {"no": "2", "name": "矿用产品安全标志证书", "mandatory": "必需", "clause": "3.2"},
            {"no": "3", "name": "同类业绩合同", "mandatory": "建议", "clause": "3.3"},
        ],
        "tender.required_declarations": ["投标函承诺真实有效", "不围标串标承诺"],
        "tender.deposit_required": 100000,
        "tender.deposit_forms": ["银行转账"],
        "tender.bid_deadline": "2026-12-01 09:00",
        "tender.min_warranty_period": "24个月",
        "tender.max_duration": "90天",
        "tender.consortium_allowed": False,
    }
    base.update(overrides)
    return base


def test_golden_attachment_rows_star_flagged():
    """附件要求逐条成行;★行 star=True(三类强制标红之一);行序稳定。"""
    rows = matrix.assemble_matrix(_fields())
    att = [r for r in rows if r["clause_id"].startswith("att:")]
    assert [r["clause_id"] for r in att] == ["att:1", "att:2", "att:3"]
    assert att[0]["star"] is True and att[1]["star"] is False and att[2]["star"] is False
    assert att[0]["kind"] == "attachment"
    assert "营业执照" in att[0]["requirement"] and "★" in att[0]["requirement"]
    assert all(r["strategy"] == "pending" and r["status"] == "draft" for r in att)


def test_golden_declaration_and_aggregate_rows():
    """承诺条款逐条成行(clause);聚合要素行(deposit/deadline/warranty★/duration★/
    consortium)有值才造行;warranty/duration 为 star(商务承诺对照面)。"""
    rows = matrix.assemble_matrix(_fields())
    by_id = {r["clause_id"]: r for r in rows}
    decl = by_id["decl:1"]
    assert decl["kind"] == "clause" and "真实有效" in decl["requirement"]
    assert by_id["deposit"]["requirement"].startswith("投标保证金:") and "100000" in by_id["deposit"]["requirement"]
    assert by_id["deadline"]["star"] is False
    assert by_id["warranty"]["star"] is True and "24个月" in by_id["warranty"]["requirement"]
    assert by_id["duration"]["star"] is True
    assert by_id["consortium"]["requirement"].startswith("联合体:")
    # 未给的聚合路径不造行(缺行=下游可见缺口,不造假行)
    assert "volume" not in by_id and "qual_level" not in by_id and "sections" not in by_id


def test_golden_deterministic_and_sorted():
    """同输入两次装配逐行相等;输出按 (kind, clause_id) 稳定排序。"""
    r1 = matrix.assemble_matrix(_fields())
    r2 = matrix.assemble_matrix(_fields())
    assert r1 == r2
    keys = [(r["kind"], r["clause_id"]) for r in r1]
    assert keys == sorted(keys)


def test_blocked_low_confidence_unverified():
    """F1 强制标红:blocked 语义=source_path 未 quote 核验且 conf<0.6 → 该源全部行
    status=blocked(低置信未确认禁入生成);verified=True 或 conf 缺省 → draft。"""
    conf = {
        "tender.attachment_requirements": {"conf": 0.4, "verified": False},
        "tender.deposit_required": {"conf": 0.9, "verified": True},
        "tender.bid_deadline": {"conf": None, "verified": False},
    }
    rows = matrix.assemble_matrix(_fields(), conf)
    by_id = {r["clause_id"]: r for r in rows}
    assert by_id["att:1"]["status"] == "blocked" and by_id["att:3"]["status"] == "blocked"
    assert by_id["deposit"]["status"] == "draft"
    assert by_id["deadline"]["status"] == "draft"  # conf 未报不造 block(诚实缺省)
    assert by_id["decl:1"]["status"] == "draft"  # 无 conf 条目的路径=draft


def test_excerpt_truncated_with_ellipsis():
    """超长摘录截断带省略号(只抄不编;cap 120)。"""
    long_decl = "很长的承诺条款" * 40  # 280 字
    rows = matrix.assemble_matrix({"tender.required_declarations": [long_decl]})
    assert len(rows) == 1
    assert rows[0]["requirement"].endswith("…") and len(rows[0]["requirement"]) <= 121


def test_empty_fields_no_rows():
    """全空输入→零行(不造默认行;伪零纪律:显)。"""
    assert matrix.assemble_matrix({}) == []
    assert matrix.assemble_matrix({"tender.attachment_requirements": []}) == []


# ── 批十九 T7 golden cases-write(夹具yaml驱动;批二十生成器同目录续批)────────


def test_golden_cases_write_fixture():
    """夹具三例:装配输出逐行匹配 expect_rows(clause_id 全集相等+指定键相等+稳定排序);
    CW-2 空快照→零行;CW-3 钉★不继承(逐行判定律)。"""
    with open(CASES_WRITE, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]
    assert [c["case_id"] for c in cases] == ["CW-1-full-matrix", "CW-2-empty-honest-zero", "CW-3-no-star-inheritance"]
    for case in cases:
        rows = matrix.assemble_matrix(case["tender_fields"], case.get("fields_conf") or {})
        got = {r["clause_id"]: r for r in rows}
        expect = case["expect_rows"]
        assert set(got) == {e["clause_id"] for e in expect}, case["case_id"]
        for e in expect:
            for k, v in e.items():
                assert got[e["clause_id"]][k] == v, (case["case_id"], e["clause_id"], k)
        keys = [(r["kind"], r["clause_id"]) for r in rows]
        assert keys == sorted(keys)
