"""批卅 T1:quote_repair golden(修复=原文复制;编造/短摘录/错文档=诚实放弃)。"""

from app.extensions.bid_write.quote_repair import repair_quotes

DOCS = [
    {
        "doc_id": "T",
        "text": "投标保证金:人民币伍万元整(¥50,000.00),应当从基本账户转出。"
        "第三章 评标办法详见附件二。投标截止时间:2026年12月1日09时30分。",
    }
]


def _prov(quote: str, doc_id: str = "T") -> dict:
    return {"t.deposit_required": {"doc_id": doc_id, "quote": quote}}


def test_verbatim_fast_path_untouched():
    prov = _prov("人民币伍万元整")
    stats = repair_quotes(prov, DOCS)
    assert stats["verified_fast"] == 1 and stats["repaired"] == 0
    assert prov["t.deposit_required"]["quote"] == "人民币伍万元整"


def test_punct_width_variant_repaired_to_verbatim():
    # AI 版:标点丢失+全角数字改写 → 归一后高相似 → 复制原文片段
    prov = _prov("投标保证金 人民币伍万元整 ¥５００００００ 应当从基本账户转出")
    stats = repair_quotes(prov, DOCS)
    assert stats["repaired"] == 1
    q = prov["t.deposit_required"]["quote"]
    assert "人民币伍万元整(¥50,000.00)" in q  # 原文逐字(含全角括号/千分位)
    assert "".join(q.split()) in "".join(DOCS[0]["text"].split())  # 必为原文子串
    assert prov["t.deposit_required"]["repaired"] is True


def test_hallucinated_number_not_repaired():
    prov = _prov("投标保证金人民币壹拾万元整,应当从一般账户转出")  # 金额/账户都错
    stats = repair_quotes(prov, DOCS)
    assert stats["unrepaired"] == 1
    assert "repaired" not in prov["t.deposit_required"]


def test_short_quote_skipped():
    prov = _prov("保证金五万")  # 走样(五≠伍)且归一后仅 5 字 < 8 → 诚实跳过
    stats = repair_quotes(prov, DOCS)
    assert stats["skipped_short"] == 1


def test_wrong_doc_unrepaired():
    prov = _prov("投标保证金人民币伍万元整", doc_id="OTHER")
    stats = repair_quotes(prov, DOCS)
    assert stats["unrepaired"] == 1


def test_empty_quote_ignored():
    stats = repair_quotes({"p": {"doc_id": "T", "quote": ""}}, DOCS)
    assert stats["scanned"] == 0
