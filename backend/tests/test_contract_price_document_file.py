"""合同原文下载端点(GET /documents/{id}/file): 原件流式回传+守卫。"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.extensions.contract_price import storage as cpa_storage
from app.extensions.contract_price.routers import download_document_file


class _StubDB:
    def __init__(self, doc):
        self._doc = doc

    async def get(self, model, doc_id):
        return self._doc


def test_download_streams_original_object(monkeypatch):
    doc = SimpleNamespace(
        storage_uri="s3://cpa-contracts/钢材采购合同-签字版.pdf",
        file_name="钢材采购合同-签字版.pdf",
        file_type="pdf",
    )
    captured = {}

    def fake_get(key):
        captured["key"] = key
        return b"%PDF-1.7 fake"

    monkeypatch.setattr(cpa_storage, "get_object", fake_get)
    resp = asyncio.run(download_document_file(uuid4(), db=_StubDB(doc), _=None))
    assert captured["key"] == "钢材采购合同-签字版.pdf"  # s3:// 前缀已剥离
    assert resp.status_code == 200
    assert resp.media_type == "application/pdf"
    assert resp.body == b"%PDF-1.7 fake"
    disp = resp.headers["content-disposition"]
    assert disp.startswith("attachment;")
    assert "filename*=UTF-8''" in disp and "%E9%92%A2%E6%9D%90" in disp  # CJK 文件名 RFC 5987


def test_download_inline_disposition(monkeypatch):
    """?inline=1 → Content-Disposition inline(浏览器内嵌 PDF 查看器,原文全档可见)。"""
    doc = SimpleNamespace(storage_uri="s3://cpa-contracts/a.pdf", file_name="a.pdf", file_type="pdf")
    monkeypatch.setattr(cpa_storage, "get_object", lambda k: b"%PDF-1.7")
    resp = asyncio.run(download_document_file(uuid4(), inline=True, db=_StubDB(doc), _=None))
    assert resp.headers["content-disposition"].startswith("inline;")


def test_download_404_when_no_storage_uri(monkeypatch):
    monkeypatch.setattr(cpa_storage, "get_object", lambda k: b"x")
    doc = SimpleNamespace(storage_uri=None, file_name="a.pdf", file_type="pdf")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(download_document_file(uuid4(), db=_StubDB(doc), _=None))
    assert exc.value.status_code == 404


def test_download_404_when_object_missing(monkeypatch):
    def boom(key):
        raise RuntimeError("not found")

    monkeypatch.setattr(cpa_storage, "get_object", boom)
    doc = SimpleNamespace(storage_uri="s3://cpa-contracts/a.pdf", file_name="a.pdf", file_type="pdf")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(download_document_file(uuid4(), db=_StubDB(doc), _=None))
    assert exc.value.status_code == 404
