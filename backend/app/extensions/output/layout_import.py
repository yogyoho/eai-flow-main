"""Deterministic .docx → layout-template extraction.

Reads page settings, body/heading styles, table style, header/footer, and
best-effort cover structure from a sample .docx and returns a
LayoutTemplate-shaped dict (snake_case) consumed by the output/docmgr
``import-layout`` endpoints. Pure python-docx, no new dependencies.
"""

from __future__ import annotations

import base64
import re
from copy import deepcopy
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from lxml import etree

_PAPER_DIMS = {
    "A4": (21.0, 29.7),
    "A3": (29.7, 42.0),
    "B5": (17.6, 25.0),
    "letter": (21.59, 27.94),
}
_DRAWML = "http://schemas.openxmlformats.org/drawingml/2006/main"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TOC_TEXT_RE = re.compile(r"^目\s*录$|^contents$", re.I)
_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}")


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


_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def _clean_font(name: str | None) -> str | None:
    """A real font name, or None. Filters OOXML locale codes (zh-CN / en-US) that
    appear in w:eastAsia slots but are region tags, not fonts."""
    if not name or _LOCALE_RE.match(name):
        return None
    return name


def _style_eastAsia(style) -> str | None:
    """w:eastAsia CJK font declared on a style (cleaned), or None."""
    try:
        m = re.search(r'w:eastAsia="([^"]+)"', style.element.xml)
        return _clean_font(m.group(1)) if m else None
    except Exception:
        return None


def _doc_defaults_eastAsia(doc) -> str | None:
    """Document default CJK font from w:docDefaults' <w:rFonts w:eastAsia=...>.

    CN docs commonly leave the Normal style and most runs unformatted, so body text
    inherits this default (typically 宋体). Scoped to rFonts so it ignores the
    unrelated <w:lang w:eastAsia="zh-CN"> locale tag."""
    try:
        m = re.search(r'<w:docDefaults>.*?<w:rFonts[^>]*w:eastAsia="([^"]+)"', doc.styles.element.xml, re.S)
        return _clean_font(m.group(1)) if m else None
    except Exception:
        return None


def _style_color(style, default: str) -> str:
    try:
        rgb = style.font.color.rgb
        if rgb is not None:
            return f"#{rgb}"  # editor <input type="color"> requires #RRGGBB
    except Exception:
        pass
    return default


def _run_font(run) -> str | None:
    """w:eastAsia CJK font on a run (cleaned), or None when the run sets none and
    therefore inherits. Deliberately NOT run.font.name — that returns the Western
    (ascii) font (e.g. Times New Roman), which is wrong for CJK text."""
    try:
        m = re.search(r'w:eastAsia="([^"]+)"', run._element.xml)
        return _clean_font(m.group(1)) if m else None
    except Exception:
        return None


def _cjk_font(doc, style, paragraphs) -> str:
    """Resolve the CJK font body/heading text actually renders in.

    CN docs rarely set w:eastAsia on every run — most runs are *silent* and inherit
    the document/style default. So if a MAJORITY of runs declare eastAsia the text
    actively uses that font (take the dominant); otherwise the runs inherit and we
    walk style.eastAsia → docDefaults.eastAsia → style.font.name → 宋体. Counting the
    few runs that DO declare (often emphasis/labels) would mislabel the whole body —
    e.g. 17 黑体 runs among 887 silent 宋体 runs must not win."""
    runs = [r for p in paragraphs for r in p.runs]
    declared: dict[str, int] = {}
    for r in runs:
        fam = _run_font(r)
        if fam:
            declared[fam] = declared.get(fam, 0) + 1
    if runs and declared:
        top_font, top_n = max(declared.items(), key=lambda kv: kv[1])
        if top_n >= len(runs) * 0.5:
            return top_font
    return _style_eastAsia(style) or _doc_defaults_eastAsia(doc) or _clean_font(style.font.name) or "宋体"


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
# 第三支 `^\d{1,3}\s{2,}\S` 覆盖中文报告常见的手写章号 "1  设计依据"（数字+≥2空格），
# 不会误伤 "2024 年" / "100 万元"（无 ≥2 空格分隔）。
_HEADING_DEC_RE = re.compile(r"^\d+[.\)）]|^\d+\.\d+|^\d{1,3}\s{2,}\S")

