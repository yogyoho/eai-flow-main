"""Markdown → DOCX generator using python-docx with layout template styling."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Pt, RGBColor

# ---------------------------------------------------------------------------
# Minimal markdown parser — produces a list of typed blocks
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
LIST_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
LIST_OL_RE = re.compile(r"^(\s*)\d+\.\s+(.+)$")
HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def _split_frontmatter(md: str) -> tuple[dict, str]:
    """Split leading ``---\\nkey: value\\n---\\n`` front-matter from markdown.

    Only flat ``key: value`` lines are supported (no nested YAML, no new dep).
    Returns ``(meta_dict, body_markdown)``. If there is no front-matter, or any
    non-blank/non-comment line lacks a colon (malformed), returns ``({}, md)``
    — i.e. treat the whole input as body so generation never crashes.
    """
    m = FRONTMATTER_RE.match(md)
    if not m:
        return {}, md
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            return {}, md  # malformed → degrade to whole-body
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, md[m.end():]


@dataclass
class Block:
    kind: str  # heading | paragraph | ul_item | ol_item | hr | code_block | table
    level: int = 0
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)


def _compute_heading_numbers(blocks: list[Block], heading_styles: list[dict]) -> dict[int, str]:
    """Compute decimal multilevel numbers for heading blocks.

    Returns ``{block_index: number_string}`` (e.g. ``{0: "1", 1: "1.1", 3: "1.2.1"}``)
    for heading blocks whose level has ``numbering == "decimal"``. Headings on
    levels with ``numbering != "decimal"`` (or unspecified) are omitted.

    Note: meaningful only when every relevant level is "decimal". Mixing "none"
    in the middle produces counter-intuitive numbers for deeper levels —
    acceptable since templates configure all-or-none per the spec.
    """
    numbering_by_level: dict[int, str] = {
        hs.get("level", 0): hs.get("numbering", "none") for hs in heading_styles
    }
    counters = [0, 0, 0, 0]  # levels 1..4
    result: dict[int, str] = {}
    for i, b in enumerate(blocks):
        if b.kind != "heading":
            continue
        level = max(1, min(b.level, 4))
        if numbering_by_level.get(level, "none") != "decimal":
            continue
        counters[level - 1] += 1
        for deeper in range(level, 4):
            counters[deeper] = 0
        result[i] = ".".join(str(counters[k]) for k in range(level))
    return result


def _render_cover(doc, cover_template: dict | None, cover_fields: dict) -> None:
    """Render the cover page at the start of the document body.

    ``cover_template`` toggles which fields appear (showLogo/showTitle/showClient/
    showDate/showProjectNumber). ``cover_fields`` carries resolved values
    (title/client/date/project_number); a line is rendered only if its toggle is
    on AND its value is present. No-op content-wise when ``cover_template`` is falsy.
    """
    ct = cover_template or {}

    if ct.get("showLogo"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[编制单位 LOGO]")
        _set_run_font(run, "宋体")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    for _ in range(3):  # vertical spacing before title
        doc.add_paragraph()

    if ct.get("showTitle") and cover_fields.get("title"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(cover_fields["title"]))
        _set_run_font(run, "黑体")
        run.font.size = Pt(22)
        run.bold = True

    for _ in range(4):  # spacing before info lines
        doc.add_paragraph()

    def _info_line(label: str, value) -> None:
        if not value:
            return
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"{label}:{value}")
        _set_run_font(run, "宋体")
        run.font.size = Pt(14)

    if ct.get("showClient"):
        _info_line("建设单位", cover_fields.get("client"))
    if ct.get("showProjectNumber"):
        _info_line("项目编号", cover_fields.get("project_number"))
    if ct.get("showDate"):
        _info_line("日期", cover_fields.get("date"))


def parse_markdown(md: str) -> list[Block]:
    """Parse markdown text into a flat list of blocks."""
    blocks: list[Block] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Blank line
        if not line.strip():
            i += 1
            continue

        # Horizontal rule
        if HR_RE.match(line.strip()):
            blocks.append(Block(kind="hr"))
            i += 1
            continue

        # Heading
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            blocks.append(Block(kind="heading", level=level, text=m.group(2).strip()))
            i += 1
            continue

        # Fenced code block
        if line.strip().startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append(Block(kind="code_block", text="\n".join(code_lines)))
            continue

        # Table
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|?[\s\-:|]+\|?$", lines[i + 1].strip()):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator
            table_rows = [header]
            while i < len(lines) and "|" in lines[i]:
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                table_rows.append(row)
                i += 1
            blocks.append(Block(kind="table", rows=table_rows))
            continue

        # Unordered list
        m = LIST_UL_RE.match(line)
        if m:
            indent = len(m.group(1))
            blocks.append(Block(kind="ul_item", level=indent, text=m.group(2).strip()))
            i += 1
            continue

        # Ordered list
        m = LIST_OL_RE.match(line)
        if m:
            indent = len(m.group(1))
            blocks.append(Block(kind="ol_item", level=indent, text=m.group(2).strip()))
            i += 1
            continue

        # Paragraph — accumulate until blank line
        para_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            para_lines.append(lines[i])
            i += 1
        blocks.append(Block(kind="paragraph", text=" ".join(para_lines)))

    return blocks


# ---------------------------------------------------------------------------
# Inline formatting helper — handles **bold**, *italic*, `code`
# ---------------------------------------------------------------------------

def _add_inline_text(paragraph, text: str) -> None:
    """Add text with inline **bold**, *italic*, `code` formatting."""
    # Tokenize: split on bold/italic/code patterns while keeping delimiters
    parts = re.split(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*") and not part.startswith("**"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            paragraph.add_run(part)


# ---------------------------------------------------------------------------
# DOCX generation from parsed blocks + layout template
# ---------------------------------------------------------------------------

# Map common Chinese font names to English equivalents python-docx understands
FONT_ALIASES = {
    "宋体": "SimSun",
    "黑体": "SimHei",
    "仿宋": "FangSong",
    "楷体": "KaiTi",
    "微软雅黑": "Microsoft YaHei",
    "等线": "DengXian",
}


def _resolve_font(name: str) -> str:
    return FONT_ALIASES.get(name, name)


def generate_docx(
    markdown_content: str,
    template_data: dict,
    output_path: Path,
    watermark: str | None = None,
) -> str:
    """Generate a DOCX file from markdown content using layout template styling.

    Returns the output file path.
    """
    blocks = parse_markdown(markdown_content)
    doc = Document()

    # --- Page setup ---
    ps = template_data.get("page_settings", {})
    section = doc.sections[0]
    section.page_width = Cm(21.0) if ps.get("paperSize", "A4") == "A4" else Cm(29.7)
    section.page_height = Cm(29.7) if ps.get("paperSize", "A4") == "A4" else Cm(42.0)
    if ps.get("orientation") == "landscape":
        section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(ps.get("marginTop", 2.54))
    section.bottom_margin = Cm(ps.get("marginBottom", 2.54))
    section.left_margin = Cm(ps.get("marginLeft", 3.17))
    section.right_margin = Cm(ps.get("marginRight", 3.17))

    # --- Body style defaults ---
    bs = template_data.get("body_styles", {})
    body_font = _resolve_font(bs.get("fontFamily", "宋体"))
    body_size = Pt(bs.get("fontSize", 12))
    body_line_spacing = bs.get("lineHeight", 1.5)

    # --- Heading styles map ---
    heading_styles: dict[int, dict] = {}
    for hs in template_data.get("heading_styles", []):
        heading_styles[hs.get("level", 0)] = hs

    # --- Helper: style a paragraph ---
    def style_paragraph(para, font_name: str = body_font, font_size=body_size, bold: bool = False, color: str | None = None, alignment=None, first_indent: float | None = None, space_after: int | None = None):
        pf = para.paragraph_format
        pf.line_spacing = body_line_spacing
        if space_after is not None:
            pf.space_after = Pt(space_after)
        else:
            pf.space_after = Pt(bs.get("paragraphSpacing", 6))
        if first_indent is not None:
            pf.first_line_indent = Cm(first_indent)
        if alignment is not None:
            pf.alignment = alignment

    # --- Render blocks ---
    ol_counters: dict[int, int] = {}

    for block in blocks:
        if block.kind == "heading":
            level = min(block.level, 4)
            hs = heading_styles.get(level, {})
            heading = doc.add_heading(level=level)
            _add_inline_text(heading, block.text)

            # Apply heading font
            for run in heading.runs:
                _set_run_font(run, _resolve_font(hs.get("fontFamily", body_font)))
                run.font.size = Pt(hs.get("fontSize", 16))
                if hs.get("fontWeight", 700) >= 700:
                    run.bold = True
                c = hs.get("color")
                if c:
                    run.font.color.rgb = RGBColor.from_string(c.replace("#", ""))
            style_paragraph(heading, space_after=6)

        elif block.kind == "paragraph":
            para = doc.add_paragraph()
            indent = bs.get("firstLineIndent", 2)
            style_paragraph(para, first_indent=indent * body_size.pt / 28.35 * 0.5 if indent else None)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ul_item":
            para = doc.add_paragraph()
            indent_cm = block.level * 0.6
            para.paragraph_format.left_indent = Cm(indent_cm)
            para.paragraph_format.first_line_indent = Cm(-0.3)
            para.add_run("• ")
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ol_item":
            indent_level = block.level
            ol_counters[indent_level] = ol_counters.get(indent_level, 0) + 1
            counter = ol_counters[indent_level]
            para = doc.add_paragraph()
            indent_cm = indent_level * 0.6
            para.paragraph_format.left_indent = Cm(indent_cm)
            para.add_run(f"{counter}. ")
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "hr":
            para = doc.add_paragraph()
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(6)
            run = para.add_run("─" * 60)
            run.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
            run.font.size = Pt(8)

        elif block.kind == "code_block":
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Cm(1)
            para.paragraph_format.space_before = Pt(4)
            para.paragraph_format.space_after = Pt(4)
            run = para.add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        elif block.kind == "table":
            if block.rows:
                tstyles = template_data.get("table_styles")
                ncols = max(len(r) for r in block.rows)
                table = doc.add_table(rows=len(block.rows), cols=ncols)
                table.style = "Table Grid"

                for ri, row in enumerate(block.rows):
                    for ci, cell_text in enumerate(row):
                        if ci < ncols:
                            cell = table.rows[ri].cells[ci]
                            cell.text = ""
                            para = cell.paragraphs[0]
                            _add_inline_text(para, cell_text.strip())
                            for run in para.runs:
                                _set_run_font(run, body_font)
                                run.font.size = Pt(body_size.pt - 1)
                                if ri == 0 and tstyles:
                                    run.bold = True
                                    c = tstyles.get("headerColor", "#FFFFFF")
                                    run.font.color.rgb = RGBColor.from_string(c.replace("#", ""))

                # Header row shading
                if tstyles and block.rows:
                    from docx.oxml.ns import qn

                    bg = tstyles.get("headerBg", "#2B579A").replace("#", "")
                    for ci in range(ncols):
                        cell = table.rows[0].cells[ci]
                        shading = cell._element.get_or_add_tcPr()
                        shading_elem = shading.makeelement(qn("w:shd"), {
                            qn("w:fill"): bg,
                            qn("w:val"): "clear",
                        })
                        shading.append(shading_elem)

    # --- Header / Footer ---
    hf = template_data.get("header_footer")
    if hf:
        if hf.get("headerText"):
            section.header.paragraphs[0].text = hf["headerText"]
            for run in section.header.paragraphs[0].runs:
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        if hf.get("footerText") or hf.get("showPageNumber"):
            footer_para = section.footer.paragraphs[0]
            if hf.get("footerText"):
                footer_para.text = hf["footerText"]
            if hf.get("showPageNumber"):
                from docx.oxml.ns import qn

                run = footer_para.add_run()
                fld_char_begin = run._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "begin"})
                run._element.append(fld_char_begin)
                run2 = footer_para.add_run()
                instr = run2._element.makeelement(qn("w:instrText"), {})
                instr.text = " PAGE "
                run2._element.append(instr)
                run3 = footer_para.add_run()
                fld_char_end = run3._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "end"})
                run3._element.append(fld_char_end)
            for run in footer_para.runs:
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # --- Watermark placeholder (as a header note) ---
    if watermark:
        labels = {"draft": "初稿", "review": "送审稿", "final": "正式稿"}
        label = labels.get(watermark, watermark)
        existing = section.header.paragraphs[0].text if section.header.paragraphs else ""
        section.header.paragraphs[0].text = f"【{label}】{chr(10)}{existing}".strip()

    # Save
    doc.save(str(output_path))
    return str(output_path)


# ---------------------------------------------------------------------------
# Simple DOCX generation (no template) — used by document export
# ---------------------------------------------------------------------------

DEFAULT_BODY_FONT = "SimSun"
DEFAULT_BODY_SIZE = 12
HEADING_SIZES = {1: 22, 2: 16, 3: 14, 4: 12}


def _set_run_font(run, font_name: str) -> None:
    """Set both ASCII and eastAsia font on a run.

    python-docx's ``run.font.name`` only sets ``w:ascii`` / ``w:hAnsi``.
    Chinese text in Word uses ``w:eastAsia`` instead, so we must set both
    to guarantee correct font rendering on the user's machine.
    """
    from docx.oxml.ns import qn

    run.font.name = font_name
    rPr = run._element.find(qn("w:rPr"))
    if rPr is not None:
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is not None:
            rFonts.set(qn("w:eastAsia"), font_name)


def generate_docx_simple(
    markdown_content: str,
    buf,
    template_data: dict | None = None,
    watermark: str | None = None,
) -> None:
    """Generate a DOCX from markdown into a writable buffer.

    Args:
        markdown_content: Source markdown text.
        buf: Writable buffer (BytesIO) for the output.
        template_data: Optional layout template dict with keys like
            page_settings, body_styles, heading_styles, table_styles,
            header_footer. When None, sensible defaults are used.
        watermark: Optional watermark type — "draft", "review", or "final".
    """
    td = template_data or {}
    blocks = parse_markdown(markdown_content)
    doc = Document()

    # --- Page setup ---
    ps = td.get("page_settings", {})
    section = doc.sections[0]
    section.page_width = Cm(21.0) if ps.get("paperSize", "A4") == "A4" else Cm(29.7)
    section.page_height = Cm(29.7) if ps.get("paperSize", "A4") == "A4" else Cm(42.0)
    if ps.get("orientation") == "landscape":
        section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(ps.get("marginTop", 2.54))
    section.bottom_margin = Cm(ps.get("marginBottom", 2.54))
    section.left_margin = Cm(ps.get("marginLeft", 3.17))
    section.right_margin = Cm(ps.get("marginRight", 3.17))

    # --- Body style ---
    bs = td.get("body_styles", {})
    body_font = _resolve_font(bs.get("fontFamily", DEFAULT_BODY_FONT))
    body_size = Pt(bs.get("fontSize", DEFAULT_BODY_SIZE))
    body_line_spacing = bs.get("lineHeight", 1.5)
    body_paragraph_spacing = bs.get("paragraphSpacing", 6)
    body_first_indent = bs.get("firstLineIndent", 2)

    # --- Heading styles ---
    hs_map: dict[int, dict] = {}
    for hs in td.get("heading_styles", []):
        hs_map[hs.get("level", 0)] = hs

    ol_counters: dict[int, int] = {}

    for block in blocks:
        if block.kind == "heading":
            level = min(block.level, 4)
            hs = hs_map.get(level, {})
            heading = doc.add_heading(level=level)
            _add_inline_text(heading, block.text)
            for run in heading.runs:
                _set_run_font(run, _resolve_font(hs.get("fontFamily", body_font)))
                run.font.size = Pt(hs.get("fontSize", HEADING_SIZES.get(level, 12)))
                if hs.get("fontWeight", 700) >= 700:
                    run.bold = True
                c = hs.get("color")
                if c:
                    run.font.color.rgb = RGBColor.from_string(str(c).replace("#", ""))

        elif block.kind == "paragraph":
            para = doc.add_paragraph()
            pf = para.paragraph_format
            pf.line_spacing = body_line_spacing
            pf.space_after = Pt(body_paragraph_spacing)
            if body_first_indent:
                pf.first_line_indent = Cm(body_first_indent * body_size.pt / 28.35 * 0.5)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ul_item":
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Cm(block.level * 0.6)
            para.paragraph_format.first_line_indent = Cm(-0.3)
            _set_run_font(para.add_run("• "), body_font)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "ol_item":
            indent_level = block.level
            ol_counters[indent_level] = ol_counters.get(indent_level, 0) + 1
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Cm(indent_level * 0.6)
            _set_run_font(para.add_run(f"{ol_counters[indent_level]}. "), body_font)
            _add_inline_text(para, block.text)
            for run in para.runs:
                _set_run_font(run, body_font)
                run.font.size = body_size

        elif block.kind == "hr":
            # Skip horizontal rules — not needed in Word export
            pass

        elif block.kind == "code_block":
            para = doc.add_paragraph()
            para.paragraph_format.left_indent = Cm(1)
            run = para.add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        elif block.kind == "table":
            if block.rows:
                tstyles = td.get("table_styles")
                ncols = max(len(r) for r in block.rows)
                table = doc.add_table(rows=len(block.rows), cols=ncols)
                table.style = "Table Grid"
                for ri, row in enumerate(block.rows):
                    for ci, cell_text in enumerate(row):
                        if ci < ncols:
                            cell = table.rows[ri].cells[ci]
                            cell.text = ""
                            para = cell.paragraphs[0]
                            _add_inline_text(para, cell_text.strip())
                            for run in para.runs:
                                _set_run_font(run, body_font)
                                run.font.size = Pt(body_size.pt - 1)
                                if ri == 0 and tstyles:
                                    run.bold = True
                                    c = tstyles.get("headerColor", "#FFFFFF")
                                    run.font.color.rgb = RGBColor.from_string(str(c).replace("#", ""))

                # Header row shading
                if tstyles and block.rows:
                    from docx.oxml.ns import qn

                    bg = str(tstyles.get("headerBg", "#2B579A")).replace("#", "")
                    for ci in range(ncols):
                        cell = table.rows[0].cells[ci]
                        shading = cell._element.get_or_add_tcPr()
                        shading_elem = shading.makeelement(qn("w:shd"), {
                            qn("w:fill"): bg,
                            qn("w:val"): "clear",
                        })
                        shading.append(shading_elem)

    # --- Header / Footer ---
    hf = td.get("header_footer")
    if hf:
        if hf.get("headerText"):
            section.header.paragraphs[0].text = hf["headerText"]
            for run in section.header.paragraphs[0].runs:
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        if hf.get("footerText") or hf.get("showPageNumber"):
            footer_para = section.footer.paragraphs[0]
            if hf.get("footerText"):
                footer_para.text = hf["footerText"]
            if hf.get("showPageNumber"):
                from docx.oxml.ns import qn

                run = footer_para.add_run()
                fld_char_begin = run._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "begin"})
                run._element.append(fld_char_begin)
                run2 = footer_para.add_run()
                instr = run2._element.makeelement(qn("w:instrText"), {})
                instr.text = " PAGE "
                run2._element.append(instr)
                run3 = footer_para.add_run()
                fld_char_end = run3._element.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "end"})
                run3._element.append(fld_char_end)
            for run in footer_para.runs:
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # --- Watermark ---
    if watermark:
        labels = {"draft": "初稿", "review": "送审稿", "final": "正式稿"}
        label = labels.get(watermark, watermark)
        existing = section.header.paragraphs[0].text if section.header.paragraphs else ""
        section.header.paragraphs[0].text = f"【{label}】{chr(10)}{existing}".strip()
        for run in section.header.paragraphs[0].runs:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.save(buf)
