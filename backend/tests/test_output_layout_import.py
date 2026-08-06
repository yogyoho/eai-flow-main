"""Tests for deterministic .docx → layout-template extraction."""

from io import BytesIO

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
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


def test_heading_color_has_hash_prefix():
    """Extracted heading color must be #RRGGBB (editor <input type=color> rejects bare hex)."""
    doc = Document()
    from docx.shared import RGBColor

    doc.styles["Heading 1"].font.color.rgb = RGBColor(0x2B, 0x57, 0x9A)
    h1 = extract_layout_from_docx(_docx_bytes(doc))["heading_styles"][0]
    assert h1["color"] == "#2B579A"


def test_table_style_present_only_when_table_exists():
    assert data_for(with_table=True)["table_styles"] is not None
    # plain table has no row banding → stripeRows must be False (not invented True)
    assert data_for(with_table=True)["table_styles"]["stripeRows"] is False
    assert data_for()["table_styles"] is None


def _shaded_cell_table(*, direct_fill: str | None = None, style_firstrow_fill: str | None = None) -> bytes:
    doc = Document()
    doc.add_heading("标题", level=1)
    table = doc.add_table(rows=2, cols=2)
    if direct_fill:
        tc_pr = table.rows[0].cells[0]._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), direct_fill)
        tc_pr.append(shd)
    if style_firstrow_fill:
        table.style = "Table Grid"
        tsp = OxmlElement("w:tblStylePr")
        tsp.set(qn("w:type"), "firstRow")
        tc_pr = OxmlElement("w:tcPr")
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), style_firstrow_fill)
        tc_pr.append(shd)
        tsp.append(tc_pr)
        table.style.element.append(tsp)
    return _docx_bytes(doc)


def test_table_plain_header_is_white_not_blue():
    """Regression: a plain table (no header shading) must NOT invent a blue header."""
    ts = data_for(with_table=True)["table_styles"]
    assert ts["headerBg"] == "#FFFFFF"  # no fill detected → white, never the old #2B579A blue
    assert ts["headerColor"] == "#333333"


def test_table_direct_cell_shading_extracted():
    """A directly-shaded header cell must yield its real fill color."""
    ts = extract_layout_from_docx(_shaded_cell_table(direct_fill="D9E2F3"))["table_styles"]
    assert ts["headerBg"] == "#D9E2F3"


def test_table_style_firstrow_shading_extracted():
    """A table style with a firstRow band must yield the band fill (common Word case)."""
    ts = extract_layout_from_docx(_shaded_cell_table(style_firstrow_fill="C6E0B4"))["table_styles"]
    assert ts["headerBg"] == "#C6E0B4"


def test_table_style_banding_enables_striping():
    """stripeRows is True only when the table style defines row banding; plain → False."""
    # plain table: no banding
    assert data_for(with_table=True)["table_styles"]["stripeRows"] is False
    # banded style: defines band1Row shading
    doc = Document()
    doc.add_heading("标题", level=1)
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    tsp = OxmlElement("w:tblStylePr")
    tsp.set(qn("w:type"), "band1Row")
    tc_pr = OxmlElement("w:tcPr")
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F2F2F2")
    tc_pr.append(shd)
    tsp.append(tc_pr)
    table.style.element.append(tsp)
    assert extract_layout_from_docx(_docx_bytes(doc))["table_styles"]["stripeRows"] is True


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


def test_output_router_registers_import_layout():
    from app.extensions.output.routers import router

    paths = set()
    for route in router.routes:
        for method in getattr(route, "methods", None) or set():
            paths.add((route.path, method))
    assert ("/api/extensions/output/import-layout", "POST") in paths, "output import-layout route missing"


def test_validate_docx_upload_rejects_non_docx_filename():
    from app.extensions.output.layout_import import validate_docx_upload

    with pytest.raises(ValueError, match="仅支持 .docx 文件"):
        validate_docx_upload("report.pdf", b"PK\x03\x04" + b"\x00" * 100)


def test_validate_docx_upload_rejects_oversize():
    from app.extensions.output.layout_import import validate_docx_upload

    with pytest.raises(ValueError, match="不能超过 10MB"):
        validate_docx_upload("report.docx", b"PK\x03\x04" + b"\x00" * (10 * 1024 * 1024 + 1))


def test_validate_docx_upload_returns_extraction():
    from app.extensions.output.layout_import import validate_docx_upload

    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)
    data = _docx_bytes(doc)
    result = validate_docx_upload("report.docx", data)
    assert result["page_settings"]["paperSize"] == "A4"
