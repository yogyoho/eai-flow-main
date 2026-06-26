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


class PageResult(BaseModel):
    page_no: int  # 1-based
    page_width: int
    page_height: int
    tables: list[Table]
    preview_png_b64: str = ""  # page render; == traceback preview asset


class OcrResponse(BaseModel):
    pages: list[PageResult]
    elapsed_ms: int
    engine: str
    table_count: int
