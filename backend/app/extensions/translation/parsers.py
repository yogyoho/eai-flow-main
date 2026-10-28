"""Document parsers: EN/FR office formats → block trees (EAI-CUSTOM, T3).

设计构件 1/4：电子件 docx/xlsx/pptx 按 block 树抽取；born-digital PDF 直接解析
（PyMuPDF 文本层判定）；扫描件 PDF 与图片抛 OcrRequired → eai-flow-ocr
（POST /ocr，multipart，text_pages=999 全页；Phase 0 仅 .pdf）。

依赖全部复用容器既有库：python-docx / openpyxl / python-pptx / PyMuPDF / httpx。
分流判据（narrative/tabular/mixed）= 样例验证头号待决问题（设计前提 2）——
classify_tag 是 stub：表格块占比 >30% 记 tabular、无表记 narrative、其余 mixed。
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

OCR_BASE_URL = os.environ.get("EAI_OCR_BASE_URL", "http://eai-flow-ocr:8010")

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}
_PDF_MIN_TEXT_CHARS = 32  # born-digital 判定：全文文本层低于此值按扫描件处理（扫描件通常 0-10 字符）


class OcrRequired(Exception):
    """扫描件/图片：文本层不可用，须走 eai-flow-ocr。"""


@dataclass
class Block:
    """解析块（设计构件 1 的 block 树节点；worker 的占位符注册表以此为界）。"""

    id: str
    type: str  # heading | paragraph | table | page_text
    text: str
    meta: dict = field(default_factory=dict)  # page/section/sheet/row/cells

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "text": self.text, "meta": self.meta}


def parse_document(path: str | Path) -> list[Block]:
    """按扩展名路由到对应解析器；图片/无文本层 PDF → OcrRequired。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _IMAGE_EXTS:
        raise OcrRequired(f"image file requires OCR: {p.name}")
    if ext == ".pdf":
        return _parse_pdf(p)
    if ext == ".docx":
        return _parse_docx(p)
    if ext in {".xlsx", ".xlsm"}:
        return _parse_xlsx(p)
    if ext == ".pptx":
        return _parse_pptx(p)
    if ext in {".txt", ".md"}:
        return _parse_text(p)
    raise ValueError(f"unsupported file type for translation: {ext}")


def blocks_text(blocks: list[Block]) -> str:
    return "\n".join(b.text for b in blocks if b.text)


def classify_tag(blocks: list[Block]) -> str | None:
    """内容语义 tag stub（ponytail: 判据=样例验证待决，设计前提 2；样例到手后替换）。"""
    if not blocks:
        return None
    tables = sum(1 for b in blocks if b.type == "table")
    if tables == 0:
        return "narrative"
    if tables / len(blocks) > 0.3:
        return "tabular"
    return "mixed"


# ── docx ──────────────────────────────────────────────────────────────


def _parse_docx(p: Path) -> list[Block]:
    from docx import Document as DocxDocument
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    doc = DocxDocument(str(p))
    blocks: list[Block] = []
    seq = 0

    def _add(btype: str, text: str, **meta) -> None:
        nonlocal seq
        seq += 1
        blocks.append(Block(id=f"b{seq:04d}", type=btype, text=text, meta=meta))

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = DocxParagraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            _add("heading" if para.style.name.startswith("Heading") else "paragraph", text)
        elif tag == "tbl":
            table = DocxTable(child, doc)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            _add("table", "\n".join("\t".join(r) for r in rows), rows=len(rows), cells=rows)
    return blocks


# ── xlsx ──────────────────────────────────────────────────────────────


def _parse_xlsx(p: Path) -> list[Block]:
    import openpyxl

    wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    blocks: list[Block] = []
    seq = 0
    try:
        for ws in wb.worksheets:
            seq += 1
            blocks.append(Block(id=f"b{seq:04d}", type="heading", text=ws.title, meta={"sheet": ws.title}))
            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if any(c.strip() for c in cells):
                    rows.append(cells)
            if rows:
                seq += 1
                blocks.append(
                    Block(
                        id=f"b{seq:04d}",
                        type="table",
                        text="\n".join("\t".join(r) for r in rows),
                        meta={"sheet": ws.title, "rows": len(rows), "cells": rows},
                    )
                )
    finally:
        wb.close()
    return blocks


