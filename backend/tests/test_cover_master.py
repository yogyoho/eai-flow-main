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

SAMPLE = Path(
    "backend/data/users/f8766d55-2b1b-422e-a945-5fcf268a8a39/knowledge/"
    "8376f624-95de-47b1-b871-0bb000b5a934/基地项目-消防设计专篇.docx"
)


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
        page_settings={}, body_styles={}, heading_styles=[], table_styles=None,
        figure_styles=None, header_footer=None, reference_style="gb7714",
        appendix_rules=None, cover_template=None, toc_settings=None,
        cover_master={"mode": "master", "xml": "<w:p/>", "images": [], "slots": [], "sourceFile": "x.docx", "boundary": "before_toc"},
    )
    td = _build_template_data(tpl)
    assert td["cover_master"]["mode"] == "master"
