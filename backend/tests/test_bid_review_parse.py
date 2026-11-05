"""bid_review 解析层测试(EAI-CUSTOM 2026-10-30,spec §2/§4.1)。

覆盖:raw 落盘清单、docx 流序解析+图片 OCR 原位插回、pdf 真页码+扫描页 OCR、
text 切段、OCR 失败隔离(空文本占位不炸任务)、docs_from_entries 全文拼回、
excerpt_window 窗口边界。task_dir monkeypatch 到 tmp_path,不碰真实存储。
"""

import base64
import io

import pytest

from app.extensions.bid_review import parse

# 1x1 PNG(最小合法图片,python-docx add_picture 可收)
_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(parse, "task_dir", lambda owner, task: tmp_path / owner / task)
    return tmp_path / "u1" / "t1"


@pytest.fixture()
def ocr_ok():
    async def _fn(name: str, data: bytes, mime: str) -> str:
        return f"OCR[{name}]"

    return _fn


def _make_docx() -> bytes:
    import docx as docx_lib

    d = docx_lib.Document()
    d.add_paragraph("第一段正文")
    d.add_picture(io.BytesIO(_PNG))
    d.add_paragraph("第二段正文")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _make_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "hello pdf page one")
    doc.new_page()  # 空文本层页 → 扫描页
    return doc.tobytes()


@pytest.mark.asyncio
async def test_text_roundtrip_and_windows(base, ocr_ok):
    entry = parse.save_raw("u1", "t1", "tender", "t.txt", b"line1\nline2")
    assert entry["status"] == "raw" and entry["kind"] == "text" and entry["slug"]
    assert (base / "raw" / f"{entry['slug']}.bin").read_bytes() == b"line1\nline2"

    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    assert out["status"] == "parsed" and out["chars"] == len("line1\nline2") and out["pages"] == 0

    segs = parse.load_segments("u1", "t1", entry["slug"])
    assert [s["kind"] for s in segs] == ["text"] and segs[0]["page"] is None
    assert parse.docs_from_entries("u1", "t1", [out]) == [{"doc_id": "t.txt", "role": "tender", "text": "line1\nline2"}]

    # excerpt_window:命中段 ±N,首尾夹取
    many = [{"seq": i, "page": None, "kind": "text", "text": str(i), "asset_id": None} for i in range(30)]
    win = parse.excerpt_window(many, 0)
    assert win[0]["seq"] == 0 and len(win) == 11
    assert parse.excerpt_window(many, 15)[0]["seq"] == 5 and parse.excerpt_window(many, 15)[-1]["seq"] == 25


@pytest.mark.asyncio
async def test_docx_flow_order_and_image_ocr(base, ocr_ok):
    entry = parse.save_raw("u1", "t1", "bid", "bid.docx", _make_docx())
    assert entry["kind"] == "docx"
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    assert out["status"] == "parsed" and out["assets"] == 1 and out["pages"] == 0  # D8:docx 无页码

    segs = parse.load_segments("u1", "t1", entry["slug"])
    assert [s["kind"] for s in segs] == ["text", "ocr", "text"]  # 图按原位插回流序
    assert segs[0]["text"] == "第一段正文" and segs[1]["text"].startswith("OCR[asset-")
    assert segs[1]["page"] is None and segs[1]["asset_id"]
    asset_file = next((base / "assets").iterdir())
    assert asset_file.stem == segs[1]["asset_id"]


@pytest.mark.asyncio
async def test_pdf_real_pages_and_scanned_ocr(base, ocr_ok):
    entry = parse.save_raw("u1", "t1", "tender", "t.pdf", _make_pdf())
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    assert out["pages"] == 2 and out["assets"] == 1

    segs = parse.load_segments("u1", "t1", entry["slug"])
    assert segs[0]["kind"] == "text" and segs[0]["page"] == 1 and "hello pdf" in segs[0]["text"]
    assert segs[1]["kind"] == "ocr" and segs[1]["page"] == 2 and segs[1]["asset_id"]  # 扫描页真页码保留


@pytest.mark.asyncio
async def test_ocr_failure_isolated_not_fatal(base):
    """单图 OCR 失败(返回 "")→ 空文本 segment 占位,任务照常 parsed。"""

    async def bad_ocr(name: str, data: bytes, mime: str) -> str:
        return ""

    entry = parse.save_raw("u1", "t1", "bid", "b.docx", _make_docx())
    out = await parse.parse_raw("u1", "t1", entry, bad_ocr)
    assert out["status"] == "parsed"
    segs = parse.load_segments("u1", "t1", entry["slug"])
    assert segs[1]["kind"] == "ocr" and segs[1]["text"] == "" and segs[1]["asset_id"]


