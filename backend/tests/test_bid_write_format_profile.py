"""招标商务卷 FormatProfile 提取:章节/占位符/表格/签章位与差距清单(P0)。"""

from __future__ import annotations

import io
import json

from docx import Document

from app.extensions.bid_write.format_profile import (
    extract_format_profile,
    extract_format_profile_from_path,
    main,
)

_FIXED_SENTENCE = "我方承诺本投标文件真实有效，并承担相应法律责任。"
_LIST_ITEM = "1.开户许可证或基本存款账户信息（加盖公章）"
_SIGNATURE_LINE = "投标人（盖章）："
_IMAGE_LINE = "（此处贴营业执照扫描件）"


def _docx_bytes(build) -> bytes:
    document = Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _tender_docx() -> bytes:
    def build(document):
        document.add_paragraph("第六章 投标文件格式", style="Heading 1")
        document.add_paragraph("投标文件目录")
        document.add_paragraph("一  投标函")
        document.add_paragraph("二  投标保证金")

        document.add_paragraph("一、投标函", style="Heading 1")
        document.add_paragraph("致：________（招标人名称）")
        document.add_paragraph(_FIXED_SENTENCE)
        document.add_paragraph("项目名称：________")
        document.add_paragraph(_LIST_ITEM)

        table = document.add_table(rows=2, cols=3)
        table.cell(0, 0).text = "项目名称"
        table.cell(0, 1).text = ""
        table.cell(0, 2).text = "金额"
        table.cell(0, 0).merge(table.cell(0, 1))
        table.cell(1, 0).text = "报价"
        table.cell(1, 1).text = "________"
        table.cell(1, 2).text = "100"

        document.add_paragraph("二、投标保证金", style="Heading 1")
        document.add_paragraph("2.1 投标保证金凭证")
        document.add_paragraph(_SIGNATURE_LINE)
        document.add_paragraph(_IMAGE_LINE)

        document.add_paragraph("第七章 合同条款", style="Heading 1")

    return _docx_bytes(build)


def test_extracts_chapters_tables_placeholders_and_gap_report():
    data = _tender_docx()
    profile = extract_format_profile(data, doc_id="tender-1", source_name="tender.docx")

    assert profile["supported"] is True
    assert profile["source"]["doc_id"] == "tender-1"
    assert profile["source"]["kind"] == "docx" and profile["source"]["bytes"] == len(data)

    section = profile["format_section"]
    assert section["detected"] is True
    assert section["chapter_count"] == 2
    assert section["toc_entry_count"] == 2
    assert section["toc_matched_count"] == 2
    assert section["chapter_titles"] == ["一  投标函", "二  投标保证金"]

    headings = [chapter for chapter in profile["chapters"] if chapter["kind"] == "heading"]
    assert [chapter["title"] for chapter in headings] == ["一、投标函", "二、投标保证金", "2.1 投标保证金凭证"]
    assert [chapter["level"] for chapter in headings] == [1, 1, 2]
    assert _LIST_ITEM not in [chapter["title"] for chapter in headings]

    assert any(placeholder["type"] == "underscore" for placeholder in profile["placeholders"])

    assert len(profile["tables"]) == 1
    table = profile["tables"][0]
    assert table["column_count"] == 3
    assert table["headers"][0] == "项目名称"
    assert table["has_merged_cells"] is True
    assert table["merged_cell_count"] >= 1

    fixed_texts = [item["text"] for item in profile["fixed_texts"]]
    assert _FIXED_SENTENCE in fixed_texts
    assert "一  投标函" not in fixed_texts
    assert _SIGNATURE_LINE not in fixed_texts
    assert [item["text"] for item in profile["signatures"]] == [_SIGNATURE_LINE]
    assert [item["text"] for item in profile["image_slots"]] == [_IMAGE_LINE]

    gap = profile["gap_report"]
    assert gap["summary"]["chapter_count"] == 2
    assert gap["summary"]["toc_entry_count"] == 2
    assert gap["summary"]["table_count"] == 1
    assert gap["summary"]["merged_table_count"] == 1
    assert gap["summary"]["blocking_gap_count"] == len(gap["blocking_gaps"])
    assert "approval_freeze" not in gap["blocking_gaps"]
    assert "table_structure" not in gap["blocking_gaps"]
    assert "export_render" in gap["blocking_gaps"]
    assert gap["blocking_reasons"]["export_render"]
    assert any(capability["status"] == "supported" for capability in gap["capabilities"])


def test_profile_hash_is_deterministic():
    data = _tender_docx()
    first = extract_format_profile(data, doc_id="tender-1")
    second = extract_format_profile(data, doc_id="tender-1")

    assert first["profile_hash"] == second["profile_hash"]
    assert len(first["profile_hash"]) == 64


def test_corrupt_bytes_return_unsupported_without_raising():
    profile = extract_format_profile(b"not-a-docx", doc_id="broken")

    assert profile["supported"] is False
    assert profile["source"]["kind"] == "unknown"
    assert profile["reason"].startswith("无法打开 DOCX")
    assert len(profile["profile_hash"]) == 64


def test_missing_format_section_still_reports_gaps():
    data = _docx_bytes(lambda document: document.add_paragraph("第一章 总则", style="Heading 1"))
    profile = extract_format_profile(data, doc_id="plain")

    assert profile["supported"] is True
    assert profile["format_section"]["detected"] is False
    assert profile["chapters"] == [] and profile["tables"] == []
    assert profile["gap_report"]["summary"]["chapter_count"] == 0
    assert profile["gap_report"]["summary"]["toc_entry_count"] == 0
    assert len(profile["gap_report"]["capabilities"]) == 9
    assert profile["gap_report"]["blocking_gaps"]


def test_cli_writes_summary_json(tmp_path):
    source = tmp_path / "tender.docx"
    source.write_bytes(_tender_docx())
    out = tmp_path / "summary.json"

    assert main(["--input", str(source), "--summary", "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["supported"] is True
    assert payload["format_section"]["chapter_count"] == 2
    assert extract_format_profile_from_path(source)["source"]["name"] == "tender.docx"
