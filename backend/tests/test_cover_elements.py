"""Tests for the structured cover element model (replaces cover_master passthrough)."""
import pytest
from pydantic import ValidationError

from app.extensions.output.schemas import (
    CoverElementSchema,
    CoverSchema,
    LayoutTemplateCreate,
)


def test_cover_schema_roundtrip():
    cover = CoverSchema(
        sourceFile="x.docx",
        pages=[
            {
                "elements": [
                    {"id": "e1", "type": "text", "text": "项目名", "alignment": "center", "fontSize": 22, "bold": True},
                    {"id": "e2", "type": "table", "rows": 2, "cols": 2, "cells": [["专业名称", "编制"], ["总图", ""]]},
                ]
            }
        ],
    )
    d = cover.model_dump()
    assert d["mode"] == "elements"
    assert d["pages"][0]["elements"][0]["text"] == "项目名"
    assert d["pages"][0]["elements"][1]["cells"][0][0] == "专业名称"


def test_cover_element_type_validated():
    with pytest.raises(ValidationError):
        CoverElementSchema(id="x", type="canvas", text="t")


def test_layout_template_create_accepts_cover_elements():
    tpl = LayoutTemplateCreate(
        name="T",
        report_type="g",
        page_settings={"paperSize": "A4", "orientation": "portrait", "marginTop": 2.54, "marginBottom": 2.54, "marginLeft": 3.17, "marginRight": 3.17},
        body_styles={"fontFamily": "宋体", "fontSize": 12, "lineHeight": 1.5, "paragraphSpacing": 0, "firstLineIndent": 2},
        heading_styles=[],
        cover_elements={"sourceFile": "x.docx", "pages": [{"elements": [{"id": "e1", "type": "text", "text": "报告标题"}]}]},
    )
    assert tpl.cover_elements.pages[0].elements[0].text == "报告标题"
