"""Parse a contract file via the eai-flow-ocr HTTP service -> TableExtract list.

The heavy OCR (rapid-layout + rapid-table + rapidocr) lives in the standalone
eai-flow-ocr container; this module just POSTs the file and reshapes the JSON
into TableExtract per detected table. Downstream (table_classifier +
price_validator, called from cli.run_pipeline) decides which tables are
goods/price tables and validates the numbers.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ponytail: retry transient OCR worker crashes (RemoteProtocolError) up to 2
# times with backoff — scanned PDFs can OOM a worker on first pass but a lone
# retry against a fresh worker usually succeeds. 3 total attempts, 30s/60s
# backoff, enough headroom without blowing the per-doc timeout.
_RETRY_MAX = 3
_RETRY_BACKOFF = [30, 60]


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


async def parse_document(file_bytes: bytes, filename: str, ocr_service_url: str, last_pages: int = 0) -> tuple:
    """Call eai-flow-ocr POST /ocr, return (list[TableExtract], page_texts, orientation_fixed).

    page_texts is {page_no: full_page_text} for the first few pages only (the OCR
    service gates full-page text to the cover/front pages). Used downstream to
    regex-extract project-level fields (name/location) that never appear in tables.

    orientation_fixed 是被 OCR 服务页级方向归一化纠偏的页号列表(1-based;parse_meta
    透传,溯源时可提示该页预览/坐标来自纠偏后图像)。

    last_pages > 0 时仅 OCR 末 N 页(元数据兜底用;Task 8 前服务端忽略该字段)。

    Large PDFs take minutes (per-page layout+table+ocr), so the timeout is long.
    """
    url = ocr_service_url.rstrip("/") + "/ocr"
    # 137-page scanned contracts take ~14-16 min of OCR; 900s was too tight
    # (cold-start after a rebuild pushed one run to 15.6min → ReadTimeout with
    # an empty message that looked like a silent failure). 1800s gives margin.
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_MAX + 1):
        try:
            async with httpx.AsyncClient(timeout=1800.0) as client:
                resp = await client.post(
                    url,
                    files={"file": (filename, file_bytes, "application/octet-stream")},
                    data={"last_pages": last_pages} if last_pages else None,
                )
                resp.raise_for_status()
                data = resp.json()
            break  # success — exit retry loop
        except httpx.RemoteProtocolError as exc:
            last_exc = exc
            if attempt < _RETRY_MAX:
                wait = _RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(_RETRY_BACKOFF) else 60
                logger.warning(
                    "OCR server disconnected (attempt %d/%d), retrying in %ds: %s",
                    attempt, _RETRY_MAX, wait, exc,
                )
                await asyncio.sleep(wait)
            else:
                raise

    tables: list[TableExtract] = []
    page_texts: dict[int, str] = {}
    orientation_fixed: list[int] = list(data.get("orientation_fixed_pages", []) or [])
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
    return tables, page_texts, orientation_fixed


def to_cache(tables: list[TableExtract], page_texts: dict[int, str], orientation_fixed=()) -> dict:
    """OCR 结构化结果的缓存形态(剔 preview b64——预览 PNG 本就单独存 MinIO)。"""
    return {
        "v": 1,
        "page_texts": {str(k): v for k, v in page_texts.items()},
        "orientation_fixed_pages": list(orientation_fixed),
        "tables": [
            {
                "page_no": t.page_no,
                "table_idx": t.table_idx,
                "bbox": t.bbox,
                "rows": t.rows,
                "cell_bboxes": t.cell_bboxes,
                "mean_confidence": t.mean_confidence,
            }
            for t in tables
        ],
    }


def from_cache(data: dict) -> tuple:
    """缓存 → (tables, page_texts, orientation_fixed)。preview 恒为空串(缓存命中
    重解析时预览 PNG 在首解析已落 MinIO,preview_prefix 不变)。旧缓存无
    orientation_fixed_pages 键 → 空列表(与无纠偏等价)。"""
    tables = [
        TableExtract(
            page_no=t["page_no"],
            table_idx=t["table_idx"],
            bbox=t.get("bbox", [0, 0, 0, 0]),
            rows=t.get("rows", []),
            cell_bboxes=t.get("cell_bboxes", []),
            page_preview_b64="",
            mean_confidence=float(t.get("mean_confidence", 0.0)),
        )
        for t in data.get("tables", [])
    ]
    page_texts = {int(k): v for k, v in (data.get("page_texts") or {}).items()}
    return tables, page_texts, list(data.get("orientation_fixed_pages", []) or [])
