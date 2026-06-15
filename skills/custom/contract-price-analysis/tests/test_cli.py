"""End-to-end CLI pipeline tests (RAGFlow + DB mocked)."""

from unittest.mock import AsyncMock, patch

import pytest

from scripts.cli import run_pipeline


@pytest.mark.asyncio
async def test_run_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "k")
    monkeypatch.setenv("CPA_OUTPUT_DIR", str(tmp_path))

    table_chunk = (
        "| 货物名称 | 规格型号 | 数量 | 单位 | 单价(元) |\n"
        "|---|---|---|---|---|\n"
        "| 高压开关柜 | KYN28 | 2 | 台 | 120000 |\n"
        "| 高压开关柜 | KYN28 | 1 | 台 | 130000 |\n"
        "| 变压器 | SCB13 | 1 | 台 | 85000 |"
    )

    fake_docs = [{"id": "d1", "name": "合同1.pdf", "hash": "h1"}]
    fake_chunks = [{"content": table_chunk}]

    with patch("scripts.cli.RagflowClient") as MockClient, \
         patch("scripts.cli.init_schema", new=AsyncMock()), \
         patch("scripts.cli._load_cached_hashes", new=AsyncMock(return_value={})), \
         patch("scripts.cli._persist", new=AsyncMock()) as persist_mock:
        instance = MockClient.return_value
        instance.list_documents = AsyncMock(return_value=fake_docs)
        instance.get_document_chunks = AsyncMock(return_value=fake_chunks)
        instance.filter_changed = staticmethod(lambda docs, cached: docs)
        instance.close = AsyncMock()

        groups = await run_pipeline(mode="table", trigger="manual", client=instance)

    # At least one cluster group produced and Excel written.
    assert isinstance(groups, list)
    assert len(groups) >= 1
    assert persist_mock.await_count == 1
    # Excel file exists in the tmp output dir.
    import os
    assert any(f.endswith(".xlsx") for f in os.listdir(str(tmp_path)))


@pytest.mark.asyncio
async def test_run_pipeline_skips_unchanged_docs(tmp_path, monkeypatch):
    """When cache matches all hashes, nothing is parsed but pipeline still completes."""
    monkeypatch.setenv("RAGFLOW_API_KEY", "k")
    monkeypatch.setenv("CPA_OUTPUT_DIR", str(tmp_path))

    fake_docs = [{"id": "d1", "name": "c.pdf", "hash": "h1"}]

    with patch("scripts.cli.RagflowClient") as MockClient, \
         patch("scripts.cli.init_schema", new=AsyncMock()), \
         patch("scripts.cli._load_cached_hashes", new=AsyncMock(return_value={"d1": "h1"})), \
         patch("scripts.cli._persist", new=AsyncMock()):
        instance = MockClient.return_value
        instance.list_documents = AsyncMock(return_value=fake_docs)
        instance.get_document_chunks = AsyncMock(return_value=[])
        instance.filter_changed = staticmethod(lambda docs, cached: [])  # nothing changed
        instance.close = AsyncMock()

        groups = await run_pipeline(mode="table", client=instance)

    assert groups == []  # no changed docs → no items → no clusters
