"""Tests for cover-master OOXML passthrough + slot binding (B1)."""

import base64  # noqa: F401  # used in later tasks (B2+ image encoding)
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest  # noqa: F401  # used in later tasks (B2+ fixtures/markers)
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: F401  # used in later tasks (B2+ OOXML asserts)
from docx.oxml import OxmlElement  # noqa: F401  # used in later tasks (B2+ OOXML construction)
from docx.oxml.ns import qn  # noqa: F401  # used in later tasks (B2+ OOXML asserts)
from docx.shared import Cm, Pt  # noqa: F401  # used in later tasks (B2+ layout asserts)

from app.extensions.output.layout_import import extract_layout_from_docx  # noqa: F401  # used in later tasks (B2+)
from app.extensions.output.schemas import CoverMasterSchema, CoverSlotSchema

SAMPLE = Path("backend/data/users/f8766d55-2b1b-422e-a945-5fcf268a8a39/knowledge/8376f624-95de-47b1-b871-0bb000b5a934/基地项目-消防设计专篇.docx")


def _docx_bytes(doc: Document) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Task 1: schema + wiring ────────────────────────────────────────────────


def test_cover_master_schema_camelcase_and_defaults():
    m = CoverMasterSchema(
        xml="<w:p/>",
        slots=[CoverSlotSchema(id="client", label="建设单位", sampleValue="甲公司", defaultFrom="frontmatter:client")],
    )
    d = m.model_dump()
    assert d["mode"] == "master"
    assert d["sourceFile"] == ""
    assert d["boundary"] == "before_toc"
    assert d["images"] == []
    assert d["slots"][0]["sampleValue"] == "甲公司"
    assert d["slots"][0]["defaultFrom"] == "frontmatter:client"
    assert d["slots"][0]["kind"] == "variable"


def test_build_template_data_includes_cover_master():
    from app.extensions.output.routers import _build_template_data

    tpl = SimpleNamespace(
        page_settings={},
        body_styles={},
        heading_styles=[],
        table_styles=None,
        figure_styles=None,
        header_footer=None,
        reference_style="gb7714",
        appendix_rules=None,
        cover_template=None,
        toc_settings=None,
        cover_master={"mode": "master", "xml": "<w:p/>", "images": [], "slots": [], "sourceFile": "x.docx", "boundary": "before_toc"},
    )
    td = _build_template_data(tpl)
    assert td["cover_master"]["mode"] == "master"


# ── Task 2: extraction ────────────────────────────────────────────────────


def _make_table_cover_docx() -> bytes:
    """Synthetic replica of the real sample's cover: empty spacer, title-banner
    table, a 建设单位 line, a 会签 table, a 目录 marker, then the body heading."""
    doc = Document()
    s = doc.sections[0]
    s.page_width = Cm(21.0)
    s.page_height = Cm(29.7)

    doc.add_paragraph()  # leading blank spacer

    # table[0]: title banner (single cell, big font)
    t1 = doc.add_table(rows=1, cols=1)
    banner = t1.rows[0].cells[0].paragraphs[0]
    run = banner.add_run("基地项目 消防设计专篇")
    run.font.size = Pt(22)
    run.bold = True

    doc.add_paragraph("建设单位：甲公司")  # client line (body-level paragraph)

    # table[1]: 编制会签表
    doc.add_table(rows=2, cols=2)

    doc.add_paragraph("目录")  # TOC marker (Normal style, text-based)
    doc.add_heading("第一章 概述", level=1)  # body
    return _docx_bytes(doc)


def test_extract_cover_master_table_cover():
    data = extract_layout_from_docx(_make_table_cover_docx(), source_file="sample.docx")
    cm = data["cover_master"]
    assert cm is not None
    assert cm["boundary"] == "before_toc"
    assert cm["xml"].count("<w:tbl ") == 2  # banner + 会签 (trailing space excludes <w:tblPr/<w:tblGrid/etc.)
    assert cm["images"] == []
    assert cm["sourceFile"] == "sample.docx"
    ids = {s["id"] for s in cm["slots"]}
    assert "client" in ids
    assert "title" in ids
    assert data["cover_detected"] is True


def test_extract_cover_master_none_for_plain_doc():
    """Body starts with a Heading, nothing before → no cover master."""
    doc = Document()
    doc.add_heading("第一章 概述", level=1)
    doc.add_paragraph("正文。")
    assert extract_layout_from_docx(_docx_bytes(doc))["cover_master"] is None


def test_extract_cover_master_none_for_toc_pre_region():
    """TOC-styled entries before the heading → no cover (regression guard)."""
    from docx.enum.style import WD_STYLE_TYPE

    doc = Document()
    try:
        toc = doc.styles.add_style("toc 1", WD_STYLE_TYPE.PARAGRAPH)
    except ValueError:
        toc = doc.styles["toc 1"]
    doc.add_paragraph("第一章 概述 .......... 1", style=toc)
    doc.add_heading("第一章 概述", level=1)
    assert extract_layout_from_docx(_docx_bytes(doc))["cover_master"] is None


@pytest.mark.skipif(not SAMPLE.exists(), reason="real sample not checked into repo")
def test_extract_real_sample_cover_master():
    data = extract_layout_from_docx(SAMPLE.read_bytes(), source_file="基地项目-消防设计专篇.docx")
    cm = data["cover_master"]
    assert cm is not None, "real sample should yield a cover master"
    assert cm["xml"].count("<w:tbl") >= 2
    assert cm["images"] == []
    assert cm["boundary"] in ("before_toc", "before_first_heading")
    assert cm["sourceFile"] == "基地项目-消防设计专篇.docx"
    assert "title" in {s["id"] for s in cm["slots"]}
