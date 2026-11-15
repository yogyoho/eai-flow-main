"""冻结 AST + FormatProfile → DOCX(P1,EAI-CUSTOM 2026-11-15)。

替换「AST→Markdown→通用 DOCX」在有招标格式档案时的导出路径。直接使用
python-docx 写入,保留:
- 首个分节的页面尺寸/方向/页边距/页眉页脚/页码;
- section 的标题层级(Heading 样式,Word 目录可识别);
- 表格 col_span/row_span → w:gridSpan / w:vMerge(经 cell.merge);
- 固定文字、占位符值、签章/贴图位文字;
- 段落对齐/缩进/行距/段前后距,以及段落 run 摘要字体/字号/粗斜体/颜色。

边界(诚实面):FormatProfile 的 runs 是段落级摘要,不是逐 run 快照;字体细节
按首 run 近似。图片/印章图形仍不嵌入,保留文字位。
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

_ALIGN = {
    "LEFT": WD_ALIGN_PARAGRAPH.LEFT,
    "CENTER": WD_ALIGN_PARAGRAPH.CENTER,
    "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT,
    "JUSTIFY": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "DISTRIBUTE": WD_ALIGN_PARAGRAPH.DISTRIBUTE,
    "JUSTIFY_MED": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "JUSTIFY_HI": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "JUSTIFY_LOW": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "THAI_JUSTIFY": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def _attrs(node: dict) -> dict:
    value = node.get("attrs")
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _set_east_asian(run, font_name: str) -> None:
    run.font.name = font_name
    r_pr = run._element.find(qn("w:rPr"))
    if r_pr is not None:
        r_fonts = r_pr.find(qn("w:rFonts"))
        if r_fonts is not None:
            r_fonts.set(qn("w:eastAsia"), font_name)


def _placeholder_text(node: dict) -> str:
    attrs = _attrs(node)
    value = str(attrs.get("value") or "").strip()
    if value:
        return value
    label = str(attrs.get("label") or "").strip()
    if label:
        return f"（待填：{label}）"
    return str(attrs.get("raw") or "________").strip() or "________"


def _inline_text(node: dict) -> str:
    kind = str(node.get("type") or "")
    if kind == "text":
        return str(node.get("text") or "")
    if kind == "placeholder":
        return _placeholder_text(node)
    if kind == "attachment_ref":
        no = str(_attrs(node).get("attachment_no") or "").strip()
        return f"（附件 {no}）" if no else "（见附件）"
    return "".join(_inline_text(child) for child in node.get("content") or [] if isinstance(child, dict))


def _add_inline(paragraph, content: list[dict]) -> None:
    for child in content:
        if not isinstance(child, dict):
            continue
        kind = str(child.get("type") or "")
        if kind == "text":
            text = str(child.get("text") or "")
            if text:
                paragraph.add_run(text)
        elif kind == "placeholder":
            attrs = _attrs(child)
            run = paragraph.add_run(_placeholder_text(child))
            if not str(attrs.get("value") or "").strip():
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        else:
            text = _inline_text(child)
            if text:
                paragraph.add_run(text)


def _apply_run_summary(paragraph, summary: dict | None, *, fallback_font: str = "宋体", fallback_size: float = 12) -> None:
    summary = summary or {}
    fonts = [str(item) for item in summary.get("fonts") or [] if str(item or "").strip()]
    sizes = [float(item) for item in summary.get("sizes_pt") or [] if _float(item) is not None]
    colors = [str(item) for item in summary.get("colors") or [] if str(item or "").strip()]
    font_name = fonts[0] if fonts else fallback_font
    size = sizes[0] if sizes else fallback_size
    for run in paragraph.runs:
        _set_east_asian(run, font_name)
        run.font.size = Pt(size)
        run.bold = bool(summary.get("bold")) if summary else run.bold
        run.italic = bool(summary.get("italic")) if summary else run.italic
        run.underline = bool(summary.get("underline")) if summary else run.underline
        if colors:
            try:
                run.font.color.rgb = RGBColor.from_string(colors[0].replace("#", "").upper()[:6])
            except ValueError:
                pass


def _apply_paragraph_format(paragraph, fmt: dict | None) -> None:
    fmt = fmt or {}
    alignment = _ALIGN.get(str(fmt.get("alignment") or "").upper())
    if alignment is not None:
        paragraph.alignment = alignment
    first_line = _int(fmt.get("first_line_indent"))
    left = _int(fmt.get("left_indent"))
    right = _int(fmt.get("right_indent"))
    if first_line is not None:
        paragraph.paragraph_format.first_line_indent = Emu(first_line)
    if left is not None:
        paragraph.paragraph_format.left_indent = Emu(left)
    if right is not None:
        paragraph.paragraph_format.right_indent = Emu(right)
    line_spacing = fmt.get("line_spacing")
    if isinstance(line_spacing, float):
        paragraph.paragraph_format.line_spacing = line_spacing
    elif _int(line_spacing) is not None:
        paragraph.paragraph_format.line_spacing = Emu(int(line_spacing))
    space_before = _int(fmt.get("space_before"))
    space_after = _int(fmt.get("space_after"))
    if space_before is not None:
        paragraph.paragraph_format.space_before = Emu(space_before)
    if space_after is not None:
        paragraph.paragraph_format.space_after = Emu(space_after)
    if fmt.get("keep_with_next") is not None:
        paragraph.paragraph_format.keep_with_next = bool(fmt.get("keep_with_next"))
    if fmt.get("page_break_before"):
        paragraph.paragraph_format.page_break_before = True


def _block_by_index(profile: dict | None) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for block in (profile or {}).get("blocks") or []:
        if isinstance(block, dict) and block.get("index") is not None:
            try:
                out[int(block["index"])] = block
            except (TypeError, ValueError):
                continue
    return out


def _template_block(profile: dict | None, node: dict) -> dict:
    template_id = str(_attrs(node).get("template_id") or "")
    if not template_id.startswith("tender-format:"):
        return {}
    suffix = template_id.split(":", 1)[1]
    try:
        return _block_by_index(profile).get(int(suffix), {})
    except ValueError:
        return {}


def _add_paragraph(doc, node: dict, profile: dict | None) -> None:
    attrs = _attrs(node)
    if attrs.get("page_break_before"):
        doc.add_page_break()
    paragraph = doc.add_paragraph()
    _add_inline(paragraph, [child for child in node.get("content") or [] if isinstance(child, dict)])
    block = _template_block(profile, node)
    _apply_paragraph_format(paragraph, block.get("format") if block else None)
    _apply_run_summary(paragraph, block.get("runs") if block else None)
    label = str(attrs.get("label") or "").strip()
    if label and paragraph.runs:
        paragraph.runs[0].bold = True


def _add_heading(doc, title: str, level: int, profile: dict | None, block: dict | None = None) -> None:
    level = min(max(int(level or 1), 1), 4)
    paragraph = doc.add_paragraph(style=f"Heading {level}")
    paragraph.add_run(title)
    _apply_paragraph_format(paragraph, (block or {}).get("format"))
    _apply_run_summary(paragraph, (block or {}).get("runs"), fallback_size={1: 18, 2: 16, 3: 14, 4: 12}.get(level, 12))
    for run in paragraph.runs:
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.bold = True


def _add_table(doc, node: dict, profile: dict | None) -> None:
    rows = [row for row in node.get("content") or [] if isinstance(row, dict) and row.get("type") == "table_row"]
    if not rows:
        return
    table_type = str(_attrs(node).get("table_type") or "")
    source_index = _int(_attrs(node).get("source_index"))
    source_table = None
    if source_index is not None:
        for item in (profile or {}).get("tables") or []:
            if isinstance(item, dict) and _int(item.get("table_index")) == source_index:
                source_table = item
                break
    widths: list[int] = []
    for row in rows:
        total = 0
        for cell in row.get("content") or []:
            if isinstance(cell, dict):
                total += max(1, _int(_attrs(cell).get("col_span")) or 1)
        widths.append(total)
    columns = max([_int((source_table or {}).get("column_count")) or 0, *widths, 1])
    table = doc.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"

    column_widths = (source_table or {}).get("column_widths") or []
    if len(column_widths) == columns and all(_int(value) for value in column_widths):
        table.autofit = False
        for index, width in enumerate(column_widths):
            table.columns[index].width = Emu(int(width))

    occupied: list[set[int]] = [set() for _ in rows]
    for row_index, row in enumerate(rows):
        column = 0
        for cell_node in row.get("content") or []:
            if not isinstance(cell_node, dict):
                continue
            attrs = _attrs(cell_node)
            col_span = max(1, _int(attrs.get("col_span")) or 1)
            row_span = max(1, _int(attrs.get("row_span")) or 1)
            while column < columns and column in occupied[row_index]:
                column += 1
            if column >= columns:
                break
            corner_row = min(row_index + row_span - 1, len(rows) - 1)
            corner_col = min(column + col_span - 1, columns - 1)
            for span_row in range(row_index + 1, corner_row + 1):
                for span_col in range(column, corner_col + 1):
                    occupied[span_row].add(span_col)
            cell = table.cell(row_index, column)
            if corner_row > row_index or corner_col > column:
                cell = cell.merge(table.cell(corner_row, corner_col))
            paragraph = cell.paragraphs[0]
            _add_inline(paragraph, [child for child in cell_node.get("content") or [] if isinstance(child, dict)])
            if table_type in ("price",) and str(attrs.get("role") or "") in ("amount", "subtotal", "total_num", "total_cn"):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            column += col_span


def _render_blocks(doc, nodes: list[dict], profile: dict | None) -> None:
    index_map = _block_by_index(profile)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("type") or "")
        if kind == "section":
            attrs = _attrs(node)
            title = str(attrs.get("title") or "").strip()
            level = _int(attrs.get("level")) or 1
            block = {}
            section_id = str(attrs.get("section_id") or "")
            if section_id.startswith("S-fmt-"):
                try:
                    block = index_map.get(int(section_id.rsplit("-", 1)[1]), {})
                except ValueError:
                    block = {}
            if title:
                _add_heading(doc, title, level, profile, block)
            _render_blocks(doc, [child for child in node.get("content") or [] if isinstance(child, dict)], profile)
            continue
        if kind in ("para", "locked_paragraph"):
            _add_paragraph(doc, node, profile)
            continue
        if kind == "table":
            _add_table(doc, node, profile)
            continue
        if kind == "todo_block":
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(f"【待补·{_attrs(node).get('level') or 'D0'}】 {_attrs(node).get('missing') or '待补内容'}")
            run.bold = True
            run.font.color.rgb = RGBColor(0xB4, 0x5A, 0x00)
            continue
        if kind == "deviation_note":
            paragraph = doc.add_paragraph()
            paragraph.add_run("负偏离展开").bold = True
            _render_blocks(doc, [child for child in node.get("content") or [] if isinstance(child, dict)], profile)
            continue
        if kind == "toc_entry":
            attrs = _attrs(node)
            title = str(attrs.get("title") or "").strip()
            page = str(attrs.get("page_placeholder") or "—").strip()
            if title:
                doc.add_paragraph(f"{title} …… {page}")
            continue
        if kind in ("text", "attachment_ref", "placeholder"):
            paragraph = doc.add_paragraph()
            _add_inline(paragraph, [node])


def _apply_page_setup(doc, profile: dict | None) -> None:
    section = doc.sections[0]
    setup: dict = {}
    sections = (profile or {}).get("document", {}).get("page_setup") or []
    if sections and isinstance(sections[0], dict):
        setup = sections[0]
    width = _int(setup.get("page_width"))
    height = _int(setup.get("page_height"))
    if width and height:
        section.page_width = Emu(width)
        section.page_height = Emu(height)
        if str(setup.get("orientation") or "").upper() == "LANDSCAPE" or width > height:
            section.orientation = WD_ORIENT.LANDSCAPE
        else:
            section.orientation = WD_ORIENT.PORTRAIT
    else:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.17)
        section.right_margin = Cm(3.17)
    for key, attr in (
        ("top_margin", "top_margin"),
        ("bottom_margin", "bottom_margin"),
        ("left_margin", "left_margin"),
        ("right_margin", "right_margin"),
        ("header_distance", "header_distance"),
        ("footer_distance", "footer_distance"),
    ):
        value = _int(setup.get(key))
        if value is not None:
            setattr(section, attr, Emu(value))


def _add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = run._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "begin"})
    run._element.append(begin)
    run2 = paragraph.add_run()
    instr = run2._element.makeelement(qn("w:instrText"), {})
    instr.text = " PAGE "
    run2._element.append(instr)
    run3 = paragraph.add_run()
    end = run3._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "end"})
    run3._element.append(end)


def _apply_chrome(doc, profile: dict | None, watermark: str | None) -> None:
    section = doc.sections[0]
    setup = ((profile or {}).get("document", {}).get("page_setup") or [{}])[0]
    header_texts = [str(item).strip() for item in setup.get("header_texts") or [] if str(item).strip()]
    footer_texts = [str(item).strip() for item in setup.get("footer_texts") or [] if str(item).strip()]
    if watermark:
        labels = {"draft": "初稿", "review": "送审稿", "final": "正式稿"}
        header_texts.insert(0, f"【{labels.get(watermark, watermark)}】")
    if header_texts:
        section.header.paragraphs[0].text = "  ".join(header_texts)
    footer = section.footer.paragraphs[0]
    if footer_texts:
        footer.text = "  ".join(footer_texts)
    _add_page_field(footer)
    for paragraph in (section.header.paragraphs[0], footer):
        for run in paragraph.runs:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)


def _set_default_styles(doc) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(12)
    r_pr = normal.element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = r_pr.makeelement(qn("w:rFonts"), {})
        r_pr.append(r_fonts)
    r_fonts.set(qn("w:eastAsia"), "宋体")


def _set_core_properties(doc) -> None:
    props = doc.core_properties
    fixed = datetime(2026, 1, 1, 0, 0, 0)
    props.author = "EAI"
    props.last_modified_by = "EAI"
    props.created = fixed
    props.modified = fixed
    props.title = "投标商务卷"
    props.revision = 1


def render_ast_to_docx(ast: dict, *, profile: dict | None = None, watermark: str | None = None) -> bytes:
    if not isinstance(ast, dict) or ast.get("type") != "doc":
        raise ValueError('ast 根节点 type 必须为 "doc"')
    doc = Document()
    _set_core_properties(doc)
    _set_default_styles(doc)
    _apply_page_setup(doc, profile)
    _render_blocks(doc, [node for node in ast.get("content") or [] if isinstance(node, dict)], profile)
    _apply_chrome(doc, profile, watermark)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
