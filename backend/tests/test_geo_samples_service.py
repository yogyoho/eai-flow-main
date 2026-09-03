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
    monkeypatch.setattr(service.crud, "get_document_fresh", _get)  # R2 重取改走 populate_existing
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
    monkeypatch.setattr(service.crud, "get_document_fresh", _get)  # P5 ledger A：R2 重取对齐 run_parse
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
    monkeypatch.setattr(service.crud, "get_document_fresh", _get)  # R2 重取改走 populate_existing
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"docx-bytes")
    monkeypatch.setattr(service.parsers, "parse_document", AsyncMock(return_value=("# 报告", "docx")))
    monkeypatch.setattr(service.storage, "put_work", lambda rid, data: f"s3://geo-samples/work/{rid}/parsed.md")
    monkeypatch.setattr(service.crud, "finish_run", _accounting_boom)

    await service.run_parse(db, "doc-4", run_id="run-4")  # 不得抛出
    assert doc.status == "parsed"


@pytest.mark.asyncio
async def test_run_parse_releases_connection_before_heavy_work(monkeypatch):
    """OCR 级重活前必须 commit 释放连接、重活后重取文档（R2）。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r5", file_name="a.pdf", file_hash="h", file_type="pdf", status="uploaded", raw_uri="s3://geo-samples/raw/r5/a.pdf")
    events = []

    async def _get(db_, did):
        events.append("get")
        return doc

    async def _heavy(*a, **k):
        events.append("heavy")
        return "# 报告", "pdf"  # plan 原稿漏了返回值——unpack md, mode 需要真元组，否则任何实现都走 except

    def _get_obj(uri):
        events.append("getobj")
        return b"pdf"

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.crud, "get_document_fresh", _get)  # R2 重取改走 populate_existing
    monkeypatch.setattr(service.storage, "get_object", _get_obj)
    monkeypatch.setattr(service.parsers, "parse_document", _heavy)
    monkeypatch.setattr(service.storage, "put_work", lambda rid, d: f"s3://geo-samples/work/{rid}/parsed.md")
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: events.append("commit"))
    db.refresh = AsyncMock()

    await service.run_parse(db, "doc-5", run_id="run-5")
    assert doc.status == "parsed"
    # 连接释放必须发生在 heavy 之前
    assert events.index("commit") < events.index("heavy")
    # 重活后必须重取文档（P2-T2 quality：普通 get 命中 identity map 看不到改判，须 get_document_fresh）
    assert events.count("get") >= 2


@pytest.mark.asyncio
async def test_run_parse_discards_result_when_doc_state_drifted(monkeypatch):
    """P2-T2 quality：重活后重取见漂移态 → 丢弃解析结果：不写 work_uri、run=failed、doc 状态不被覆盖。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc_initial = GsbDocument(report_id="r7", file_name="a.pdf", file_hash="h", file_type="pdf", status="uploaded", raw_uri="s3://geo-samples/raw/r7/a.pdf")
    doc_drifted = GsbDocument(report_id="r7", file_name="a.pdf", file_hash="h", file_type="pdf", status="redacted", raw_uri="s3://geo-samples/raw/r7/a.pdf")

    async def _get_first(db_, did):
        return doc_initial

    async def _get_fresh(db_, did):
        return doc_drifted

    finish_run = AsyncMock()
    put_work = MagicMock()
    monkeypatch.setattr(service.crud, "get_document", _get_first)
    monkeypatch.setattr(service.crud, "get_document_fresh", _get_fresh)
    monkeypatch.setattr(service.crud, "finish_run", finish_run)
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"pdf")
    monkeypatch.setattr(service.parsers, "parse_document", AsyncMock(return_value=("# md", "pdf")))
    monkeypatch.setattr(service.storage, "put_work", put_work)
    db = MagicMock()
    db.commit = AsyncMock()

    await service.run_parse(db, "doc-7", run_id="run-7")

    assert doc_drifted.status == "redacted"  # 漂移态不被本次解析结果覆盖
    assert doc_initial.status == "uploaded"
    put_work.assert_not_called()
    finish_run.assert_awaited_once_with(db, "run-7", "failed", "document state changed during parse: redacted")


@pytest.mark.asyncio
async def test_get_document_fresh_bypasses_identity_map(tmp_path):
    """真实 DB 回归（P2-T2 quality reviewer 实验）：expire_on_commit=False 下，同 session 普通 get
    命中 identity map 返回旧属性，get_document_fresh（populate_existing）才见他方已提交的改判。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'gsb_fresh.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: GsbDocument.__table__.create(sync_conn, checkfirst=True))
    # 镜像 app/extensions/database.py 会话工厂配置（expire_on_commit=False）
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        doc_id = "doc-fresh-1"
        async with factory() as seed:
            seed.add(GsbDocument(id=doc_id, report_id="rf-1", file_name="a.pdf", file_hash="h", file_type="pdf", status="uploaded"))
            await seed.commit()

        async with factory() as session_a:
            got = await crud.get_document(session_a, doc_id)
            assert got is not None and got.status == "uploaded"
            await session_a.commit()  # 镜像 run_parse：get 后 commit 释放（expire_on_commit=False 保持属性加载）

            async with factory() as session_b:
                other = await crud.get_document(session_b, doc_id)
                assert other is not None
                other.status = "redacted"
                await session_b.commit()

            stale = await crud.get_document(session_a, doc_id)
            assert stale is got  # identity map 命中：同一实例
            assert stale.status == "uploaded"  # 普通 get 看到的是旧值——改判对本会话不可见
            fresh = await crud.get_document_fresh(session_a, doc_id)
            assert fresh is got  # 仍是同一实例，属性被行数据刷新
            assert fresh.status == "redacted"  # populate_existing 见 DB 真值
    finally:
        await engine.dispose()