@pytest.mark.asyncio
async def test_build_ocr_fn_builtin_fallback(monkeypatch):
    """default_ocr_engine 解析不出(builtin/未配置)→ 内建 eai-flow-ocr callable。"""
    from app.extensions import ocr_resolve

    async def none_entry(db):
        return None

    monkeypatch.setattr(ocr_resolve, "resolve_default_ocr_entry", none_entry)
    fn = await parse.build_ocr_fn(None)
    assert fn is parse._ocr_builtin


@pytest.mark.asyncio
async def test_docs_from_entries_page_markers_and_sharding(base, ocr_ok):
    """抽取 v2(EAI-CUSTOM 2026-10-30):pdf 段带 [[p.N]] 标记(provenance.page 锚点);
    超 shard_chars 按 segment 边界切成同 doc_id 多片段;docx 无页不插标记(D8)。"""
    entry = parse.save_raw("u1", "t1", "tender", "t.pdf", _make_pdf())
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    pieces = parse.docs_from_entries("u1", "t1", [out], shard_chars=40)
    assert len(pieces) >= 2 and all(p["doc_id"] == "t.pdf" for p in pieces)
    assert "[[p.1]]" in pieces[0]["text"]  # pdf 真页码标记

    # docx:无页码 → 无标记,单段小文档不切
    entry2 = parse.save_raw("u1", "t1", "bid", "b.docx", _make_docx())
    out2 = await parse.parse_raw("u1", "t1", entry2, ocr_ok)
    pieces2 = parse.docs_from_entries("u1", "t1", [out2])
    assert len(pieces2) == 1 and "[[p." not in pieces2[0]["text"]


def _make_docx_table() -> bytes:
    import docx as docx_lib

    d = docx_lib.Document()
    d.add_paragraph("表前段落")
    tbl = d.add_table(rows=2, cols=3)
    tbl.cell(0, 0).text = "项目"
    tbl.cell(0, 1).text = "招标"
    tbl.cell(0, 2).text = "投标"
    tbl.cell(1, 0).text = "工期"
    tbl.cell(1, 1).text = "180天"
    tbl.cell(1, 2).text = "150天\n换行归一"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_table_rows_structured(base, ocr_ok):
    """对齐审计④(2026-11-05):docx 表格不再只有 |a|b| 拍平文本——块与 seg 带 rows
    二维数组;text 键原样保留,模型通路零改动。"""
    data = _make_docx_table()
    blocks = parse._parse_docx_sync(data)
    table = next(b for b in blocks if b["kind"] == "table")
    assert table["rows"] == [["项目", "招标", "投标"], ["工期", "180天", "150天 换行归一"]]
    assert table["text"].startswith("| 项目 | 招标 | 投标 |"), "文本键原样兼容"

    entry = parse.save_raw("u1", "t-tbl", "bid", "b.docx", data)
    await parse.parse_raw("u1", "t-tbl", entry, ocr_ok)
    seg = next(s for s in parse.load_segments("u1", "t-tbl", entry["slug"]) if s["kind"] == "table")
    assert seg["rows"][1] == ["工期", "180天", "150天 换行归一"]


def test_detect_kind_xlsx_and_image():
    """对齐审计⑤⑦(2026-11-05):新入口探测——xlsx 与图片扩展名。"""
    assert parse.detect_kind("报价表.xlsx") == "xlsx"
    assert parse.detect_kind("scan.PDF") == "pdf"
    assert parse.detect_kind("stamp.png") == "image"
    assert parse.detect_kind("stamp.JPG") == "image"
    assert parse.detect_kind("notes.txt") == "text"
    assert parse.detect_kind("noext") == "text"


@pytest.mark.asyncio
async def test_xlsx_sheets_to_table_blocks(base, ocr_ok):
    """对齐审计⑤(2026-11-05):xlsx 每 sheet 一个 table 块(rows 双键同 docx 表);
    sheet 名注记进 text 首行。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "报价"
    ws.append(["项目", "金额"])
    ws.append(["设备", "100万"])
    ws2 = wb.create_sheet("备注")
    ws2.append(["只有一行"])
    buf = io.BytesIO()
    wb.save(buf)

    entry = parse.save_raw("u1", "t-xlsx", "bid", "报价表.xlsx", buf.getvalue())
    assert entry["kind"] == "xlsx"
    out = await parse.parse_raw("u1", "t-xlsx", entry, ocr_ok)
    assert out["status"] == "parsed" and out["assets"] == 0 and out["pages"] == 0
    segs = [s for s in parse.load_segments("u1", "t-xlsx", entry["slug"]) if s["kind"] == "table"]
    assert len(segs) == 2
    assert segs[0]["rows"] == [["项目", "金额"], ["设备", "100万"]]
    assert segs[0]["text"].startswith("[sheet: 报价]")
    assert segs[1]["rows"] == [["只有一行"]]


@pytest.mark.asyncio
async def test_xlsx_row_cap_truncates():
    """500 行/sheet 上限:截断不炸,rows 长度=500(超大清单防 blocks 膨胀)。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for i in range(600):
        ws.append([str(i)])
    buf = io.BytesIO()
    wb.save(buf)
    blocks = parse._parse_xlsx_sync(buf.getvalue())
    assert len(blocks) == 1 and len(blocks[0]["rows"]) == parse._XLSX_MAX_ROWS