# ── pptx ──────────────────────────────────────────────────────────────


def _parse_pptx(p: Path) -> list[Block]:
    from pptx import Presentation

    prs = Presentation(str(p))
    blocks: list[Block] = []
    seq = 0
    for idx, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if getattr(shape, "has_table", False):
                rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
                seq += 1
                blocks.append(
                    Block(
                        id=f"b{seq:04d}",
                        type="table",
                        text="\n".join("\t".join(r) for r in rows),
                        meta={"slide": idx, "rows": len(rows), "cells": rows},
                    )
                )
            elif shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    seq += 1
                    blocks.append(Block(id=f"b{seq:04d}", type="paragraph", text=text, meta={"slide": idx}))
    return blocks


# ── pdf ───────────────────────────────────────────────────────────────


def _parse_pdf(p: Path) -> list[Block]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(p))
    blocks: list[Block] = []
    seq = 0
    total_chars = 0
    try:
        for page in doc:
            total_chars += len(page.get_text().strip())
        if total_chars < _PDF_MIN_TEXT_CHARS:
            raise OcrRequired(f"scanned pdf (text layer {total_chars} chars): {p.name}")
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                seq += 1
                blocks.append(Block(id=f"b{seq:04d}", type="page_text", text=text, meta={"page": page_no}))
    finally:
        doc.close()
    return blocks


# ── txt / md ──────────────────────────────────────────────────────────


def _parse_text(p: Path) -> list[Block]:
    text = p.read_text(encoding="utf-8", errors="replace")
    blocks: list[Block] = []
    for i, para in enumerate(text.split("\n\n"), start=1):
        para = para.strip()
        if para:
            blocks.append(Block(id=f"b{i:04d}", type="paragraph", text=para))
    return blocks


# ── OCR（eai-flow-ocr, POST /ocr；PDF 直传，图片先转单页 PDF）────────────

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def _image_to_pdf_bytes(path: Path) -> bytes:
    """图片 → 单页 PDF（OCR 服务 Phase 0 只收 PDF）。"""
    import fitz

    doc = fitz.open(str(path))
    try:
        return doc.convert_to_pdf()
    finally:
        doc.close()


async def ocr_pdf(path: str | Path, text_pages: int = 999) -> list[Block]:
    """扫描件/图片 → eai-flow-ocr 全页 OCR → blocks（text_pages=999 全文语料）。

    端点契约：mcp-server/ocr-service/server.py POST /ocr（multipart file=*.pdf）。
    图片先经 PyMuPDF 转单页 PDF 再上传。失败抛异常由调用方落 failed（R7/SC-3）。
    """
    import httpx

    p = Path(path)
    if p.suffix.lower() in _IMAGE_EXTS:
        payload = _image_to_pdf_bytes(p)
        filename = f"{p.stem}.pdf"
    else:
        payload = p.read_bytes()
        filename = p.name
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{OCR_BASE_URL}/ocr",
            files={"file": (filename, payload, "application/pdf")},
            data={"text_pages": str(text_pages)},
        )
    resp.raise_for_status()
    payload = resp.json()
    blocks: list[Block] = []
    seq = 0
    for page in payload.get("pages", []):
        text = (page.get("text") or "").strip()
        if text:
            seq += 1
            blocks.append(Block(id=f"b{seq:04d}", type="page_text", text=text, meta={"page": page.get("page_no")}))
        for t_idx, table in enumerate(page.get("tables", []) or [], start=1):
            rows = table.get("rows") or []
            if not rows:
                continue
            seq += 1
            blocks.append(
                Block(
                    id=f"b{seq:04d}",
                    type="table",
                    text="\n".join("\t".join(str(c) for c in r) for r in rows),
                    meta={"page": page.get("page_no"), "table": t_idx, "cells": rows},
                )
            )
    return blocks


async def parse_document_with_ocr(path: str | Path) -> tuple[list[Block], bool]:
    """统一入口：电子件直解；扫描件走 OCR。返回 (blocks, used_ocr)。"""
    p = Path(path)
    try:
        return parse_document(p), False
    except OcrRequired:
        if p.suffix.lower() != ".pdf":
            # Phase 0 OCR 服务仅收 .pdf；图片转 PDF 在 worker 阶段处理（T4）
            raise
        return await ocr_pdf(p), True
