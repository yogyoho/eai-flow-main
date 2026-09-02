# EAI-CUSTOM: geo-sample-bank Phase 1 三分支解析（spec 2026-09-01 §3.3）。
# docx→python-docx 结构化转 md；pdf 文字版→pymupdf4llm；字符密度稀疏判定扫描件→eai-flow-ocr。
# MathType OLE / OMML 公式不解析，落 [公式:pN] 占位（W1 比拟法公式人工转录先例）。
# 已知限制：嵌套表格不展开；合并单元格文本按跨格重复；公式仅 OLE/OMML 占位不转写。
from __future__ import annotations

import asyncio
import io
import os

import httpx

OCR_TIMEOUT = 1800.0  # contract_price document_parser 同款
# 每页可提取字符数低于此值即判扫描件。正常文字版 A4 报告约 200-2000+ 字符/页，
# 扫描件文字层为空或仅零星水印页眉。harness file_conversion 的稀疏回退同思路
# （那边回退 MarkItDown，这里改抛 ScannedPdfError 转 OCR）。
SCAN_DENSITY_THRESHOLD = 200
# eai-flow-ocr 默认只对前 3 页做整页文字 OCR（text_pages=3，全页 OCR 大致翻倍运行
# 时的运行时考量）；样例库要全文语料，显式放开到 999 页（引擎按 idx<=text_pages 门控）。
OCR_TEXT_PAGES = "999"


class ScannedPdfError(Exception):
    """文字密度低于阈值——判定为扫描件，须走 OCR。"""


def _docx_formula_blocks(paragraph) -> list:  # noqa: ANN001 — docx Element, 避免顶层重依赖
    from docx.oxml.ns import qn

    return paragraph._p.findall(".//" + qn("w:object")) + paragraph._p.findall(".//" + qn("m:oMath"))


# 中文/英文 Word 内置样式名归一——中文 authored docx 的样式名是「标题 1」而非
# "Heading 1"，不归一则整篇降级正文、Phase 2 节号切片将找零节（终审 R1）。
_STYLE_ALIASES = {"标题 1": "heading 1", "标题 2": "heading 2", "标题 3": "heading 3", "标题 4": "heading 4", "标题 5": "heading 5", "标题": "title"}


def _heading_level(style_name: str | None) -> int | None:
    """样式名 → 标题级（1=##/2=###/3+=####）；非标题返回 None。"""
    if not style_name:
        return None
    s = _STYLE_ALIASES.get(style_name.strip(), style_name.strip()).lower()
    if s == "title" or s.startswith("heading 1"):
        return 1
    if s.startswith("heading 2"):
        return 2
    if s.startswith(("heading 3", "heading 4", "heading 5")):
        return 3
    return None


def docx_to_markdown(data: bytes) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    formula_no = 0
    for block in doc.iter_inner_content():  # python-docx>=1.1：按文档顺序交错产出段落/表格
        if isinstance(block, Paragraph):
            text = block.text.strip()
            has_formula = bool(_docx_formula_blocks(block))
            if not text:
                # OLE/OMML 公式对象：元素存在且无文本 → 占位
                if has_formula:
                    formula_no += 1
                    lines.append(f"[公式:p{formula_no}]")
                continue
            if has_formula:
                # 行内公式（有文本的段落里夹公式对象）：文本保留 + 占位后缀
                formula_no += 1
                text = f"{text} [公式:p{formula_no}]"
            lvl = _heading_level(block.style.name if block.style is not None else None)
            if lvl == 1:
                lines.append(f"## {text}")
            elif lvl == 2:
                lines.append(f"### {text}")
            elif lvl == 3:
                lines.append(f"#### {text}")
            else:
                lines.append(text)
        elif isinstance(block, Table):
            rows = [[c.text.strip().replace("\n", "<br>").replace("|", "\\|") for c in r.cells] for r in block.rows]
            if not rows:
                continue
            header = rows[0]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for r in rows[1:]:
                lines.append("| " + " | ".join(r) + " |")
    return "\n\n".join(lines)


def pdf_text_to_markdown(data: bytes) -> str:
    import fitz
    import pymupdf4llm

    doc = fitz.open(stream=data, filetype="pdf")
    total_chars = sum(len(p.get_text()) for p in doc)
    density = total_chars / max(len(doc), 1)
    if density < SCAN_DENSITY_THRESHOLD:
        raise ScannedPdfError(f"文字密度 {density:.0f} 字符/页 < {SCAN_DENSITY_THRESHOLD}，判定扫描件，需 OCR")
    return pymupdf4llm.to_markdown(doc)


def _ocr_page_to_md(page: dict) -> str:
    """一页 → 文本 + 拍平的表格块（表在文后，块间空行）。"""
    parts = [page.get("text", "")]
    for table in page.get("tables", []):
        rows = []
        for row in table.get("rows", []):
            cells = [(_cell_text(c).replace("|", "\\|")) for c in row]
            rows.append("| " + " | ".join(cells) + " |")
        if rows:
            parts.append("\n".join(rows))
    return "\n\n".join(p for p in parts if p.strip())


def _cell_text(cell) -> str:  # noqa: ANN001 — Cell dict 或裸 str（服务端 schema 是 {text,bbox,confidence}）
    return cell.get("text", "") if isinstance(cell, dict) else str(cell)


async def ocr_pdf_to_markdown(data: bytes, base_url: str | None = None) -> str:
    url = (base_url or os.environ.get("OCR_SERVICE_URL", "http://eai-flow-ocr:8010")).rstrip("/") + "/ocr"
    resp = None
    async with httpx.AsyncClient(timeout=OCR_TIMEOUT) as client:
        # M3: 对端半途断流（RemoteProtocolError）重试，30s/60s 退避——contract_price 先例
        for attempt in range(3):
            try:
                resp = await client.post(url, files={"file": ("doc.pdf", data, "application/pdf")}, data={"text_pages": OCR_TEXT_PAGES})
                resp.raise_for_status()
                break
            except httpx.RemoteProtocolError:
                if attempt == 2:
                    raise
                await asyncio.sleep(30.0 * (attempt + 1))
    pages = (resp.json() if resp is not None else {}).get("pages", [])
    md = "\n\n".join(_ocr_page_to_md(p) for p in pages)
    if not md.strip():
        raise ValueError("OCR 返回空文本——服务异常或空文档")
    return md


async def parse_document(file_name: str, data: bytes) -> tuple[str, str]:
    """统一入口 → (markdown, parse_mode)。docx 分支同步、pdf 分支可能转 OCR。"""
    lower = file_name.lower()
    if lower.endswith(".docx"):
        return await asyncio.to_thread(docx_to_markdown, data), "docx"
    if lower.endswith(".pdf"):
        try:
            return await asyncio.to_thread(pdf_text_to_markdown, data), "pdf_text"
        except ScannedPdfError:
            return await ocr_pdf_to_markdown(data), "pdf_ocr"
    raise ValueError(f"不支持的文件类型: {file_name}（仅 .docx/.pdf）")
