"""Tests for the structured cover element model (replaces cover_master passthrough)."""
from pathlib import Path

import pytest
from docx import Document
from pydantic import ValidationError

from app.extensions.output.layout_import import _extract_cover_pages
from app.extensions.output.schemas import (
    CoverElementSchema,
    CoverSchema,
    LayoutTemplateCreate,
)

SAMPLE1 = Path("C:/Temp/eai-cover1-消防.docx")   # 基地项目-消防设计专篇
SAMPLE2 = Path("C:/Temp/eai-cover2-环评.docx")   # 横城矿区环评报告


def _cover_of(path):
    return _extract_cover_pages(Document(str(path)))


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


def test_fire_sample_single_page_with_table_elements():
    """消防设计专篇: 1 页, 含文本元素(标题横幅/项目编号) + 会签表元素."""
    pages = _cover_of(SAMPLE1)
    assert len(pages) == 1, f"消防样例应为 1 页, got {len(pages)}"
    els = pages[0].elements
    texts = [e.text for e in els if e.type == "text"]
    assert any("第三册 消防设计专篇" in t for t in texts), "报告名称文本元素缺失"
    assert any(t.strip() == "项目名" for t in texts), "独立项目名占位元素缺失"
    tables = [e for e in els if e.type == "table"]
    assert tables, "会签表应为表格元素"
    assert tables[0].rows >= 10, f"会签表 rows 应 >=10, got {tables[0].rows}"
    assert tables[0].cols >= 5, f"会签表 cols 应 >=5(实为6), got {tables[0].cols}"
    bound = {e.slotId: e for e in els if e.slotId}
    assert bound.get("project_number"), "项目编号:XX 应绑 project_number"
    assert bound.get("date"), "20XX年0X月 应绑 date"
    ids = [e.id for e in els]
    assert len(ids) == len(set(ids)), f"元素 id 应唯一, got {len(ids)} els / {len(set(ids))} unique"


def test_huanping_sample_three_pages():
    """环评报告: 3 页 (封面/批准页/名单页), 含名单表格."""
    pages = _cover_of(SAMPLE2)
    assert len(pages) == 3, f"环评样例应为 3 页, got {len(pages)}"
    p1_texts = [e.text for e in pages[0].elements if e.type == "text"]
    assert any("环境影响报告书" in t for t in p1_texts)
    p2_texts = " ".join(e.text for e in pages[1].elements)
    assert "工程" in p2_texts and "H7367Z" in p2_texts
    p3_tables = [e for e in pages[2].elements if e.type == "table"]
    assert len(p3_tables) == 2, f"名单页应 2 张表, got {len(p3_tables)}"
    assert p3_tables[1].rows >= 16
    assert p3_tables[0].cols >= 3, f"名单页首表 cols 应 >=3(实为3), got {p3_tables[0].cols}"
    ids = [e.id for p in pages for e in p.elements]
    assert len(ids) == len(set(ids)), f"元素 id 应唯一, got {len(ids)} els / {len(set(ids))} unique"
