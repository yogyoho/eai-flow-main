"""OCR 缓存序列化往返 + 缓存命中跳过 OCR 调用。"""

import json

from scripts.document_parser import TableExtract, from_cache, to_cache


def _tbl(page_no=1, table_idx=0):
    return TableExtract(
        page_no=page_no, table_idx=table_idx, bbox=[0.1, 0.1, 0.9, 0.9],
        rows=[["序号", "品名"], ["1", "盘圆"]],
        cell_bboxes=[[[0, 0, 0, 0], [0, 0, 0, 0]], [[0, 0, 0, 0], [0, 0, 0, 0]]],
        page_preview_b64="", mean_confidence=0.93,
    )


def test_cache_roundtrip_preserves_tables_and_texts():
    tables = [_tbl(), _tbl(page_no=2)]
    page_texts = {1: "合同封面", 2: "含税总价"}
    data = json.loads(json.dumps(to_cache(tables, page_texts, [2])))  # JSON 严进严出
    t2, p2, fixed = from_cache(data)
    assert [(t.page_no, t.table_idx, t.rows, t.mean_confidence, t.bbox, t.cell_bboxes) for t in t2] == [
        (t.page_no, t.table_idx, t.rows, t.mean_confidence, t.bbox, t.cell_bboxes) for t in tables
    ]
    assert p2 == page_texts
    assert fixed == [2]  # 纠偏页号随缓存往返
    assert all(t.page_preview_b64 == "" for t in t2)  # preview 不入缓存(单独存PNG)


def test_get_ocr_cache_rejects_non_dict_json(monkeypatch):
    """合法 JSON 但非 dict(如 "[1,2]")→ None:否则 from_cache 崩溃 → 文档误标 failed,
    而非静默回退全量 OCR。不实例化 ContractStore(构造函数连 MinIO),只测方法本体。"""
    from scripts.storage import ContractStore

    class FakeRaw:
        def get(self, key):
            return b"[1,2]"

    assert ContractStore.get_ocr_cache(FakeRaw(), "ocr/x.json") is None


def test_process_one_doc_cache_hit_skips_ocr(monkeypatch):
    """缓存命中: 不发 HTTP,直接从缓存重建 tables;re_ocr=True 强制重 OCR。"""
    import asyncio
    from types import SimpleNamespace

    import scripts.cli as cli
    from scripts.seed_library import DEFAULT_TABLE_SEEDS

    calls = {"ocr": 0}

    async def fake_parse(file_bytes, filename, url):
        calls["ocr"] += 1
        return [_tbl()], {1: "text"}, []

    monkeypatch.setattr(cli, "parse_document", fake_parse)

    class FakeStore:
        def __init__(self):
            self.blobs = {}

        def get_ocr_cache(self, key):
            return self.blobs.get(key)

        def put_ocr_cache(self, key, obj):
            self.blobs[key] = obj

        def get(self, key):
            return b"%PDF-fake"

        def put_preview(self, doc_id, page_no, png_bytes):
            return f"previews/{doc_id}/"

    store = FakeStore()
    sem = asyncio.Semaphore(1)
    ch = {"key": "a.pdf", "hash": "abc", "size": 9}
    cfg = SimpleNamespace(minio_bucket="b", ocr_service_url="http://x")
    base_state = lambda: {"docs_processed": 0, "items_extracted": 0, "failed_docs": 0, "done": 0, "processing": set()}
    # 第一遍: OCR 并写缓存
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, base_state(), None, 1, re_ocr=False))
    assert calls["ocr"] == 1
    assert store.blobs["ocr/abc.json"]
    # 第二遍: 命中缓存,不再 OCR
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, base_state(), None, 1, re_ocr=False))
    assert calls["ocr"] == 1
    # re_ocr=True: 强制重 OCR
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, base_state(), None, 1, re_ocr=True))
    assert calls["ocr"] == 2
