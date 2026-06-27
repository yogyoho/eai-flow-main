"""Parse a contract file via the eai-flow-ocr HTTP service -> TableExtract list.

The heavy OCR (rapid-layout + rapid-table + rapidocr) lives in the standalone
eai-flow-ocr container; this module just POSTs the file and reshapes the JSON
into TableExtract per detected table. Downstream (table_classifier +
price_validator, called from cli.run_pipeline) decides which tables are
goods/price tables and validates the numbers.
"""

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TableExtract:
    page_no: int
    table_idx: int
    bbox: list               # page-relative [x1,y1,x2,y2] normalized 0~1
    rows: list               # list of rows; each row = list of cell text
    cell_bboxes: list        # parallel to rows: rows of cell bbox (0~1 vs page)
    page_preview_b64: str
    mean_confidence: float = 0.0
    extra: dict = field(default_factory=dict)


async def parse_document(file_bytes: bytes, filename: str, ocr_service_url: str) -> tuple:
    """Call eai-flow-ocr POST /ocr, return (list[TableExtract], page_texts).

    page_texts is {page_no: full_page_text} for the first few pages only (the OCR
    service gates full-page text to the cover/front pages). Used downstream to
    regex-extract project-level fields (name/location) that never appear in tables.

    Large PDFs take minutes (per-page layout+table+ocr), so the timeout is long.
    """
    url = ocr_service_url.rstrip("/") + "/ocr"
    async with httpx.AsyncClient(timeout=900.0) as client:
        resp = await client.post(
            url,
            files={"file": (filename, file_bytes, "application/octet-stream")},
        )
        resp.raise_for_status()
        data = resp.json()

    tables: list[TableExtract] = []
    page_texts: dict[int, str] = {}
    for page in data.get("pages", []):
        preview = page.get("preview_png_b64", "")
        page_no = page.get("page_no", 0)
        ptext = page.get("text", "") or ""
        if ptext:
            page_texts[page_no] = ptext
        for ti, t in enumerate(page.get("tables", [])):
            raw_rows = t.get("rows", []) or []
            rows_text = [
                [(c.get("text", "") if isinstance(c, dict) else str(c)) for c in row]
                for row in raw_rows
            ]
            rows_bbox = [
                [
                    (c.get("bbox", [0, 0, 0, 0]) if isinstance(c, dict) else [0, 0, 0, 0])
                    for c in row
                ]
                for row in raw_rows
            ]
            tables.append(
                TableExtract(
                    page_no=page_no,
                    table_idx=ti,
                    bbox=t.get("bbox", [0, 0, 0, 0]),
                    rows=rows_text,
                    cell_bboxes=rows_bbox,
                    page_preview_b64=preview,
                    mean_confidence=float(t.get("mean_confidence", 0.0)),
                )
            )
    return tables, page_texts
