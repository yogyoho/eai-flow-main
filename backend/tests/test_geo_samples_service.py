"""服务编排：parse→parsed、redact→redacted、异常→failed+run 落账。"""

import pytest


@pytest.mark.asyncio
async def test_run_parse_happy_path(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r1", file_name="a.docx", file_hash="h", file_type="docx", status="uploaded", raw_uri="s3://geo-samples/raw/r1/a.docx")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _get(db_, did):
        return doc

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"docx-bytes")
    monkeypatch.setattr(service.parsers, "parse_document", AsyncMock(return_value=("# 报告\n正文", "docx")))
    monkeypatch.setattr(service.storage, "put_work", lambda rid, data: f"s3://geo-samples/work/{rid}/parsed.md")

    await service.run_parse(db, "doc-1", run_id="run-1")

    assert doc.status == "parsed"
    assert doc.parse_mode == "docx"
    assert doc.work_uri == "s3://geo-samples/work/r1/parsed.md"


@pytest.mark.asyncio
async def test_run_parse_failure_marks_failed(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r2", file_name="a.pdf", file_hash="h", file_type="pdf", status="uploaded", raw_uri="s3://geo-samples/raw/r2/a.pdf")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _get(db_, did):
        return doc

    async def _boom(*a, **k):
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"x")
    monkeypatch.setattr(service.parsers, "parse_document", _boom)
    monkeypatch.setattr(service.crud, "finish_run", AsyncMock())

    await service.run_parse(db, "doc-2", run_id="run-2")
    assert doc.status == "failed"
    service.crud.finish_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_redact_writes_clean_and_summary(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r3", file_name="a.docx", file_hash="h", file_type="docx", status="parsed", work_uri="s3://geo-samples/work/r3/parsed.md")
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _get(db_, did):
        return doc

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: "证号C5300002023000003 正文".encode())
    monkeypatch.setattr(service.storage, "put_clean", lambda rid, data: f"s3://geo-samples/clean/{rid}/source.md")
    monkeypatch.setattr(service.crud, "add_redactions", AsyncMock())

    await service.run_redact(db, "doc-3", run_id="run-3")

    assert doc.status == "redacted"
    assert doc.redaction_summary is not None and "exploration_cert" in doc.redaction_summary


@pytest.mark.asyncio
async def test_run_parse_survives_finish_run_failure(monkeypatch):
    """⚡调整2 回归：finish_run 记账失败不得改写已提交状态、不得向调用方抛出。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r4", file_name="a.docx", file_hash="h", file_type="docx", status="uploaded", raw_uri="s3://geo-samples/raw/r4/a.docx")
    db = MagicMock()
    db.commit = AsyncMock()

    async def _get(db_, did):
        return doc

    async def _accounting_boom(*a, **k):
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"docx-bytes")
    monkeypatch.setattr(service.parsers, "parse_document", AsyncMock(return_value=("# 报告", "docx")))
    monkeypatch.setattr(service.storage, "put_work", lambda rid, data: f"s3://geo-samples/work/{rid}/parsed.md")
    monkeypatch.setattr(service.crud, "finish_run", _accounting_boom)

    await service.run_parse(db, "doc-4", run_id="run-4")  # 不得抛出
    assert doc.status == "parsed"
