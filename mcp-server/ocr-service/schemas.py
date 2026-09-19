"""Request/response models for the eai-flow-ocr service.

All bboxes are normalized to 0~1 relative to the FULL page (not the table
crop), so the contract-price traceback UI can overlay them directly on the
page preview PNG without knowing crop offsets.
"""

from pydantic import BaseModel


class Cell(BaseModel):
    text: str = ""
    bbox: list[float]  # [x1, y1, x2, y2], normalized 0~1 vs page
    confidence: float = 0.0


class Table(BaseModel):
    bbox: list[float]  # table region in page, normalized 0~1
    rows: list[list[Cell]]
    row_count: int
    col_count: int
    mean_confidence: float = 0.0
    # P1 几何层(spec 2026-09-19 §2.1): per-crop 行级 OCR token 透出。
    # [{text, box:[x1,y1,x2,y2](页绝对像素,crop 原点偏移), score}];下游
    # document_parser 按页宽高归一化 0~1 后随 OCR 缓存 v2 落盘。
    tokens: list = []


class PageResult(BaseModel):
    page_no: int  # 1-based
    page_width: int
    page_height: int
    tables: list[Table]
    preview_png_b64: str = ""  # page render; == traceback preview asset
    text: str = ""  # full-page OCR text (first N pages only); project fields source
    orientation: str | None = None  # None|"cw90"|"ccw90" 该页OCR所用方向(纠偏后)


class OcrResponse(BaseModel):
    pages: list[PageResult]
    elapsed_ms: int
    engine: str
    table_count: int
    orientation_fixed_pages: list[int] = []  # 被纠偏的页号(1-based,parse_meta透传)
