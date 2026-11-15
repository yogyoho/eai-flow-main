"""FormatProfile→AST 与招标版式 DOCX 渲染(P1,EAI-CUSTOM 2026-11-15)。"""

from __future__ import annotations

import io
import json
import zipfile

from docx import Document

from app.extensions.bid_write.export_docx import render_ast_to_docx
from app.extensions.bid_write.format_profile import extract_format_profile
from app.extensions.bid_write.generate.format_ast import format_profile_to_ast

_FIXED = "我方承诺本投标文件真实有效，并承担相应法律责任。"


class _Task:
    project_name = "某矿井智能化建设项目"
    lot_name = "一标段"
    tender_no = "TB-2026-001"


def _ctx() -> dict:
    return {
        "tender": {"tender.purchaser_name": "中煤科工集团"},
        "material": {"bidder_profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"}},
        "products": {
            "price_sheet": {"detail_total": 1280000, "amount_cn": "壹佰贰拾捌万元整"},
            "bid_letter": {"slots": {"total_amount_num": 1280000}},
        },
        "knobs": {"sign_date": "2026年11月15日"},
    }


def _tender_docx() -> bytes:
    document = Document()
    document.sections[0].header.paragraphs[0].text = "招标文件页眉"
    document.add_paragraph("第六章 投标文件格式", style="Heading 1")
    document.add_paragraph("投标文件目录")
    document.add_paragraph("一  投标函")
    document.add_paragraph("二  投标保证金")

    document.add_paragraph("一、投标函", style="Heading 1")
    document.add_paragraph("致：________（招标人名称）")
    document.add_paragraph(_FIXED)
    document.add_paragraph("项目名称：________")

    table = document.add_table(rows=3, cols=3)
    table.cell(0, 0).text = "项目名称"
    table.cell(0, 2).text = "金额"
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(1, 0).text = "报价"
    table.cell(1, 1).text = "________"
    table.cell(1, 2).text = "100"
    table.cell(1, 0).merge(table.cell(2, 0))
    table.cell(2, 1).text = "备注"
    table.cell(2, 2).text = "200"

    document.add_paragraph("二、投标保证金", style="Heading 1")
    document.add_paragraph("投标人（盖章）：")
    document.add_paragraph("（此处贴营业执照扫描件）")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _walk(node: dict) -> list[dict]:
    out = [node]
    for child in node.get("content") or []:
        if isinstance(child, dict):
            out.extend(_walk(child))
    return out


def test_format_profile_to_ast_builds_sections_fixed_text_and_placeholders():
    profile = extract_format_profile(_tender_docx(), doc_id="tender")
    ast = format_profile_to_ast(profile, task=_Task(), ctx=_ctx())
    assert ast is not None
    nodes = _walk(ast)
    sections = [node for node in nodes if node.get("type") == "section"]
    assert [node["attrs"]["title"] for node in sections] == ["一、投标函", "二、投标保证金"]

    locked = [node for node in nodes if node.get("type") == "locked_paragraph"]
    texts = ["".join(child.get("text") or "" for child in node.get("content") or [] if child.get("type") == "text") for node in locked]
    assert _FIXED in texts

    placeholders = [node for node in nodes if node.get("type") == "placeholder"]
    by_source = {node["attrs"]["source"]: node["attrs"]["value"] for node in placeholders if node["attrs"]["source"]}
    assert by_source["project_name"] == "某矿井智能化建设项目"
    assert by_source["purchaser_name"] == "中煤科工集团"


def test_format_profile_to_ast_maps_merged_cells_to_anchor_only():
    profile = extract_format_profile(_tender_docx(), doc_id="tender")
    ast = format_profile_to_ast(profile, task=_Task(), ctx=_ctx())
    tables = [node for node in _walk(ast) if node.get("type") == "table"]
    assert len(tables) == 1
    rows = tables[0]["content"]
    assert len(rows) == 3

    first_row = rows[0]["content"]
    assert first_row[0]["attrs"]["col_span"] == 2
    assert "项目名称" in "".join(child.get("text") or "" for child in first_row[0]["content"])

    second_row = rows[1]["content"]
    assert second_row[0]["attrs"]["row_span"] == 2
    third_row_texts = ["".join(child.get("text") or "" for child in cell.get("content") or []) for cell in rows[2]["content"]]
    assert "报价" not in third_row_texts
    assert "备注" in third_row_texts


def test_format_ast_export_keeps_spans_layout_and_header():
    profile = extract_format_profile(_tender_docx(), doc_id="tender")
    ast = format_profile_to_ast(profile, task=_Task(), ctx=_ctx())
    data = render_ast_to_docx(ast, profile=profile, watermark="review")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        header_xml = archive.read("word/header1.xml").decode("utf-8")
    assert "gridSpan" in document_xml
    assert "vMerge" in document_xml
    assert "某矿井智能化建设项目" in document_xml
    assert "招标文件页眉" in header_xml
    assert "送审稿" in header_xml


def test_format_ast_is_deterministic_and_falls_back_without_format_section():
    profile = extract_format_profile(_tender_docx(), doc_id="tender")
    first = format_profile_to_ast(profile, task=_Task(), ctx=_ctx())
    second = format_profile_to_ast(profile, task=_Task(), ctx=_ctx())
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(second, sort_keys=True, ensure_ascii=False)
    assert format_profile_to_ast(profile | {"format_section": {"detected": False}}, task=_Task(), ctx=_ctx()) is None
