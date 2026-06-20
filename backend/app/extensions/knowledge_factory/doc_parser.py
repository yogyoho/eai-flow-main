"""Document parser for Word (.docx) and PDF files.

Extracts structured content from reports for template extraction:
- headings: chapter/section hierarchy with levels and titles
- tables: structured table data with captions, columns, and rows
- full_text: concatenated body text in document order

Word: uses python-docx — reads Heading styles (deterministic), falls
      back to font-size heuristics + regex for unstyled documents.
PDF:  uses basic text extraction (fallback to RAGFlow OCR when
      scanned/image-only PDFs are detected).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Output data classes ──

@dataclass
class Heading:
    """A detected heading with its level and title text."""
    title: str
    level: int  # 1 = H1/chapter, 2 = H2/section, 3 = H3/sub-section
    line_number: int = 0
    style_name: str = ""  # e.g. "Heading 1" or "font-size:18pt"


@dataclass
class DocTable:
    """A structured table extracted from the document."""
    caption: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    page: int = 0


@dataclass
class ParsedDocument:
    """Result of parsing a single document."""
    file_path: str
    file_type: str  # "docx" or "pdf"
    headings: list[Heading] = field(default_factory=list)
    tables: list[DocTable] = field(default_factory=list)
    full_text: str = ""
    error: str = ""


# ── Text normalization utilities ──

_STOP_WORDS_RE = re.compile(r"[的、，。；：（）\(\)\s]+")


def normalize_text(text: str) -> str:
    """Normalize heading text: strip punctuation/stop words, collapse whitespace.

    Shared by doc_parser and chapter_matching for consistent matching.
    """
    cleaned = _STOP_WORDS_RE.sub("", text.lower().strip())
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


# ── Heading regex patterns (fallback for unstyled documents) ──

# 第一章 / 第二节 / 第三条
_CN_CHAPTER = re.compile(r"^第[一二三四五六七八九十百千\d]+[章节条款段]\s*[\.、\s]?\s*(.+)")
# (一) / (1)
_CN_PAREN = re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]\s*(.+)")
# 一、/ 二、
_CN_NUMBERED = re.compile(r"^[一二三四五六七八九十]+[、\.\s]\s*(.+)")
# 1. Title / 1.1 Title / 1.1.1 Title
_NUMBERED = re.compile(r"^(\d+(?:[\.]\d+)*)[、.\s]+(.+)$")

# Lines looking like TOC entries (page number at end)
_TOC_ENTRY = re.compile(r".*\t\d+$|.* {3,}\d+$")


def _heading_level_from_number(num_str: str) -> int:
    """Return heading level from numbered prefix: 1→1, 1.1→2, 1.1.1→3."""
    dots = num_str.count(".")
    return min(dots + 1, 3)


def _is_noise_line(line: str) -> bool:
    """Return True if line looks like a survey item or inline paragraph."""
    if any(c in line for c in ("□", "?", "？")):
        return True
    t = line.strip()
    if re.match(r"^\d+[、，]", t) and len(t) > 15:
        return True
    return False


def _scan_headings_regex(text: str) -> list[Heading]:
    """Scan plain text for heading lines using regex patterns.

    Used as fallback when document has no structural heading markers
    (e.g. unstyled Word docs, PDFs without reliable font info).
    """
    headings: list[Heading] = []
    lines = text.split("\n")
    line_no = 0

    for line in lines:
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

        # Chinese chapter patterns
        if (m := _CN_CHAPTER.match(line)):
            matched = Heading(title=line, level=1, line_number=line_no, style_name="cn-chapter")
        elif (m := _CN_PAREN.match(line)):
            matched = Heading(title=line, level=2, line_number=line_no, style_name="cn-paren")
        elif (m := _CN_NUMBERED.match(line)):
            matched = Heading(title=line, level=2, line_number=line_no, style_name="cn-numbered")
        elif (m := _NUMBERED.match(line)):
            level = _heading_level_from_number(m.group(1))
            matched = Heading(title=line, level=level, line_number=line_no, style_name="numbered")

        if matched:
            headings.append(matched)

        line_no += 1

    # Deduplicate repeated titles (page headers)
    seen: set[str] = set()
    deduped = []
    for h in headings:
        if h.title not in seen:
            seen.add(h.title)
            deduped.append(h)

    return deduped


# ── Main parse functions ──

def parse_document(file_path: str) -> ParsedDocument:
    """Parse a Word or PDF document and return structured content.

    Dispatches to the appropriate parser based on file extension.
    """
    path = Path(file_path)
    ext = path.suffix.lower().lstrip(".")

    if ext == "docx":
        return parse_docx(file_path)
    elif ext == "pdf":
        return parse_pdf(file_path)
    else:
        return ParsedDocument(
            file_path=file_path,
            file_type=ext,
            error=f"不支持的文件格式: .{ext}，仅支持 .docx 和 .pdf",
        )


def parse_docx(file_path: str) -> ParsedDocument:
    """Parse a Word (.docx) document.

    Strategy:
    1. Read Heading 1/2/3 styles for deterministic chapter detection
    2. Extract tables via doc.tables
    3. Fall back to regex heading scan if no heading styles found
    """
    try:
        import docx
    except ImportError:
        return ParsedDocument(
            file_path=file_path, file_type="docx",
            error="python-docx 未安装，无法解析 Word 文件",
        )

    path = Path(file_path)
    if not path.exists():
        return ParsedDocument(
            file_path=file_path, file_type="docx",
            error=f"文件不存在: {file_path}",
        )

    try:
        doc = docx.Document(str(path))
    except Exception as e:
        return ParsedDocument(
            file_path=file_path, file_type="docx",
            error=f"Word 文件解析失败: {e}",
        )

    headings: list[Heading] = []
    tables: list[DocTable] = []
    paragraphs: list[str] = []
    line_no = 0

    # Extract headings from paragraph styles
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            line_no += 1
            continue

        paragraphs.append(text)

        style_name = (para.style.name if para.style else "").lower()
        if "heading 1" in style_name or style_name == "heading1":
            headings.append(Heading(title=text, level=1, line_number=line_no, style_name=para.style.name))
        elif "heading 2" in style_name or style_name == "heading2":
            headings.append(Heading(title=text, level=2, line_number=line_no, style_name=para.style.name))
        elif "heading 3" in style_name or style_name == "heading3":
            headings.append(Heading(title=text, level=3, line_number=line_no, style_name=para.style.name))

        line_no += 1

    # Extract tables
    for i, table in enumerate(doc.tables):
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)

        if rows:
            caption = ""
            columns = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []
            tables.append(DocTable(
                caption=caption,
                columns=columns,
                rows=data_rows,
                page=0,
            ))

    full_text = "\n\n".join(paragraphs)

    # Fallback: if no heading styles found, use regex
    if not headings:
        logger.info(f"No heading styles found in {file_path}, falling back to regex scan")
        headings = _scan_headings_regex(full_text)

    return ParsedDocument(
        file_path=file_path,
        file_type="docx",
        headings=headings,
        tables=tables,
        full_text=full_text,
    )


def parse_pdf(file_path: str) -> ParsedDocument:
    """Parse a PDF document.

    Current implementation uses basic text extraction via PyMuPDF if available,
    with regex heading detection as fallback. Scanned/image-only PDFs return an
    error — upstream callers should fall back to RAGFlow OCR.
    """
    path = Path(file_path)
    if not path.exists():
        return ParsedDocument(
            file_path=file_path, file_type="pdf",
            error=f"文件不存在: {file_path}",
        )

    # Try PyMuPDF first (best text extraction)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        full_text_parts = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                full_text_parts.append(text)
        full_text = "\n\n".join(full_text_parts)
        doc.close()

        if not full_text.strip():
            return ParsedDocument(
                file_path=file_path, file_type="pdf",
                error="PDF 无可提取文字（可能是扫描版），请使用 RAGFlow OCR 路径",
            )

        headings = _scan_headings_regex(full_text)
        return ParsedDocument(
            file_path=file_path,
            file_type="pdf",
            headings=headings,
            full_text=full_text,
        )
    except ImportError:
        pass

    # Fallback: try basic text extraction
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        # Very basic: try to decode as text
        text = content.decode("utf-8", errors="replace")
        if len([c for c in text if c.isprintable() or c in "\n\r\t "]) < len(text) * 0.5:
            return ParsedDocument(
                file_path=file_path, file_type="pdf",
                error="PDF 为二进制内容（可能是扫描版），请使用 RAGFlow OCR 路径",
            )
        headings = _scan_headings_regex(text)
        return ParsedDocument(
            file_path=file_path,
            file_type="pdf",
            headings=headings,
            full_text=text,
        )
    except Exception as e:
        return ParsedDocument(
            file_path=file_path, file_type="pdf",
            error=f"PDF 解析失败: {e}",
        )


def build_structure_hint(parsed: ParsedDocument, max_chars: int = 5000) -> str:
    """Build a compact structure hint from parsed headings for LLM chapter inference.

    Only includes H1-level headings. If no headings found, returns truncated full_text.
    """
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
        if idx >= 0:
            snippet = parsed.full_text[idx:idx + 300]
            parts.append(f"### {h.title}\n{snippet}\n")
        else:
            parts.append(f"### {h.title}\n（内容未找到）\n")

    result = "\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n...(内容已截断)"
    return result
