"""三分支解析：docx→md（含 OLE 占位）、pdf 文字版、扫描判定异常。"""

import io

import pytest


def _build_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("第1章 总论", level=1)
    doc.add_paragraph("本矿区位于云南省。")
    doc.add_heading("1.1 编制依据", level=2)
    doc.add_paragraph("依据DZ/T 0214-2020。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "矿体编号"
    table.cell(0, 1).text = "品位%"
    table.cell(1, 0).text = "Ⅰ号"
    table.cell(1, 1).text = "0.85"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_to_markdown_structure():
    from app.extensions.geo_samples.parsers import docx_to_markdown

    md = docx_to_markdown(_build_docx())
    assert md.startswith("## 第1章 总论")
    assert "### 1.1 编制依据" in md
    assert "| 矿体编号 | 品位% |" in md
    assert "| --- | --- |" in md
    assert "| Ⅰ号 | 0.85 |" in md


def test_docx_ole_formula_placeholder():
    """段落含 OLE 对象（公式）且无文本 → [公式:pN] 占位。"""
    from docx import Document
    from docx.oxml.ns import qn

    from app.extensions.geo_samples.parsers import docx_to_markdown

    doc = Document()
    p = doc.add_paragraph()
    p._p.append(p._p.makeelement(qn("w:object"), {}))
    buf = io.BytesIO()
    doc.save(buf)
    assert "[公式:p1]" in docx_to_markdown(buf.getvalue())


def test_pdf_scan_detection_raises():
    from app.extensions.geo_samples.parsers import ScannedPdfError, pdf_text_to_markdown

    # 1 页几乎无文本 → 判定扫描件
    fake_pdf = _make_pdf_with_text("仅几个字")
    with pytest.raises(ScannedPdfError):
        pdf_text_to_markdown(fake_pdf)


def _make_pdf_with_text(text: str) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def test_ocr_dispatch_contracts(monkeypatch):
    from app.extensions.geo_samples import parsers

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"pages": [{"page_no": 1, "text": "OCR 第一页"}, {"page_no": 2, "text": "OCR 第二页"}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, files=None):
            captured["url"] = url
            captured["files"] = files
            return FakeResp()

    monkeypatch.setattr(parsers.httpx, "AsyncClient", FakeClient)

    import asyncio

    md = asyncio.run(parsers.ocr_pdf_to_markdown(b"pdfbytes"))
    assert "http" in captured["url"] and captured["url"].endswith("/ocr")
    assert "OCR 第一页" in md and "OCR 第二页" in md
