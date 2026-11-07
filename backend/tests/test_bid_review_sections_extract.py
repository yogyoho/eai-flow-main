"""M2 章节层契约+归一闸+prompt/baseline 单测(spec 2026-11-04 §5,2026-11-05)。"""

from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    _scan_heading_anchors,
    build_sections_baseline,
    build_sections_prompt,
    normalize_section_tree,
)


class TestNormalizeSectionTree:
    def test_contract_registered(self):
        assert "bid.section_tree" in FIELD_TYPE_CONTRACTS

    def test_valid_row_server_computes_offset(self):
        rows = normalize_section_tree([{"code": "3", "title": "技术方案", "toc_page": 10, "body_page": 12, "is_empty": False}])
        assert rows == [{"code": "3", "title": "技术方案", "toc_page": 10, "body_page": 12, "is_empty": False, "offset": 2, "offset_flag": False}]

    def test_offset_over_five_flags(self):
        rows = normalize_section_tree([{"title": "商务偏差", "toc_page": 3, "body_page": 20}])
        assert rows[0]["offset"] == 17
        assert rows[0]["offset_flag"] is True

    def test_pages_missing_offset_none(self):
        rows = normalize_section_tree([{"title": "A", "toc_page": 5}, {"title": "B", "body_page": 7}])
        assert rows[0]["offset"] is None and rows[0]["offset_flag"] is None
        assert rows[1]["offset"] is None and rows[1]["offset_flag"] is None

    def test_junk_pages_nulled(self):
        rows = normalize_section_tree([{"title": "A", "toc_page": True, "body_page": "3"}])
        assert rows[0]["toc_page"] is None and rows[0]["body_page"] is None

    def test_page_one_valid_zero_offset_not_flagged(self):
        rows = normalize_section_tree([{"title": "A", "toc_page": 1, "body_page": 1}])
        assert rows[0]["offset"] == 0
        assert rows[0]["offset_flag"] is False

    def test_is_empty_non_bool_nulled(self):
        assert normalize_section_tree([{"title": "A", "is_empty": "yes"}])[0]["is_empty"] is None

    def test_dropped_rows_zero_fabrication(self):
        rows = normalize_section_tree(["junk", {}, {"toc_page": 1}, {"title": "  "}, {"code": 1, "title": "T", "toc_page": "x"}])
        assert len(rows) == 1
        assert rows[0]["title"] == "T"

    def test_non_list(self):
        assert normalize_section_tree(None) == []
        assert normalize_section_tree("junk") == []
        assert normalize_section_tree({"a": 1}) == []

    def test_code_stripped_title_spacing_kept(self):
        rows = normalize_section_tree([{"code": " 3 ", "title": "技术 方案"}])
        assert rows[0]["code"] == "3"
        assert rows[0]["title"] == "技术 方案"


class TestPromptAndBaseline:
    def test_prompt_contains_inputs_and_contract(self):
        docs = [{"doc_id": "b.pdf", "role": "bid", "text": "目录 [[p.2]] 3 技术方案 [[p.12]]"}]
        prompt = build_sections_prompt(docs, ["3", "5"], [{"code": "3"}])
        assert "章节结构定位器" in prompt
        assert '"3"' in prompt  # toc codes
        assert "[[p." in prompt
        assert FIELD_TYPE_CONTRACTS["bid.section_tree"] in prompt
        assert "禁止编造" in prompt
        assert "指令性文字" in prompt

    def test_baseline_unwraps_and_normalizes(self):
        docs = [{"doc_id": "b.pdf", "role": "bid", "text": "x"}]

        def fake_fn(docs, toc_codes, required):
            return {"sections": [{"title": "技术方案", "toc_page": 10, "body_page": 12}]}

        rows = build_sections_baseline(docs, fake_fn, ["3"], None)
        assert rows[0]["offset"] == 2

    def test_baseline_bare_list(self):
        rows = build_sections_baseline([], lambda *a: [{"title": "A"}], None, None)
        assert rows[0]["title"] == "A"

    def test_baseline_none_signal(self):
        assert build_sections_baseline([], lambda *a: None, None, None) == []


class TestHeadingAnchors:
    """批四章节兜底(A-β4-①②):确定性标题锚点扫描 + prompt 注入(hint 通道,签名零变)。"""

    def test_scan_hits_three_families_with_page(self):
        docs = [
            {
                "doc_id": "d1",
                "text": "前言叙述文字\n[[p.3]]\n第一章 施工组织设计\n正文内容\n[[p.5]]\n一、总体部署\n[[p.7]]\n1.1 人员配置",
            }
        ]
        anchors = _scan_heading_anchors(docs)
        assert [a["title"] for a in anchors] == ["第一章 施工组织设计", "一、总体部署", "1.1 人员配置"]
        assert [a["page"] for a in anchors] == [3, 5, 7]
        assert [a["kind"] for a in anchors] == ["chapter", "cn_enum", "arabic"]

    def test_scan_rejects_non_headings_and_caps(self):
        # 数字开头非标题形(无分隔符)不中
        docs = [{"doc_id": "d1", "text": "2026年开工\n3.5万元预算\n普通叙述文字不匹配"}]
        assert _scan_heading_anchors(docs) == []
        # 上限 80 截断(A-β4-⑧)
        many = [{"doc_id": "d", "text": "\n".join(f"第{i}章 标题{i}" for i in range(100))}]
        assert len(_scan_heading_anchors(many)) == 80

    def test_prompt_injects_anchor_block_only_when_present(self):
        with_anchors = build_sections_prompt([{"doc_id": "d1", "text": "[[p.2]]\n第一章 概述"}], [], [])
        assert "正文标题锚点候选" in with_anchors
        assert "第一章 概述" in with_anchors
        assert "仅供参考" in with_anchors
        plain = build_sections_prompt([{"doc_id": "d1", "text": "没有任何标题形的普通文本"}], [], [])
        assert "正文标题锚点候选" not in plain
        # 铁律与既有结构原样(A-β4-①禁编造不动)
        assert "禁止编造章节" in with_anchors
        assert "定位不到的目录节就跳过" in with_anchors

    def test_prompt_empty_toc_with_anchors_still_honest(self):
        # 空 TOC + 锚点:契约文本(code 空串合法)与锚点候选同在,模型可诚实产出
        prompt = build_sections_prompt([{"doc_id": "d1", "text": "[[p.4]]\n第二章 商务文件"}], [], [])
        assert "第二章 商务文件" in prompt
        assert '"code"' in prompt  # 输出契约仍在
