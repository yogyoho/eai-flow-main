"""eai-flow-ocr — FastAPI service wrapping OcrEngine.

Consumed by the contract_price gateway extension and the
contract-price-analysis skill over HTTP. The gateway never imports OCR deps;
it just POSTs a PDF here and gets structured tables + bboxes + confidence +
page previews back.

Endpoints:
  GET  /health   — liveness (no model load)
  POST /ocr      — multipart PDF upload -> OcrResponse
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from ocr_engine import OcrEngine
from schemas import OcrResponse

logger = logging.getLogger("eai-flow-ocr")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="eai-flow-ocr", version="0.1.0")
_engine: OcrEngine | None = None


def _get_engine() -> OcrEngine:
    global _engine
    if _engine is None:
        logger.info("Initializing OcrEngine (first request; loads ONNX models ~2s)...")
        _engine = OcrEngine()
    return _engine


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "eai-flow-ocr"}


@app.post("/ocr", response_model=OcrResponse)
async def ocr(file: UploadFile = File(...), text_pages: int = Form(3)) -> OcrResponse:
    """text_pages: 前多少页做整页文字 OCR（默认 3，沿用 contract_price 行为）。
    EAI-CUSTOM: geo-sample-bank 需全文语料，POST data 里传 text_pages=999 即全页。"""
    name = (file.filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported in Phase 0")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    try:
        return _get_engine().ocr_pdf_bytes(data, text_pages=text_pages)
    except Exception as exc:  # surface reason, never silent
        logger.exception("OCR failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"ocr failed: {exc!r}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("OCR_HOST", "0.0.0.0"),
        port=int(os.environ.get("OCR_PORT", "8010")),
    )
