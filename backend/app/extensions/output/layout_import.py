"""Deterministic .docx → layout-template extraction.

Reads page settings, body/heading styles, table style, header/footer, and
best-effort cover structure from a sample .docx and returns a
LayoutTemplate-shaped dict (snake_case) consumed by the output/docmgr
``import-layout`` endpoints. Pure python-docx, no new dependencies.
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

_PAPER_DIMS = {
    "A4": (21.0, 29.7),
    "A3": (29.7, 42.0),
    "B5": (17.6, 25.0),
    "letter": (21.59, 27.94),
}
_DRAWML = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _to_cm(length) -> float:
    """python-docx Length (EMU) → cm, rounded to 2 decimals."""
    return round(length.cm, 2) if length is not None else 0.0


def _paper_from_dimensions(width_cm: float, height_cm: float) -> tuple[str, str]:
    """Map page width/height (cm) → (paperSize, orientation)."""
    orientation = "landscape" if width_cm > height_cm else "portrait"
    w, h = (height_cm, width_cm) if width_cm > height_cm else (width_cm, height_cm)
    best, best_err = "A4", float("inf")
    for name, (pw, ph) in _PAPER_DIMS.items():
        err = abs(w - pw) + abs(h - ph)
        if err < best_err:
            best, best_err = name, err
    return best, orientation


def _style_font(style) -> str:
    """eastAsia-first font name for a docx style (CJK samples set w:eastAsia)."""
    try:
        m = re.search(r'w:eastAsia="([^"]+)"', style.element.xml)
        if m:
            return m.group(1)
    except Exception:
        pass
    return style.font.name or "宋体"


def _style_color(style, default: str) -> str:
    try:
        rgb = style.font.color.rgb
        if rgb is not None:
            return f"#{rgb}"  # editor <input type="color"> requires #RRGGBB
    except Exception:
        pass
    return default


def _run_font(run) -> str | None:
    """eastAsia-first font name on a run, or None if not explicitly set."""
    try:
        m = re.search(r'w:eastAsia="([^"]+)"', run._element.xml)
        if m:
            return m.group(1)
        return run.font.name
    except Exception:
        return None


def _dominant_run_font(paragraphs) -> tuple[float | None, str | None]:
    """Most common (size_pt, family) across explicitly-formatted runs in `paragraphs`.

    Returns (None, None) when no run sets a size/family — caller then falls back to
    the style. Real docs usually set body/heading size on each run (e.g. 四号 = 14pt)
    while leaving the Normal/Heading style at a template default, so sampling runs is
    far more accurate than reading the style alone.
    """
    sizes: dict[float, int] = {}
    families: dict[str, int] = {}
    for p in paragraphs:
        for run in p.runs:
            try:
                sz = run.font.size
            except Exception:
                sz = None
            if sz is not None:
                sizes[sz.pt] = sizes.get(sz.pt, 0) + 1
            fam = _run_font(run)
            if fam:
                families[fam] = families.get(fam, 0) + 1
    size = max(sizes, key=sizes.get) if sizes else None
    family = max(families, key=families.get) if families else None
    return size, family


def _body_paragraphs(doc) -> list:
    """Non-heading, non-empty body paragraphs (excludes table cells)."""
    return [p for p in doc.paragraphs if p.text.strip() and not p.style.name.startswith("Heading")]


def _heading_paragraphs(doc, level: int) -> list:
    return [p for p in doc.paragraphs if p.style.name == f"Heading {level}"]


def _dominant(paragraphs, getter):
    """Most common non-None getter(paragraph) value across paragraphs, or None."""
    counts: dict = {}
    for p in paragraphs:
        try:
            v = getter(p)
        except Exception:
            v = None
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _line_spacing_value(ls, body_pt: float | None) -> float | None:
    """line_spacing (float 'multiple' e.g. 1.5, or Length 'exact/atLeast') → editor decimal multiple.

    Exact/atLeast (固定值/最小值, common in CN docs) has no clean multiple form, so we approximate
    as exact_pt ÷ body_font_pt — e.g. 固定值28pt at 14pt ≈ 2.0. Returns None when unset.
    """
    if isinstance(ls, float) and ls:
        return round(ls, 2)
    if ls is not None and body_pt:
        return round(ls.pt / body_pt, 2)
    return None


def _para_space_after_pt(p) -> int | None:
    sa = p.paragraph_format.space_after
    return int(sa.pt) if sa is not None else None


def _para_first_indent_chars(p, body_pt: float | None) -> int | None:
    fi = p.paragraph_format.first_line_indent
    if fi is None or not body_pt:
        return None
    return round(fi.pt / body_pt)  # pt indent ÷ pt body size ≈ 字 (char) indent


def _dominant_run_color(paragraphs) -> str | None:
    """Most common explicit run color (#RRGGBB) across paragraphs, or None."""
    counts: dict = {}
    for p in paragraphs:
        for run in p.runs:
            try:
                rgb = run.font.color.rgb
            except Exception:
                rgb = None
            if rgb is not None:
                key = f"#{rgb}"
                counts[key] = counts.get(key, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _dominant_run_bold(paragraphs) -> bool | None:
    """Most common explicit run bold across paragraphs, or None (no run sets it)."""
    counts: dict = {}
    for p in paragraphs:
        for run in p.runs:
            try:
                b = run.font.bold
            except Exception:
                b = None
            if b is not None:
                counts[b] = counts.get(b, 0) + 1
    return max(counts, key=counts.get) if counts else None


_HEADING_CN_RE = re.compile(r"^第[一二三四五六七八九十百零\d]+章|^[一二三四五六七八九十]+[、.．]")
_HEADING_DEC_RE = re.compile(r"^\d+[.\)）]|^\d+\.\d+")


def _heading_numbering(paragraphs) -> str:
    """Best-effort heading numbering style: 'chinese' | 'decimal' | 'none'.

    CN reports usually type the number into the heading text (第一章 / 一、 / 1. / 1.1) rather than
    using Word's list auto-numbering, so we check the text first, then fall back to a w:numPr
    (auto-numbered) check. ponytail: resolving numId→abstractNum→lvlText to distinguish decimal
    from 天干/字母 auto-formats would need numbering.xml parsing; auto-numbered ⇒ 'decimal'.
    """
    for p in paragraphs:
        text = p.text.strip()
        if _HEADING_CN_RE.search(text):
            return "chinese"
        if _HEADING_DEC_RE.search(text):
            return "decimal"
        try:
            pPr = p._p.find(qn("w:pPr"))
            if pPr is not None and pPr.find(qn("w:numPr")) is not None:
                return "decimal"
        except Exception:
            pass
    return "none"


def _tbl_border_color(table) -> str | None:
    """First non-auto border color from w:tblBorders (representative of all edges)."""
    try:
        borders = table._tbl.tblPr.find(qn("w:tblBorders"))
        if borders is None:
            return None
        for edge in ("top", "left", "bottom", "right"):
            e = borders.find(qn(f"w:{edge}"))
            if e is not None:
                color = e.get(qn("w:color"))
                if color and color.lower() != "auto":
                    return f"#{color}"
    except Exception:
        pass
    return None


def _extract_body_styles(doc) -> dict:
    style = doc.styles["Normal"]
    pf = style.paragraph_format
    body = _body_paragraphs(doc)
    run_size, run_family = _dominant_run_font(body)
    style_size = style.font.size.pt if style.font.size else None
    size = run_size or style_size
    family = run_family or _style_font(style)

    # Real docs set spacing/indent per-paragraph, not on the Normal style — sample the
    # dominant paragraph value, then fall back to the style / a sensible default.
    line_spacing = _dominant(body, lambda p: _line_spacing_value(p.paragraph_format.line_spacing, size))
    if line_spacing is None:
        line_spacing = _line_spacing_value(pf.line_spacing, size) or 1.5
    space_after = _dominant(body, _para_space_after_pt)
    if space_after is None:
        sa = pf.space_after
        space_after = int(sa.pt) if sa else 6
    indent = _dominant(body, lambda p: _para_first_indent_chars(p, size))
    if indent is None:
        indent = 2  # ponytail: not derivable from style → default 2 字

    return {
        "fontFamily": family,
        "fontSize": int(size) if size else 12,
        "lineHeight": line_spacing,
        "paragraphSpacing": space_after,
        "firstLineIndent": indent,
    }


def _extract_heading_styles(doc) -> list[dict]:
    defaults = {1: 16, 2: 14, 3: 12, 4: 12}
    out = []
    for level in range(1, 5):
        try:
            style = doc.styles[f"Heading {level}"]
        except KeyError:
            continue
        hps = _heading_paragraphs(doc, level)
        run_size, run_family = _dominant_run_font(hps)
        style_size = style.font.size.pt if style.font.size else None
        size = run_size or style_size
        run_bold = _dominant_run_bold(hps)
        bold = run_bold if run_bold is not None else bool(style.font.bold)
        out.append(
            {
                "level": level,
                "fontFamily": run_family or _style_font(style),
                "fontSize": int(size) if size else defaults[level],
                "fontWeight": 700 if bold else 400,
                "color": _dominant_run_color(hps) or _style_color(style, "#333333"),
                "numbering": _heading_numbering(hps),
            }
        )
    return out


def _shd_fill(shd) -> str | None:
    """w:shd element → fill hex string, or None when absent / 'auto' (no fill)."""
    if shd is None:
        return None
    fill = shd.get(qn("w:fill"))
    return fill if fill and fill.lower() != "auto" else None


def _cell_shading_fill(tc) -> str | None:
    tc_pr = tc.tcPr
    return _shd_fill(tc_pr.find(qn("w:shd")) if tc_pr is not None else None)


def _style_conditional_shading(table, cond_type: str) -> str | None:
    """Fill from a table style's conditional format (firstRow / band1Row / ...), best-effort.

    Covers the common Word case where picking a built-in table style bands the header
    or zebra-stripes rows without writing per-cell shading. ponytail: ignores w:tblLook
    (assumes the conditional applies); honor tblLook if a sample whose band is disabled
    mismatches.
    """
    try:
        style = table.style
        if style is None:
            return None
        for tsp in style.element.findall(qn("w:tblStylePr")):
            if tsp.get(qn("w:type")) != cond_type:
                continue
            tc_pr = tsp.find(qn("w:tcPr"))
            fill = _shd_fill(tc_pr.find(qn("w:shd")) if tc_pr is not None else None)
            if fill:
                return fill
    except Exception:
        pass
    return None


def _header_text_color(table) -> str | None:
    """First header cell's first explicitly-colored run, best-effort."""
    try:
        for para in table.rows[0].cells[0].paragraphs:
            for run in para.runs:
                try:
                    rgb = run.font.color.rgb
                except Exception:
                    rgb = None
                if rgb is not None:
                    return f"#{rgb}"
    except Exception:
        pass
    return None


def _extract_table_styles(doc) -> dict | None:
    if not doc.tables:
        return None
    table = doc.tables[0]
    header_bg = None
    try:
        header_bg = _cell_shading_fill(table.rows[0].cells[0]._tc)
    except Exception:
        header_bg = None
    if not header_bg:
        header_bg = _style_conditional_shading(table, "firstRow")
    header_color = _header_text_color(table)
    # Zebra striping only when the table style defines row banding; plain tables → off.
    stripe = bool(
        _style_conditional_shading(table, "band1Row") or _style_conditional_shading(table, "band2Row")
    )
    return {
        # No fill detected → white (no-fill), never an invented blue. Real fill comes
        # from direct cell shading or the table style's firstRow band above.
        "headerBg": f"#{header_bg}" if header_bg else "#FFFFFF",
        "headerColor": header_color or "#333333",
        "borderColor": _tbl_border_color(table) or "#CCCCCC",
        "stripeRows": stripe,
    }


def _extract_header_footer(doc) -> dict:
    section = doc.sections[0]

    def _text(part) -> str:
        if part is None:
            return ""
        return " ".join(p.text.strip() for p in part.paragraphs if p.text.strip())

    def _has_page_field(part) -> bool:
        if part is None:
            return False
        try:
            return "PAGE" in part._element.xml
        except Exception:
            return False

    def _has_image(part) -> bool:
        if part is None:
            return False
        try:
            return bool(part._element.findall(f".//{{{_DRAWML}}}blip"))
        except Exception:
            return False

    return {
        "headerText": _text(section.header),
        "footerText": _text(section.footer),
        "showPageNumber": _has_page_field(section.footer) or _has_page_field(section.header),
        "showLogo": _has_image(section.header),
    }


def _para_has_image(para) -> bool:
    return bool(para._p.findall(f".//{{{_DRAWML}}}blip"))


def _para_align(para) -> str:
    if para.alignment in (None, WD_ALIGN_PARAGRAPH.LEFT):
        return "left"
    if para.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
        return "right"
    return "center"


def _detect_cover(doc) -> dict | None:
    """Best-effort cover detection from the first page.

    Returns None (fallback C) when no cover-like structure is found — the
    caller then leaves the cover section untouched rather than guessing.
    """
    section = doc.sections[0]
    try:
        different_first = bool(section.different_first_page_header_footer)
    except Exception:
        different_first = False

    pre: list = []
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            break
        if p.text.strip():
            pre.append(p)

    if not different_first and len(pre) < 3:
        return None

    cover: dict = {
        "showLogo": False,
        "logoPosition": "center",
        "showTitle": False,
        "showClient": False,
        "showDate": False,
        "showProjectNumber": False,
    }
    if not pre:
        return cover

    first = pre[0]
    cover["showLogo"] = _para_has_image(first)
    cover["logoPosition"] = _para_align(first)

    title_para = max(pre, key=lambda p: p.runs[0].font.size.pt if p.runs and p.runs[0].font.size else 0)
    if title_para.runs and title_para.runs[0].font.size and title_para.runs[0].font.size.pt >= 14:
        cover["showTitle"] = True

    for p in pre:
        text = p.text
        if re.search(r"(建设单位|单位|公司|业主|client)", text, re.I):
            cover["showClient"] = True
        if re.search(r"(\d{4}[-/年]\d{1,2}[-/月]\d{0,2}日?|日期)", text):
            cover["showDate"] = True
        if re.search(r"(项目编号|编号|项目号|工程号|number)", text, re.I):
            cover["showProjectNumber"] = True
    return cover


def extract_layout_from_docx(data: bytes) -> dict:
    """Parse a .docx byte stream → LayoutTemplate data subset (snake_case).

    Raises ValueError for non-.docx / unparseable input.
    """
    try:
        doc = Document(BytesIO(data))
    except Exception as exc:
        raise ValueError("无法解析该文件，请确保为 .docx 格式") from exc

    section = doc.sections[0]
    paper, orientation = _paper_from_dimensions(_to_cm(section.page_width), _to_cm(section.page_height))
    cover = _detect_cover(doc)

    return {
        "page_settings": {
            "paperSize": paper,
            "orientation": orientation,
            "marginTop": _to_cm(section.top_margin),
            "marginBottom": _to_cm(section.bottom_margin),
            "marginLeft": _to_cm(section.left_margin),
            "marginRight": _to_cm(section.right_margin),
        },
        "body_styles": _extract_body_styles(doc),
        "heading_styles": _extract_heading_styles(doc),
        "table_styles": _extract_table_styles(doc),
        "figure_styles": None,
        "header_footer": _extract_header_footer(doc),
        "cover_template": cover,
        "cover_detected": cover is not None,
    }


def validate_docx_upload(filename: str | None, data: bytes) -> dict:
    """Validate an .docx upload (extension + ≤10MB) and return extracted layout.

    Raises ValueError with a user-facing Chinese message on invalid input; the
    routers map it to HTTP 400. Kept in this pure module so both the output and
    docmgr import-layout endpoints share one implementation.
    """
    if not filename or not filename.lower().endswith(".docx"):
        raise ValueError("仅支持 .docx 文件")
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("文件不能超过 10MB")
    return extract_layout_from_docx(data)
