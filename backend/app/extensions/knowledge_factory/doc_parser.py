"""Document parser for Word (.docx) and PDF files.

Extracts structured content from reports for template extraction:
- headings: chapter/section hierarchy with levels and titles
- tables: structured table data with captions, columns, and rows
- full_text: concatenated body text in document order

Word: expat SAX parser (built-in) for true streaming — 64KB chunks,
      never loads entire XML DOM. python-docx fallback for edge cases.
PDF:  PyMuPDF (fitz) text extraction + regex. Scanned PDFs error out.
"""

from __future__ import annotations

import logging
import re
import zipfile as _zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.parsers.expat import ParserCreate, ExpatError

logger = logging.getLogger(__name__)


# ── Output data classes ──

@dataclass
class Heading:
    title: str
    level: int
    line_number: int = 0
    style_name: str = ""
    # ponytail: paragraph index + char offset into full_text.
    # -1 = unknown (regex-fallback headings have no anchor).
    # Stored as offsets (not pre-sliced text) to avoid duplicating subtree
    # text across every heading — a tree of N nodes would otherwise hold
    # O(N²) text. Section text is sliced from full_text on demand.
    para_idx: int = -1
    text_offset: int = -1


@dataclass
class DocTable:
    caption: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    page: int = 0


@dataclass
class ParsedDocument:
    file_path: str
    file_type: str
    headings: list[Heading] = field(default_factory=list)
    tables: list[DocTable] = field(default_factory=list)
    full_text: str = ""
    error: str = ""

    def finalize_sections(self, paragraphs: list[str]) -> None:
        """Compute each heading's char offset in full_text.

        Stores only offsets (O(N) memory), not pre-sliced subtree text.
        section_text_by_title slices full_text on demand — correct and
        memory-bounded regardless of heading tree depth.
        """
        offsets: list[int] = []
        pos = 0
        for p in paragraphs:
            offsets.append(pos)
            pos += len(p) + 2  # +2 for "\n\n" separator
        for h in self.headings:
            if 0 <= h.para_idx < len(offsets):
                h.text_offset = offsets[h.para_idx]

    def section_text_by_title(self, title: str, level: int = 0, max_chars: int = 6000) -> str:
        """Slice exact source text for a heading (offset-based, on demand).

        subtree = full_text[heading.offset : next_same_or_higher_level.offset].
        Returns "" if no anchored match (regex-fallback or offset unknown) —
        caller then falls back to fuzzy matching.
        """
        if not self.full_text:
            return ""
        norm = normalize_text(title)
        fallback = ""
        for hi, h in enumerate(self.headings):
            if level and h.level != level:
                continue
            matched = normalize_text(h.title) == norm
            if not matched and not (h.title in title or title in h.title):
                continue
            if h.text_offset < 0:
                continue
            end = len(self.full_text)
            for j in range(hi + 1, len(self.headings)):
                nj = self.headings[j]
                if nj.level <= h.level and nj.text_offset >= 0:
                    end = nj.text_offset
                    break
            text = self.full_text[h.text_offset:end][:max_chars]
            if matched:
                return text
            if not fallback:
                fallback = text
        return fallback

    def section_length(self, idx: int) -> int:
        """Char length of heading[idx]'s subtree source (for min_section_length filter).

        0 if heading has no anchor (regex fallback) — caller keeps such headings.
        """
        if idx < 0 or idx >= len(self.headings):
            return 0
        h = self.headings[idx]
        if h.text_offset < 0:
            return 0
        end = len(self.full_text)
        for j in range(idx + 1, len(self.headings)):
            nj = self.headings[j]
            if nj.level <= h.level and nj.text_offset >= 0:
                end = nj.text_offset
                break
        return max(0, end - h.text_offset)


# ── Text normalization ──

_STOP_WORDS_RE = re.compile(r"[的、，。；：（）\(\)\s]+")


def normalize_text(text: str) -> str:
    cleaned = _STOP_WORDS_RE.sub("", text.lower().strip())
    return re.sub(r"\s+", "", cleaned)


# ── Regex fallback patterns ──

_CN_CHAPTER = re.compile(r"^第[一二三四五六七八九十百千\d]+[章节条款段]\s*[\.、\s]?\s*(.+)")
_CN_PAREN = re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]\s*(.+)")
_CN_NUMBERED = re.compile(r"^[一二三四五六七八九十]+[、\.\s]\s*(.+)")
_NUMBERED = re.compile(r"^(\d+(?:[\.]\d+)*)[、.\s]+(.+)$")
_TOC_ENTRY = re.compile(r".*\t\d+$|.* {3,}\d+$")


def _heading_level_from_number(num_str: str) -> int:
    return min(num_str.count(".") + 1, 3)


def _is_noise_line(line: str) -> bool:
    if any(c in line for c in ("□", "?", "？")):
        return True
    t = line.strip()
    if re.match(r"^\d+[、，]", t) and len(t) > 15:
        return True
    return False


