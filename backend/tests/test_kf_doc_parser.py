"""Unit tests for doc_parser — heading detection, text normalization, regex fallback.

These tests run without external services (no RAGFlow, no DB).
They verify the core parsing logic with inline test data.
"""

import pytest

from app.extensions.knowledge_factory.doc_parser import (
    DocTable,
    Heading,
    ParsedDocument,
    _is_noise_line,
    _scan_headings_regex,
    _TOC_ENTRY,
    normalize_text,
)


# ── normalize_text ──

def test_normalize_removes_punctuation_and_spaces():
    # normalize_text strips Chinese stop words and spaces, but preserves
    # structural dots (used in chapter numbering). Same heading format
    # with different whitespace normalizes to the same string.
    assert normalize_text("1 总则") == normalize_text("1总则")
    assert normalize_text("一、 概述") == normalize_text("一概述")
    # Dot is structural (distinguishes "1.1" from "11"), intentionally preserved
    assert "." in normalize_text("1.1 任务由来")


def test_normalize_case_insensitive():
    assert normalize_text("ABC") == normalize_text("abc")


def test_normalize_chinese_stop_words():
    """的、，。；：（） should be stripped."""
    result = normalize_text("第一章 的 概述，内容")
    assert "的" not in result
    assert "，" not in result


# ── _scan_headings_regex ──

def test_regex_detects_numbered_chapters():
    text = """1. 总则
1.1 任务由来
2. 建设项目概况
3. 工程分析
14. 结论与建议"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    assert "1. 总则" in titles
    assert "2. 建设项目概况" in titles
    assert "14. 结论与建议" in titles


def test_regex_levels_correct():
    text = """1. 总则
1.1 任务由来
1.1.1 评价目的
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    by_title = {h.title: h.level for h in headings}
    assert by_title["1. 总则"] == 1
    assert by_title["1.1 任务由来"] == 2
    assert by_title["1.1.1 评价目的"] == 3
    assert by_title["2. 建设项目概况"] == 1


def test_regex_chinese_chapter_patterns():
    text = """第一章 总则
第一节 任务由来
（一）评价范围
一、概述"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    assert "第一章 总则" in titles


def test_regex_deduplicates():
    """Repeated titles (page headers) should be deduplicated."""
    text = """1. 总则
1. 总则
1. 总则
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    assert len(headings) == 2


def test_regex_skips_toc_entries():
    """TOC lines ending with page numbers should be skipped."""
    text = """1. 总则\t3
1.1 任务由来     5
2. 建设项目概况"""
    headings = _scan_headings_regex(text)
    titles = {h.title for h in headings}
    # TOC entries skipped, only real heading remains
    assert "2. 建设项目概况" in titles
    assert len(headings) == 1


# ── _is_noise_line ──

def test_noise_detects_survey_items():
    assert _is_noise_line("1、您了解本项目的环境影响吗？") is True
    assert _is_noise_line("2、噪声：合理布局，噪声高的设备需要采用低噪声设备并进行减振处理") is True


def test_noise_passes_real_headings():
    assert _is_noise_line("1. 总则") is False
    assert _is_noise_line("2. 建设项目概况") is False
    assert _is_noise_line("第一章 总则") is False


# ── TOC detection ──

def test_toc_detects_page_numbers():
    assert _TOC_ENTRY.match("1. 总则\t3") is not None
    assert _TOC_ENTRY.match("1.1 任务由来     5") is not None


def test_toc_ignores_normal_headings():
    assert _TOC_ENTRY.match("1. 总则") is None
    assert _TOC_ENTRY.match("2. 建设项目概况") is None


# ── Heading dataclass ──

def test_heading_fields():
    h = Heading(title="1. 总则", level=1, line_number=5, style_name="Heading 1")
    assert h.level == 1
    assert h.title == "1. 总则"


# ── DocTable dataclass ──

def test_doc_table_fields():
    t = DocTable(
        caption="表 1-1 监测点位",
        columns=["编号", "经度", "纬度"],
        rows=[["1#", "120.5", "30.2"]],
    )
    assert len(t.columns) == 3
    assert len(t.rows) == 1


# ── ParsedDocument dataclass ──

def test_parsed_document_empty():
    doc = ParsedDocument(file_path="/tmp/test.docx", file_type="docx")
    assert doc.headings == []
    assert doc.tables == []
    assert doc.full_text == ""


def test_parsed_document_error():
    doc = ParsedDocument(file_path="/tmp/bad.pdf", file_type="pdf", error="PDF 无可提取文字")
    assert doc.error != ""
    assert doc.error == "PDF 无可提取文字"


# ── Grounding: 精确章节切片 ──