@pytest.mark.asyncio
async def test_image_upload_ocrs_to_segment(base, ocr_ok):
    """对齐审计⑦(2026-11-05):独立图片直传 → OCR 文本段 + asset 落盘。"""
    entry = parse.save_raw("u1", "t-img", "bid", "stamp.png", _PNG)
    assert entry["kind"] == "image"
    out = await parse.parse_raw("u1", "t-img", entry, ocr_ok)
    assert out["status"] == "parsed" and out["assets"] == 1
    segs = parse.load_segments("u1", "t-img", entry["slug"])
    assert segs[0]["kind"] == "ocr" and segs[0]["text"].startswith("OCR[asset-")
    assert segs[0]["source"] is None  # 独立直传无 zip 成员名,伪零(None)非空串


@pytest.mark.asyncio
async def test_zip_embedded_image_ocr_seg_has_source(monkeypatch, base, ocr_ok):
    """挂账小件包②(2026-11-05):zip 内 docx 嵌图的 OCR seg 补 source=成员名,
    与 text/table seg 对称——asset 级溯源缺了成员名,证据锚就断在包层面。"""
    import zipfile

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("docs/盖章页.docx", _make_docx())
    entry = parse.save_raw("u1", "t-zipimg", "bid", "附件包.zip", zbuf.getvalue())
    out = await parse.parse_raw("u1", "t-zipimg", entry, ocr_ok)
    assert out["status"] == "parsed"
    segs = parse.load_segments("u1", "t-zipimg", entry["slug"])
    ocr = next(s for s in segs if s["kind"] == "ocr")
    assert ocr["source"] == "docs/盖章页.docx" and ocr["asset_id"]


@pytest.mark.asyncio
async def test_zip_members_parsed_with_source(monkeypatch, base, ocr_ok):
    """对齐审计⑥(2026-11-05):zip 材料包逐成员解析——文本/xlsx 各自成段,
    seg.source 锚定成员名;zip-slip/文件数/解压总量/嵌套 zip 一律拒绝。"""
    import zipfile

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["项目", "金额"])
    ws.append(["设备", "100万"])
    xbuf = io.BytesIO()
    wb.save(xbuf)
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("docs/说明.txt", "投标说明正文")
        zf.writestr("docs/报价.xlsx", xbuf.getvalue())
    entry = parse.save_raw("u1", "t-zip", "bid", "材料包.zip", zbuf.getvalue())
    assert entry["kind"] == "zip"
    out = await parse.parse_raw("u1", "t-zip", entry, ocr_ok)
    assert out["status"] == "parsed"
    segs = parse.load_segments("u1", "t-zip", entry["slug"])
    txt = next(s for s in segs if s["kind"] == "text")
    tbl = next(s for s in segs if s["kind"] == "table")
    assert txt["text"] == "投标说明正文" and txt["source"] == "docs/说明.txt"
    assert tbl["rows"][1] == ["设备", "100万"] and tbl["source"] == "docs/报价.xlsx"

    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ValueError, match="不安全路径"):
        parse._unzip_blocks(evil.getvalue())
    many = io.BytesIO()
    with zipfile.ZipFile(many, "w") as zf:
        for i in range(21):
            zf.writestr(f"f{i}.txt", "x")
    with pytest.raises(ValueError, match="超上限"):
        parse._unzip_blocks(many.getvalue())
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as zf:
        zf.writestr("inner.zip", zbuf.getvalue())
    with pytest.raises(ValueError, match="嵌套"):
        parse._unzip_blocks(nested.getvalue())
    monkeypatch.setattr(parse, "_ZIP_MAX_UNCOMPRESSED", 10)
    small = io.BytesIO()
    with zipfile.ZipFile(small, "w") as zf:
        zf.writestr("a.txt", "x" * 100)
    with pytest.raises(ValueError, match="超上限"):
        parse._unzip_blocks(small.getvalue())