def _scan_headings_regex(text: str) -> list[Heading]:
    headings: list[Heading] = []
    line_no = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) > 80:
            line_no += 1
            continue
        if _TOC_ENTRY.match(line):
            line_no += 1
            continue
        if _is_noise_line(line):
            line_no += 1
            continue

        matched = None
        if m := _CN_CHAPTER.match(line):
            matched = Heading(title=line, level=1, line_number=line_no, style_name="cn-chapter")
        elif m := _CN_PAREN.match(line):
            matched = Heading(title=line, level=2, line_number=line_no, style_name="cn-paren")
        elif m := _CN_NUMBERED.match(line):
            matched = Heading(title=line, level=2, line_number=line_no, style_name="cn-numbered")
        elif m := _NUMBERED.match(line):
            matched = Heading(title=line, level=_heading_level_from_number(m.group(1)),
                            line_number=line_no, style_name="numbered")
        if matched:
            headings.append(matched)
        line_no += 1

    seen: set[str] = set()
    return [h for h in headings if h.title not in seen and not seen.add(h.title)]  # type: ignore[func-returns-value]


# ── Main dispatch ──

def parse_document(file_path: str) -> ParsedDocument:
    path = Path(file_path)
    ext = path.suffix.lower().lstrip(".")
    if ext == "docx":
        return parse_docx(file_path)
    elif ext == "pdf":
        return parse_pdf(file_path)
    else:
        return ParsedDocument(file_path=file_path, file_type=ext,
                            error=f"不支持的文件格式: .{ext}，仅支持 .docx 和 .pdf")


# ── Word parser (dual-path: expat fast + python-docx fallback) ──

_HEADING_STYLES = {
    "heading1": 1, "heading 1": 1, "1": 1, "heading11": 1,
    "heading2": 2, "heading 2": 2, "2": 2, "heading21": 2,
    "heading3": 3, "heading 3": 3, "3": 3, "heading31": 3,
}


def parse_docx(file_path: str) -> ParsedDocument:
    path = Path(file_path)
    if not path.exists():
        return ParsedDocument(file_path=file_path, file_type="docx",
                            error=f"文件不存在: {file_path}")

    # Primary: expat SAX (true streaming, <30s for 50MB)
    try:
        result = _parse_docx_expat(path)
        if result is not None and (result.headings or result.tables):
            return result
    except Exception as e:
        logger.warning(f"expat parsing failed for {file_path}: {e}")

    # Fallback: python-docx (slow, handles edge cases)
    return _parse_docx_python_docx(file_path)


def _parse_docx_expat(path: Path) -> ParsedDocument | None:
    """Parse docx using expat SAX — 64KB chunk streaming, zero DOM.

    Reads word/document.xml directly from the ZIP without extracting
    to temp files. Memory = O(headings + tables), not O(document size).
    """
    try:
        zf = _zipfile.ZipFile(str(path), "r")
        if "word/document.xml" not in zf.namelist():
            zf.close()
            return None
        xml_file = zf.open("word/document.xml")
    except (_zipfile.BadZipFile, KeyError) as e:
        logger.warning(f"Failed to open docx ZIP: {e}")
        return None

    headings: list[Heading] = []
    tables: list[DocTable] = []
    paragraphs: list[str] = []
    line_no = 0

    # SAX state
    cur_text: list[str] = []
    cur_style: str = ""
    in_p = False
    in_t = False
    tbl_rows: list[list[str]] = []
    row_cells: list[str] = []
    in_tbl = False
    in_tr = False
    in_tc = False

    def start(name: str, attrs: dict):
        nonlocal cur_text, cur_style, in_p, in_t
        nonlocal tbl_rows, row_cells, in_tbl, in_tr, in_tc

        if name == "p":
            in_p = True; cur_text = []; cur_style = ""
        elif name == "pStyle" and in_p:
            cur_style = attrs.get("w:val", "").lower()
        elif name == "t":
            in_t = True
        elif name == "tbl":
            in_tbl = True; tbl_rows = []
        elif name == "tr" and in_tbl:
            in_tr = True; row_cells = []
        elif name == "tc" and in_tr:
            in_tc = True

    def end(name: str):
        nonlocal in_p, in_t, in_tbl, in_tr, in_tc
        nonlocal tbl_rows, row_cells, line_no

        if name == "t":
            in_t = False
        elif name == "p" and in_p:
            in_p = False
            text = "".join(cur_text).strip()
            if text:
                paragraphs.append(text)
                lv = _HEADING_STYLES.get(cur_style)
                if lv is not None:
                    headings.append(Heading(title=text, level=lv,
                                           line_number=line_no, style_name=f"Heading {lv}",
                                           para_idx=len(paragraphs) - 1))
            line_no += 1
        elif name == "tc":
            in_tc = False
        elif name == "tr" and in_tr:
            in_tr = False; tbl_rows.append(list(row_cells))
        elif name == "tbl":
            in_tbl = False
            if tbl_rows:
                tables.append(DocTable(
                    columns=tbl_rows[0] if tbl_rows else [],
                    rows=tbl_rows[1:] if len(tbl_rows) > 1 else [],
                ))

    def data(text: str):
        if in_t and in_p and not in_tc:
            cur_text.append(text)
        elif in_t and in_tc:
            row_cells.append(text)

    p = ParserCreate(namespace_separator=":")
    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = data

    try:
        while True:
            chunk = xml_file.read(65536)
            if not chunk:
                break
            p.Parse(chunk, False)
        p.Parse(b"", True)
    except ExpatError as e:
        logger.warning(f"expat parse error in {path.name}: {e}")
        return None
    finally:
        xml_file.close()
        zf.close()

    full_text = "\n\n".join(paragraphs)
    if not headings and full_text:
        headings = _scan_headings_regex(full_text)

    result = ParsedDocument(file_path=str(path), file_type="docx",
                        headings=headings, tables=tables, full_text=full_text)
    result.finalize_sections(paragraphs)
    return result


