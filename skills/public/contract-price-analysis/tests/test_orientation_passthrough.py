"""orientation_fixed_pages 透传链: HTTP JSON→3元组→缓存→parse_meta。"""

import asyncio
import json

from scripts.document_parser import TableExtract, from_cache, to_cache


def _fake_client(payload: dict):
    """Build an httpx.AsyncClient stand-in whose POST always returns payload."""

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    return FakeClient


def test_parse_document_reads_orientation_field(monkeypatch):
    """HTTP 响应里的 orientation_fixed_pages 必须出现在第3个返回值。"""
    import scripts.document_parser as dp

    payload = {
        "pages": [
            {"page_no": 2, "preview_png_b64": "", "text": "",
             "tables": [{"rows": [[{"text": "序号", "bbox": [0, 0, 0, 0]}]],
                         "bbox": [0, 0, 0, 0], "mean_confidence": 0.9}]},
            {"page_no": 1, "preview_png_b64": "", "text": "封面", "tables": []},
        ],
        "orientation_fixed_pages": [2],
    }
    monkeypatch.setattr(dp.httpx, "AsyncClient", _fake_client(payload))

    tables, texts, fixed = asyncio.run(dp.parse_document(b"x", "a.pdf", "http://x"))
    assert fixed == [2]
    assert tables[0].page_no == 2


def test_parse_document_defaults_empty_when_field_absent(monkeypatch):
    """旧引擎响应无 orientation_fixed_pages 键 → 空列表(不崩)。"""
    import scripts.document_parser as dp

    payload = {"pages": [{"page_no": 1, "preview_png_b64": "", "text": "", "tables": []}]}
    monkeypatch.setattr(dp.httpx, "AsyncClient", _fake_client(payload))

    _, _, fixed = asyncio.run(dp.parse_document(b"x", "a.pdf", "http://x"))
    assert fixed == []


def test_cache_carries_orientation():
    tables = [TableExtract(page_no=2, table_idx=0, bbox=[0, 0, 0, 0], rows=[["a"]],
                           cell_bboxes=[[[0, 0, 0, 0]]], page_preview_b64="", mean_confidence=0.9)]
    data = json.loads(json.dumps(to_cache(tables, {1: "t"}, [2, 3])))
    _, _, fixed = from_cache(data)
    assert fixed == [2, 3]


def test_cache_roundtrip_old_payload_without_field():
    """旧缓存(v1 无 orientation_fixed_pages 键)→ from_cache 返回空列表。"""
    legacy = {
        "v": 1,
        "page_texts": {"1": "封面"},
        "tables": [
            {"page_no": 1, "table_idx": 0, "bbox": [0, 0, 0, 0], "rows": [["a"]],
             "cell_bboxes": [[[0, 0, 0, 0]]], "mean_confidence": 0.9}
        ],
    }
    tables, texts, fixed = from_cache(legacy)
    assert fixed == []
    assert tables[0].page_no == 1
    assert texts == {1: "封面"}


def test_cli_meta_carries_orientation_fixed(monkeypatch):
    """cli._process_one_doc: parse_document 第3返回值必须进 parse_meta。"""
    from types import SimpleNamespace

    import scripts.cli as cli
    from scripts.seed_library import DEFAULT_TABLE_SEEDS

    def _tbl(page_no=2):
        return TableExtract(
            page_no=page_no, table_idx=0, bbox=[0.1, 0.1, 0.9, 0.9],
            rows=[["序号", "品名"], ["1", "盘圆"]],
            cell_bboxes=[[[0, 0, 0, 0], [0, 0, 0, 0]], [[0, 0, 0, 0], [0, 0, 0, 0]]],
            page_preview_b64="", mean_confidence=0.93,
        )

    async def fake_parse(file_bytes, filename, url, last_pages=0):
        return [_tbl()], {1: "项目名称：某工程"}, [2, 3]

    captured: dict = {}

    async def spy_persist(doc, items, run_id=None):
        captured["parse_meta"] = doc.get("parse_meta")

    monkeypatch.setattr(cli, "parse_document", fake_parse)
    monkeypatch.setattr(cli, "_persist_one_doc", spy_persist)

    class FakeStore:
        def get_ocr_cache(self, key):
            return None

        def put_ocr_cache(self, key, obj):
            pass

        def get(self, key):
            return b"%PDF-fake"

        def put_preview(self, doc_id, page_no, png_bytes):
            return f"previews/{doc_id}/"

    state = {"docs_processed": 0, "items_extracted": 0, "failed_docs": 0, "done": 0, "processing": set()}
    ch = {"key": "a.pdf", "hash": "abc", "size": 9}
    cfg = SimpleNamespace(minio_bucket="b", ocr_service_url="http://x")
    asyncio.run(cli._process_one_doc(ch, FakeStore(), cfg, DEFAULT_TABLE_SEEDS,
                                     asyncio.Semaphore(1), state, None, 1, re_ocr=False))
    assert captured.get("parse_meta", {}).get("orientation_fixed_pages") == [2, 3]