# Figure caption detection. CN report authors hand-type captions (图1-1 / 图1) rather
# than using Word's Caption style, so we match the text first and the style as a fallback.
_CAPTION_STYLE_RE = re.compile(r"caption|题注", re.I)
_CAPTION_TEXT_RE = re.compile(r"^(图|figure|fig\.?)\s*[\d一二三四五六七八九十]+", re.I)
_CAPTION_CHAPTER_RE = re.compile(r"^(图|figure|fig\.?)\s*\d+[-－—.]\d+", re.I)
_SOURCE_RE = re.compile(r"(数据来源|资料来源|图片来源|来源|source)", re.I)


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
    run_size, _ = _dominant_run_font(body)
    style_size = style.font.size.pt if style.font.size else None
    size = run_size or style_size
    family = _cjk_font(doc, style, body)

    # Real docs set spacing/indent per-paragraph, not on the Normal style — sample the
    # dominant paragraph value, then fall back to the style / a sensible default.
    line_spacing = _dominant(body, lambda p: _line_spacing_value(p.paragraph_format.line_spacing, size))
    if line_spacing is None:
        line_spacing = _line_spacing_value(pf.line_spacing, size) or 1.5
    space_after = _dominant(body, _para_space_after_pt)
    if space_after is None:
        sa = pf.space_after
        # 样例段落普遍未声明 space_after 且 pPrDefault 为空 → 段后距实为 0（密集正文），
        # 不是任意猜测值。仅当 Normal 样式显式定义时才取它。
        space_after = int(sa.pt) if sa else 0
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
    """Per-level heading styles, ONLY for levels the document actually uses.

    A level with zero Heading paragraphs is skipped — otherwise we'd emit Word's
    template-default style (often an English font like Cambria) for a level the sample
    never uses, polluting the editor with bogus values. ponytail: real docs format
    headings on runs too, so we read runs first and fall back to the Heading style.
    """
    defaults = {1: 16, 2: 14, 3: 12, 4: 12}
    out = []
    for level in range(1, 5):
        hps = _heading_paragraphs(doc, level)
        if not hps:
            continue  # 文档未使用该级标题 → 跳过,避免输出 Word 模板残留(如 Cambria)污染表单
        try:
            style = doc.styles[f"Heading {level}"]
        except KeyError:
            continue
        run_size, _ = _dominant_run_font(hps)
        style_size = style.font.size.pt if style.font.size else None
        size = run_size or style_size
        run_bold = _dominant_run_bold(hps)
        bold = run_bold if run_bold is not None else bool(style.font.bold)
        out.append(
            {
                "level": level,
                "fontFamily": _cjk_font(doc, style, hps),
                "fontSize": int(size) if size else defaults[level],
                "fontWeight": 700 if bold else 400,
                # 样例 H1 样式与 run 均未定义 color（Word auto），auto 渲染为黑色 #000000，
                # 不是猜测的深灰 #333333。
                "color": _dominant_run_color(hps) or _style_color(style, "#000000"),
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
    stripe = bool(_style_conditional_shading(table, "band1Row") or _style_conditional_shading(table, "band2Row"))
    return {
        # No fill detected → white (no-fill), never an invented blue. Real fill comes
        # from direct cell shading or the table style's firstRow band above.
        "headerBg": f"#{header_bg}" if header_bg else "#FFFFFF",
        "headerColor": header_color or "#333333",
        "borderColor": _tbl_border_color(table) or "#CCCCCC",
        "stripeRows": stripe,
    }


def _extract_header_footer(doc) -> dict:
    sections = doc.sections

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

    # A multi-section report commonly leaves the cover/TOC sections blank and only
    # fills the body sections, so scan every section: take the first non-empty header/
    # footer, and turn on page-number/logo if ANY section shows them.
    header_text = next((_text(s.header) for s in sections if _text(s.header)), "")
    footer_text = next((_text(s.footer) for s in sections if _text(s.footer)), "")
    return {
        "headerText": header_text,
        "footerText": footer_text,
        "showPageNumber": any(_has_page_field(s.footer) or _has_page_field(s.header) for s in sections),
        "showLogo": any(_has_image(s.header) for s in sections),
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
    has_toc = False
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            break
        if not p.text.strip():
            continue
        # 目录页(TOC)不是封面:toc 样式条目或"目录"/"contents"标题属于前置目录。
        if re.search(r"toc|目录|contents", p.style.name or "", re.I) or re.match(r"^目\s*录$|^contents$", p.text.strip(), re.I):
            has_toc = True
            continue
        pre.append(p)

    # 第一个 Heading 前是目录页 → 按无封面处理(回退 C,保留编辑器原状,不臆造封面)。
    if has_toc:
        return None

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


def _style_id_sets(doc) -> tuple[set[str], set[str]]:
    """Precompute (heading_style_ids, toc_style_ids) from doc.styles."""
    heading_ids: set[str] = set()
    toc_ids: set[str] = set()
    try:
        for st in doc.styles:
            name = (getattr(st, "name", "") or "").lower()
            sid = getattr(st, "style_id", None)
            if not sid:
                continue
            if name.startswith("heading"):
                heading_ids.add(sid)
            if "toc" in name:
                toc_ids.add(sid)
    except Exception:
        pass
    return heading_ids, toc_ids


def _max_run_font_pt(p_el) -> float:
    """Largest <w:sz w:val=...> (half-points) among runs in a <w:p> element."""
    best = 0.0
    for r in p_el.findall(f"{{{_W}}}r"):
        rpr = r.find(f"{{{_W}}}rPr")
        if rpr is None:
            continue
        sz = rpr.find(f"{{{_W}}}sz")
        val = sz.get(f"{{{_W}}}val") if sz is not None else None
        if val and val.isdigit():
            best = max(best, int(val) / 2.0)
    return best


def _para_text(p_el) -> str:
    return "".join((t.text or "") for t in p_el.iter(f"{{{_W}}}t"))


def _prefill_cover_slots(cover_blocks) -> list[dict]:
    """Prefill standard variable slots by scanning cover-region text. camelCase keys."""
    paras: list[tuple] = []  # (p_el, text) incl. paragraphs inside tables
    for b in cover_blocks:
        for p in b.iter(f"{{{_W}}}p"):
            txt = _para_text(p)
            if txt.strip():
                paras.append((p, txt))
    full = "\n".join(t for _, t in paras)

    slots: list[dict] = []

    def add(slot_id: str, label: str, value, default_from: str | None = None) -> None:
        if value:
            slots.append({"id": slot_id, "label": label, "kind": "variable", "sampleValue": str(value).strip(), "defaultFrom": default_from})

    # title: largest-font paragraph, else 专篇/报告书/计算书 keyword
    title, best_sz = "", 0.0
    for p, txt in paras:
        sz = _max_run_font_pt(p)
        if sz > best_sz and len(txt.strip()) >= 2:
            best_sz, title = sz, txt.strip()
    if not title:
        m = re.search(r"(.{2,40}?(?:专篇|报告书|计算书|设计说明).{0,20})", full)
        if m:
            title = m.group(1).strip()
    add("title", "报告标题", title, "doc_title")

    m = re.search(r"项目名(?:称)?[:：\s]*(\S.{0,39})", full)
    add("project_name", "项目名", m.group(1) if m else None)

    m = re.search(r"(?:建设单位|业主单位|业主)[:：]\s*(\S.{0,39})", full)
    add("client", "建设单位", m.group(1) if m else None, "frontmatter:client")

    m = re.search(r"(?:项目编号|工程编号|编号)[:：]\s*(\S.{0,39})", full)
    add("project_number", "项目编号", m.group(1) if m else None)

    m = re.search(r"(?:设计阶段|阶段)[:：]\s*(\S.{0,29})", full)
    add("stage", "设计阶段", m.group(1) if m else None)

    m = _DATE_RE.search(full)
    add("date", "日期", m.group(0) if m else None, "today")

    return slots


def _extract_cover_master(doc, source_file: str = "") -> dict | None:
    """Extract the cover region (blocks before the TOC marker or first Heading) as
    a reusable OOXML master + prefilled slots. Returns None when no meaningful
    cover exists (degrades to the legacy cover_template fallback)."""
    body = doc.element.body
    heading_ids, toc_ids = _style_id_sets(doc)

    cover_blocks: list = []
    boundary: str | None = None

    for child in body.iterchildren():
        tag = child.tag
        if tag == f"{{{_W}}}sectPr":  # final section properties — body content ended
            break
        if tag == f"{{{_W}}}p":
            style_el = child.find(f"{{{_W}}}pPr/{{{_W}}}pStyle")
            style_val = style_el.get(f"{{{_W}}}val") if style_el is not None else None
            text = _para_text(child).strip()
            if _TOC_TEXT_RE.match(text) or style_val in toc_ids:
                boundary = "before_toc"
                break
            if style_val in heading_ids:
                boundary = "before_first_heading"
                break
            cover_blocks.append(child)
        elif tag == f"{{{_W}}}tbl":
            cover_blocks.append(child)
        # other elements (bookmarkStart, etc.) ignored

    if boundary is None:
        return None

    has_table = any(b.tag == f"{{{_W}}}tbl" for b in cover_blocks)
    has_text = any(_para_text(b).strip() for b in cover_blocks if b.tag == f"{{{_W}}}p")
    if not has_table and not has_text:
        return None

    xml = "".join(etree.tostring(deepcopy(b), encoding="unicode") for b in cover_blocks)

    images: list[dict] = []
    seen: set[str] = set()
    for b in cover_blocks:
        for blip in b.iter(f"{{{_DRAWML}}}blip"):
            rid = blip.get(f"{{{_REL}}}embed")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            part = doc.part.related_parts.get(rid)
            blob = getattr(part, "blob", None)
            if not blob:
                continue
            ext = "png"
            partname = getattr(part, "partname", None)
            if partname and "." in str(partname):
                ext = str(partname).rsplit(".", 1)[-1].lower()
            images.append({"origRid": rid, "ext": ext, "b64": base64.b64encode(blob).decode("ascii")})

    return {
        "mode": "master",
        "xml": xml,
        "images": images,
        "slots": _prefill_cover_slots(cover_blocks),
        "sourceFile": source_file,
        "boundary": boundary,
    }


def _is_caption(para) -> bool:
    """A figure-caption paragraph: Caption/题注 style, or text like 图1-1 / Figure 2."""
    if _CAPTION_STYLE_RE.search(para.style.name or ""):
        return True
    return bool(_CAPTION_TEXT_RE.match(para.text.strip()))


def _extract_figure_styles(doc) -> dict | None:
    """Best-effort figure-style detection: caption position / numbering / source line.

    Returns None when the sample has neither image paragraphs nor caption text — the
    caller then leaves the figure section untouched (don't clobber user config).
    ponytail: caption adjacency heuristics (图1-1 → chapter, 图1 → continuous,
    image-then-caption → below) match how CN report authors hand-type captions; honor
    tblLook/abstractNum only if a sample mismatches these defaults.
    """
    paragraphs = doc.paragraphs
    cap_indices = {i for i, p in enumerate(paragraphs) if _is_caption(p)}
    image_indices = [i for i, p in enumerate(paragraphs) if _para_has_image(p)]
    if not cap_indices and not image_indices:
        return None

    # Caption position: a caption right after an image → below; right before → above.
    below = sum(1 for i in image_indices if (i + 1) in cap_indices)
    above = sum(1 for i in image_indices if (i - 1) in cap_indices)
    caption_position = "above" if above > below else "below"

    # Numbering: a chapter-segmented caption (图1-1) → chapter, else continuous (图1).
    numbering = "continuous"
    for i in cap_indices:
        if _CAPTION_CHAPTER_RE.match(paragraphs[i].text.strip()):
            numbering = "chapter"
            break

    show_source = any(_SOURCE_RE.search(p.text) for p in paragraphs)

    return {
        "captionPosition": caption_position,
        "numbering": numbering,
        "showSource": show_source,
    }


def extract_layout_from_docx(data: bytes, source_file: str = "") -> dict:
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
    cover_master = _extract_cover_master(doc, source_file=source_file)

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
        "figure_styles": _extract_figure_styles(doc),
        "header_footer": _extract_header_footer(doc),
        "cover_template": cover,
        "cover_master": cover_master,
        "cover_detected": cover_master is not None or cover is not None,
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
    return extract_layout_from_docx(data, source_file=filename or "")