def _parse_docx_python_docx(file_path: str) -> ParsedDocument:
    """Fallback: python-docx parser for edge cases expat can't handle."""
    try:
        import docx
    except ImportError:
        return ParsedDocument(file_path=file_path, file_type="docx",
                            error="python-docx 未安装")

    path = Path(file_path)
    try:
        doc = docx.Document(str(path))
    except Exception as e:
        return ParsedDocument(file_path=file_path, file_type="docx",
                            error=f"Word 文件解析失败: {e}")

    headings: list[Heading] = []
    tables: list[DocTable] = []
    paragraphs: list[str] = []
    line_no = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            line_no += 1; continue
        paragraphs.append(text)
        s = (para.style.name if para.style else "").lower()
        if "heading 1" in s or s == "heading1":
            headings.append(Heading(title=text, level=1, line_number=line_no, style_name=para.style.name, para_idx=len(paragraphs) - 1))
        elif "heading 2" in s or s == "heading2":
            headings.append(Heading(title=text, level=2, line_number=line_no, style_name=para.style.name, para_idx=len(paragraphs) - 1))
        elif "heading 3" in s or s == "heading3":
            headings.append(Heading(title=text, level=3, line_number=line_no, style_name=para.style.name, para_idx=len(paragraphs) - 1))
        line_no += 1

    for table in doc.tables:
        rows = [[c.text.strip() for c in row.cells] for row in table.rows]
        if rows:
            tables.append(DocTable(columns=rows[0] if rows else [],
                                  rows=rows[1:] if len(rows) > 1 else []))

    full_text = "\n\n".join(paragraphs)
    if not headings and full_text:
        headings = _scan_headings_regex(full_text)

    result = ParsedDocument(file_path=file_path, file_type="docx",
                        headings=headings, tables=tables, full_text=full_text)
    result.finalize_sections(paragraphs)
    return result


# ── PDF parser ──

def parse_pdf(file_path: str) -> ParsedDocument:
    path = Path(file_path)
    if not path.exists():
        return ParsedDocument(file_path=file_path, file_type="pdf",
                            error=f"文件不存在: {file_path}")

    try:
        import fitz
        doc = fitz.open(str(path))
        parts = [page.get_text() for page in doc if page.get_text().strip()]
        doc.close()
        full_text = "\n\n".join(parts)
        if not full_text.strip():
            return ParsedDocument(file_path=file_path, file_type="pdf",
                                error="PDF 无可提取文字（可能是扫描版），请使用 RAGFlow OCR 路径")
        headings = _scan_headings_regex(full_text)
        return ParsedDocument(file_path=file_path, file_type="pdf",
                            headings=headings, full_text=full_text)
    except ImportError:
        pass

    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        if len([c for c in text if c.isprintable() or c in "\n\r\t "]) < len(text) * 0.5:
            return ParsedDocument(file_path=file_path, file_type="pdf",
                                error="PDF 为二进制内容（可能是扫描版），请使用 RAGFlow OCR 路径")
        return ParsedDocument(file_path=file_path, file_type="pdf",
                            headings=_scan_headings_regex(text), full_text=text)
    except Exception as e:
        return ParsedDocument(file_path=file_path, file_type="pdf",
                            error=f"PDF 解析失败: {e}")


# ── Structure hint builder ──

def build_structure_hint(parsed: ParsedDocument, max_chars: int = 5000) -> str:
    headings = parsed.headings
    if not headings:
        return parsed.full_text[:max_chars]

    h1s = [h for h in headings if h.level == 1]
    if not h1s:
        h1s = [h for h in headings if h.level <= 2]
    if not h1s:
        h1s = headings[:20]

    parts = [f"## 文档章节目录（自动识别，共 {len(h1s)} 章）\n"]
    for h in h1s:
        parts.append(f"- {h.title}")
    parts.append("\n## 各章节内容摘要（每章节前300字）\n")
    for h in h1s:
        idx = parsed.full_text.find(h.title)
        parts.append(f"### {h.title}\n{parsed.full_text[idx:idx + 300] if idx >= 0 else '(未找到)'}\n")

    result = "\n".join(parts)
    return result[:max_chars] + ("\n...(内容已截断)" if len(result) > max_chars else "")
