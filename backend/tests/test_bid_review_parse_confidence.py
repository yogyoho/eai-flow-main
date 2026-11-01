"""B3 解析置信(spec §5)纯函数测试:derive_parse_confidence 派生口径。

口径:文档级 confidence = 无损解析字符占比(text/table 直取=无损;ocr 段拉低);
low_conf_pages = OCR 空文本页段(连续合并,置信按 0 记);docx 内嵌图无页边界,
失败张数走 parse_note。非 OCR 引擎自报分数——两个 OCR 通道均不回传分数,不伪造页级数字。
"""

from app.extensions.bid_review.parse import derive_parse_confidence


def _text(text: str, page: int | None = None) -> dict:
    return {"kind": "text", "text": text, "page": page}


def _ocr(text: str, page: int | None) -> dict:
    return {"kind": "ocr", "text": text, "page": page}


def test_pure_text_doc_full_confidence():
    out = derive_parse_confidence([_text("招标要求" * 10, 1), _text("评分办法" * 10, 2)])
    assert out == {"confidence": 1.0, "low_conf_pages": [], "parse_note": None}


def test_mixed_lossless_and_ocr_half():
    segs = [_text("a" * 100, 1), _ocr("b" * 100, 2)]
    out = derive_parse_confidence(segs)
    assert out["confidence"] == 0.5
    assert out["low_conf_pages"] == []  # OCR 有产出 ≠ 低置信页(无分数不伪造)


def test_empty_ocr_pages_merged_into_range():
    segs = [
        _text("x" * 50, 1),
        _ocr("", 3),
        _ocr("", 4),
        _ocr("恢复" * 20, 5),
        _ocr("", 7),
    ]
    out = derive_parse_confidence(segs)
    assert out["low_conf_pages"] == [
        {"page_from": 3, "page_to": 4, "confidence": 0.0, "note": "OCR 未产出文本"},
        {"page_from": 7, "page_to": 7, "confidence": 0.0, "note": "OCR 未产出文本"},
    ]


def test_docx_image_failure_goes_to_note():
    segs = [_text("正文" * 30), _ocr("", None), _ocr("", None)]
    out = derive_parse_confidence(segs)
    assert out["low_conf_pages"] == []
    assert out["parse_note"] == "2 张内嵌图片 OCR 未产出文本"


def test_all_ocr_empty_zero_confidence():
    out = derive_parse_confidence([_ocr("", 1), _ocr("", 2)])
    assert out["confidence"] == 0.0
    assert out["low_conf_pages"][0]["page_from"] == 1
    assert out["low_conf_pages"][0]["page_to"] == 2


def test_no_content_confidence_none():
    out = derive_parse_confidence([])
    assert out["confidence"] is None