def test_finalize_sections_exact_slice():
    """finalize_sections 算 text_offset，section_text_by_title subtree 含子节。"""
    paragraphs = ["1 总则", "本章节介绍项目背景。", "1.1 任务由来", "任务由来说明。", "2 工程分析", "工艺流程内容。"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [
        Heading(title="1 总则", level=1, para_idx=0),
        Heading(title="1.1 任务由来", level=2, para_idx=2),
        Heading(title="2 工程分析", level=1, para_idx=4),
    ]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    # H1 "1 总则" subtree 到下一个 H1，含子节 1.1
    assert "任务由来说明" in doc.section_text_by_title("1 总则", level=1)
    assert "工艺流程" not in doc.section_text_by_title("1 总则", level=1)
    # H2 "1.1" 叶子切片
    h2_text = doc.section_text_by_title("1.1 任务由来", level=2)
    assert "任务由来说明" in h2_text
    assert "1 总则" not in h2_text


def test_section_text_by_title_normalizes_spaces():
    """标题带多余空格时，normalize 后仍能匹配到精确切片。"""
    paragraphs = ["1 总  则", "总则正文内容。", "2 概述", "概述内容。"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="1 总  则", level=1, para_idx=0), Heading(title="2 概述", level=1, para_idx=2)]
    doc.finalize_sections(paragraphs)
    doc.full_text = "\n\n".join(paragraphs)
    text = doc.section_text_by_title("1 总则", level=1)
    assert "总则正文内容" in text


def test_section_text_by_title_empty_when_regex_fallback():
    """regex 兜底的 heading 无 para_idx（text_offset=-1），返回空串让调用方回退。"""
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="第一章 总则", level=1, para_idx=-1)]
    doc.full_text = "第一章 总则 正文"
    assert doc.section_text_by_title("第一章 总则") == ""


# ── section_length (min_section_length 过滤支撑) ──

def test_section_length_subtree():
    """section_length 返回 heading 子树字符长度（含子节）。"""
    paragraphs = ["1 总则", "正文A较长内容。" * 10, "2 概述", "短"]
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="1 总则", level=1, para_idx=0),
                    Heading(title="2 概述", level=1, para_idx=2)]
    doc.full_text = "\n\n".join(paragraphs)
    doc.finalize_sections(paragraphs)
    # H1 "1 总则" 子树到 H1 "2 概述"，应较长
    assert doc.section_length(0) > 50
    # H1 "2 概述" 到文末，较短
    assert doc.section_length(1) < 10


def test_section_length_no_anchor_returns_zero():
    """无锚点的 heading（regex 兜底）返回 0，调用方保留不过滤。"""
    doc = ParsedDocument(file_path="x", file_type="docx")
    doc.headings = [Heading(title="第一章", level=1, para_idx=-1, text_offset=-1)]
    doc.full_text = "正文"
    assert doc.section_length(0) == 0


# ── expat handler: 真实命名空间 docx ──

def test_expat_extracts_namespaced_docx(tmp_path):
    """expat 必须从带 xmlns:w 命名空间的真实 Word XML 提取标题/表格。

    回归: namespace_separator=':' 曾导致 name 变 URI 形式，name=='p' 失效，
    expat 返回空，静默回退 python-docx。此测试用真实命名空间 docx 覆盖。
    """
    import zipfile
    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat
    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>正文</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>c1</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:r><w:t>c2</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '</w:document>'
    ).encode("utf-8")
    fp = tmp_path / "t.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None
    assert len(r.headings) == 1, f"expat 应提取 H1，得 {len(r.headings)}（namespace 比较可能失效）"
    assert r.headings[0].level == 1
    assert len(r.tables) == 1
    assert r.tables[0].columns == ["c1", "c2"]


def test_expat_gridspan_horizontal_merge(tmp_path):
    """gridSpan 水平合并：跨列 cell 内容复制对齐列数。"""
    import zipfile
    from app.extensions.knowledge_factory.doc_parser import _parse_docx_expat
    doc_xml = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:tbl><w:tr>'
        '<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>merged</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:r><w:t>c3</w:t></w:r></w:p></w:tc>'
        '</w:tr></w:tbl></w:document>'
    ).encode("utf-8")
    fp = tmp_path / "g.docx"
    with zipfile.ZipFile(fp, "w") as zf:
        zf.writestr("word/document.xml", doc_xml)
    r = _parse_docx_expat(fp)
    assert r is not None and len(r.tables) == 1
    cols = r.tables[0].columns
    assert len(cols) == 3, f"gridSpan=2 应展开成3列，得 {len(cols)}: {cols}"
    assert cols[0] == "merged" and cols[1] == "merged"
