# EAI-CUSTOM: geo-sample-bank Phase 1 三分支解析（spec 2026-09-01 §3.3）。
# docx→python-docx 结构化转 md；pdf 文字版→pymupdf4llm；字符密度稀疏判定扫描件→eai-flow-ocr。
# MathType OLE 公式不解析，落 [公式:pN] 占位（W1 比拟法公式人工转录先例）。
from __future__ import annotations

import io
import os

import httpx

OCR_TIMEOUT = 1800.0  # contract_price document_parser 同款


class ScannedPdfError(Exception):
    """文字密度低于阈值——判定为扫描件，须走 OCR。"""


def docx_to_markdown(data: bytes) -> str:
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    formula_no = 0
    for block in doc.iter_inner_content():  # python-docx>=1.1：按文档顺序交错产出段落/表格
        if isinstance(block, Paragraph):
            text = block.text.strip()
            style = (block.style.name or "").lower() if block.style is not None else ""
            if not text:
                # OLE 公式对象：w:object 元素存在且无文本 → 占位
                if block._p.findall(".//" + qn("w:object")):
                    formula_no += 1
                    lines.append(f"[公式:p{formula_no}]")
                continue
            if style.startswith("heading 1") or style == "title":
                lines.append(f"## {text}")
            elif style.startswith("heading 2"):
                lines.append(f"### {text}")
            elif style.startswith(("heading 3", "heading 4", "heading 5")):
                lines.append(f"#### {text}")
            else:
                lines.append(text)
        elif isinstance(block, Table):
            rows = [[c.text.strip().replace("|", "\\|") for c in r.cells] for r in block.rows]
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
    if density < 200:  # 每页<200字符 → 扫描件（harness file_conversion 稀疏回退同思路，改抛错转 OCR）
        raise ScannedPdfError(f"文字密度 {density:.0f} 字符/页 < 200，判定扫描件，需 OCR")
    return pymupdf4llm.to_markdown(doc)


async def ocr_pdf_to_markdown(data: bytes, base_url: str | None = None) -> str:
    url = (base_url or os.environ.get("OCR_SERVICE_URL", "http://eai-flow-ocr:8010")).rstrip("/") + "/ocr"
    async with httpx.AsyncClient(timeout=OCR_TIMEOUT) as client:
        resp = await client.post(url, files={"file": ("doc.pdf", data, "application/pdf")})
        resp.raise_for_status()
    pages = resp.json().get("pages", [])
    return "\n\n".join(p.get("text", "") for p in pages)


async def parse_document(file_name: str, data: bytes) -> tuple[str, str]:
    """统一入口 → (markdown, parse_mode)。docx 分支同步、pdf 分支可能转 OCR。"""
    lower = file_name.lower()
    if lower.endswith(".docx"):
        return docx_to_markdown(data), "docx"
    if lower.endswith(".pdf"):
        try:
            return pdf_text_to_markdown(data), "pdf_text"
        except ScannedPdfError:
            return await ocr_pdf_to_markdown(data), "pdf_ocr"
    raise ValueError(f"不支持的文件类型: {file_name}（仅 .docx/.pdf）")
