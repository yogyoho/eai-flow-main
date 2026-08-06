"""Tests for deterministic .docx → layout-template extraction."""

from io import BytesIO

import pytest
from docx import Document
from docx.shared import Cm, Pt

from app.extensions.output.layout_import import extract_layout_from_docx


def _docx_bytes(doc: Document) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_docx(*, body_font: str | None = None, heading_font: str | None = None, with_table: bool = False) -> bytes:
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    s.top_margin = Cm(2.0)
    s.bottom_margin = Cm(2.0)
    s.left_margin = Cm(3.0)
    s.right_margin = Cm(3.0)
    if body_font:
        normal = doc.styles["Normal"]
        normal.font.name = body_font
        normal.font.size = Pt(12)
    if heading_font:
        h1 = doc.styles["Heading 1"]
        h1.font.name = heading_font
        h1.font.size = Pt(16)
    if with_table:
        doc.add_table(rows=2, cols=2)
    doc.add_heading("第一章 概述", level=1)
    doc.add_paragraph("这是正文内容，用于测试提取。")
    return _docx_bytes(doc)


def data_for(**kw):
    return extract_layout_from_docx(_make_docx(**kw))


def test_extracts_page_settings():
    data = extract_layout_from_docx(_make_docx())
    ps = data["page_settings"]
    assert ps["paperSize"] == "A4"
    assert ps["orientation"] == "portrait"
    assert ps["marginTop"] == 2.0
    assert ps["marginBottom"] == 2.0
    assert ps["marginLeft"] == 3.0
    assert ps["marginRight"] == 3.0


def test_extracts_body_and_heading_fonts():
    data = extract_layout_from_docx(_make_docx(body_font="SimSun", heading_font="SimHei"))
    assert data["body_styles"]["fontSize"] == 12
    assert data["body_styles"]["fontFamily"] == "SimSun"
    h1 = data["heading_styles"][0]
    assert h1["level"] == 1
    assert h1["fontFamily"] == "SimHei"
    assert h1["fontSize"] == 16
    assert h1["numbering"] == "decimal"


def test_table_style_present_only_when_table_exists():
    assert data_for(with_table=True)["table_styles"] is not None
    assert data_for(with_table=True)["table_styles"]["stripeRows"] is True
    assert data_for()["table_styles"] is None


def test_figure_styles_null():
    assert data_for()["figure_styles"] is None


def test_no_cover_detected_for_plain_document():
    assert data_for()["cover_detected"] is False


def test_cover_logo_position_left_for_default_left_alignment():
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    doc.add_paragraph("某化工项目消防设计专篇")  # no explicit alignment → None → left
    doc.add_paragraph("建设单位：某某公司")
    doc.add_paragraph("项目编号：P001")
    doc.add_heading("第一章 概述", level=1)
    data = extract_layout_from_docx(_docx_bytes(doc))
    assert data["cover_detected"] is True
    assert data["cover_template"]["logoPosition"] == "left"


def test_cover_detected_for_first_page_cover():
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    title = doc.add_paragraph("某化工项目消防设计专篇")
    title.runs[0].font.size = Pt(22)
    doc.add_paragraph("建设单位：某某公司")
    doc.add_paragraph("项目编号：P001")
    doc.add_paragraph("2026-08-01")
    doc.add_heading("第一章 概述", level=1)
    data = extract_layout_from_docx(_docx_bytes(doc))
    assert data["cover_detected"] is True
    ct = data["cover_template"]
    assert ct["showTitle"] is True
    assert ct["showClient"] is True
    assert ct["showProjectNumber"] is True
    assert ct["showDate"] is True


def test_rejects_non_docx_bytes():
    with pytest.raises(ValueError):
        extract_layout_from_docx(b"this is definitely not a docx file")
