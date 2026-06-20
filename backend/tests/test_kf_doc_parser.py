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
