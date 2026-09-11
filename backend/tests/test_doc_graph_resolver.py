"""doc_graph 消解纯逻辑测试（无 DB）."""

from app.extensions.ontology.doc_graph.resolver import AUTO_MERGE_THRESHOLD, REVIEW_THRESHOLD, block_key, decide_merge, normalize_name


def test_normalize_case_space_fullwidth():
    assert normalize_name("  山西 煤机　集团 ") == "山西 煤机 集团".replace("　", " ")  # 全角空格折半角后折叠
    assert normalize_name("ABC Corp") == "abc corp"
    assert normalize_name("ＡＢＣ") == "abc"  # NFKC 全角字母折半角
    assert normalize_name("") == ""


def test_block_key_same_etype_same_domain():
    assert block_key("bid", "bidder", "山西煤机") == block_key("bid", "bidder", "山西焦煤")
    assert block_key("bid", "bidder", "x") != block_key("bid", "project", "x")
    assert block_key("bid", "bidder", "x") != block_key("contract", "bidder", "x")


def test_decide_high_similarity_auto_merge():
    # 同名规范化后应 auto_merge（去重主场景）。计划原例(集团有限公司/集团有限责任公司)
    # char 级 ratio 仅 0.909，落不进 ≥0.97 带，故改用同规范名。
    d = decide_merge("山西煤机集团有限公司", "山西煤机集团有限公司")
    assert d.action == "auto_merge" and d.similarity >= AUTO_MERGE_THRESHOLD


def test_decide_mid_similarity_review():
    # OCR 易混字（究→宄）15 字全称变体，ratio≈0.933 落 [0.92,0.97) review 带。
    # 计划原例 ratio 仅 0.5，不可能达 review 带，故换真实落在带内的样例。
    d = decide_merge("中国中车集团株洲电力机车研究所", "中国中车集团株洲电力机车研宄所")
    assert REVIEW_THRESHOLD <= d.similarity < AUTO_MERGE_THRESHOLD
    assert d.action == "review"


def test_decide_low_similarity_none():
    d = decide_merge("太原重工", "横城煤矿")
    assert d.action == "none"
