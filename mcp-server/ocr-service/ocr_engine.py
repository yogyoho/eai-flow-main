"""Scanned-contract OCR engine v2 — rapid-layout + rapid-table (Phase 0).

Pipeline (replaces the v1 cv2 line-detection path, which mis-detected the
contract's multi-column body text as tables):
  PDF --pdf2image--> page PNG (== traceback preview)
       --rapid-layout--> regions with class_names; keep only 'table' regions
       (this is the fix: cdla layout model distinguishes table vs text, so
       multi-column contract body no longer pollutes results)
       --per table region: crop -> RapidOCR -> rapid-table -> HTML
       --HTML parse--> rows x cells (text + row/col structure)

Why this over cv2: real contracts have multi-column body layouts whose column
rules look exactly like table lines to a line detector. A layout *classifier*
(table vs text) is the only reliable separator. rapid-table then gives accurate
row/col structure that a line detector cannot (it was producing garbage 3-col
rows from body text).

bbox: cell_bboxes are crop-relative; offset by the region's page origin and
normalize to 0~1 vs the FULL page so the traceback overlay lands on the page
preview directly.
"""

from __future__ import annotations

import base64
import io
import time
from html.parser import HTMLParser

import numpy as np
from pdf2image import convert_from_bytes, convert_from_path
from PIL import Image
from rapid_layout import RapidLayout
from rapid_table import RapidTable
from rapidocr_onnxruntime import RapidOCR

from schemas import Cell, OcrResponse, PageResult, Table


class _HtmlTableParser(HTMLParser):
    """Minimal <tr>/<td> extractor (ignores colspan/rowspan — Phase 0 wants
    readable rows, not a perfect grid; regular清单 tables are plain grids)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = ""

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append((self._cell or "").strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c for c in self._row):
                self.rows.append(self._row)
            self._row = None


def _parse_html_rows(html: str) -> list[list[str]]:
    p = _HtmlTableParser()
    p.feed(html or "")
    return p.rows


class OcrEngine:
    def __init__(self) -> None:
        # All three load ONNX models on first use (~2-4s total); lazy so /health
        # and import stay fast.
        self._ocr: RapidOCR | None = None
        self._layout: RapidLayout | None = None
        self._table: RapidTable | None = None

    # --- public ---------------------------------------------------------
    def ocr_pdf_bytes(self, pdf_bytes: bytes, dpi: int = 200, text_pages: int = 3) -> OcrResponse:
        return self._run(convert_from_bytes(pdf_bytes, dpi=dpi), text_pages=text_pages)

    def ocr_pdf_path(self, path: str, dpi: int = 200, text_pages: int = 3) -> OcrResponse:
        return self._run(convert_from_path(path, dpi=dpi), text_pages=text_pages)

    # --- internals ------------------------------------------------------
    def _ensure(self) -> None:
        if self._ocr is None:
            self._layout = RapidLayout()
            self._table = RapidTable()
            self._ocr = RapidOCR()

    def _run(self, pages: list[Image.Image], text_pages: int = 3) -> OcrResponse:
        self._ensure()
        started = time.monotonic()
        out = [
            self._page(idx, img, with_text=idx <= text_pages)
            for idx, img in enumerate(pages, start=1)
        ]
        return OcrResponse(
            pages=out,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            engine="pdf2image+rapid-layout+rapid-table+rapidocr-onnxruntime",
            table_count=sum(len(p.tables) for p in out),
        )

    def _page(self, page_no: int, pil_img: Image.Image, with_text: bool = False) -> PageResult:
        self._ensure()
        arr = np.array(pil_img.convert("RGB"))
        h, w = arr.shape[:2]
        tables: list[Table] = []
        try:
            lout = self._layout(arr)
        except Exception:  # layout failure on one page must not kill the run
            lout = None
        if lout is not None:
            cns = list(getattr(lout, "class_names", []) or [])
            for box, cn in zip(lout.boxes, cns):
                if "table" not in str(cn).lower():
                    continue  # skip text/title/figure — the multi-column body
                t = self._table_region(arr, box, w, h)
                if t is not None:
                    tables.append(t)
        # ponytail: full-page text OCR only for the first few pages — the
        # cover/first pages carry project name/location labels that table
        # crops never see. Gated (idx<=text_pages) because full-page OCR on
        # all 137 pages would roughly double runtime; project info is always
        # near the front.
        text = ""
        if with_text:
            try:
                res, _ = self._ocr(arr)
                if res:
                    text = "\n".join(str(r[1]) for r in res)
            except Exception:
                text = ""
        return PageResult(
            page_no=page_no,
            page_width=w,
            page_height=h,
            tables=tables,
            preview_png_b64=_png_b64(pil_img),
            text=text,
        )

    def _table_region(self, arr: np.ndarray, box, w: int, h: int) -> Table | None:
        x1, y1, x2, y2 = (int(v) for v in box)
        x1, y1 = max(0, x1 - 8), max(0, y1 - 8)
        x2, y2 = min(w, x2 + 8), min(h, y2 + 8)
        crop = arr[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        if cw < 60 or ch < 60:
            return None
        res, _ = self._ocr(crop)
        if not res:
            return None
        boxes = np.array([r[0] for r in res])
        texts = tuple(r[1] for r in res)
        scores = tuple(float(r[2]) for r in res)
        try:
            tout = self._table([crop], ocr_results=[(boxes, texts, scores)])
        except Exception:
            return None
        html = (tout.pred_htmls or [""])[0]
        cbbs = (tout.cell_bboxes or [[]])[0]
        rows_text = _parse_html_rows(html)
        if not rows_text:
            return None

        region_conf = float(np.mean(scores)) if scores else 0.0
        # Build cells. bbox: pair HTML cells (row-major) with cell_bboxes in
        # order — rapid-table emits both row-major, so the flat walk aligns.
        flat_cbbs = list(cbbs) if cbbs is not None else []
        fi = 0
        rows: list[list[Cell]] = []
        for r in rows_text:
            cells: list[Cell] = []
            for txt in r:
                bbox = [0.0, 0.0, 0.0, 0.0]
                if fi < len(flat_cbbs):
                    try:
                        pts = np.array(flat_cbbs[fi], dtype=float).reshape(-1, 2)
                        if pts.shape[0] >= 2:
                            xs, ys = pts[:, 0], pts[:, 1]
                            bbox = [
                                (x1 + xs.min()) / w,
                                (y1 + ys.min()) / h,
                                (x1 + xs.max()) / w,
                                (y1 + ys.max()) / h,
                            ]
                    except Exception:
                        pass
                fi += 1
                cells.append(Cell(text=txt, bbox=bbox, confidence=region_conf))
            rows.append(cells)
        allc = [c for r in rows for c in r]
        return Table(
            bbox=[x1 / w, y1 / h, x2 / w, y2 / h],
            rows=rows,
            row_count=len(rows),
            col_count=max((len(r) for r in rows), default=0),
            mean_confidence=float(np.mean([c.confidence for c in allc])) if allc else 0.0,
        )


def _png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
