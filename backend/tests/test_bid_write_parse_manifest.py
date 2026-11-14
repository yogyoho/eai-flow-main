"""Regression: parsed manifest entries must reach docs_from_entries.

parse_raw returns the updated entry instead of mutating it. If advance drops
that return value, docs_from_entries still sees status=raw, skips every
document, and the model receives an empty prompt (observed as a 0-row matrix).
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent))

from app.extensions.bid_write import crud, models, worker
from app.extensions.bid_write import routers as R
from app.extensions.database import Base


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.WriteTask.__table__,
                models.MatrixRow.__table__,
                R._SkillRun.__table__,
                models.MaterialEntity.__table__,
                models.MaterialProfile.__table__,
                models.BidWritePolicy.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_advance_persists_parsed_manifest_before_extract(db, monkeypatch):
    from app.extensions.bid_review import parse

    task = await crud.create_task(db, "u1")
    meta = dict(task.engine_meta or {})
    meta["docs"] = [{"doc_id": "t.docx", "role": "tender", "kind": "docx", "slug": "t", "status": "raw", "chars": 0, "pages": 0}]
    task.engine_meta = meta
    await db.commit()

    seen = {}

    async def fake_ocr(_db):
        return None

    async def fake_parse_raw(_owner, _task_id, entry, _ocr_fn):
        return {**entry, "status": "parsed", "chars": 42, "pages": 3}

    def fake_docs_from_entries(_owner, _task_id, entries):
        seen["entries"] = [dict(entry) for entry in entries]
        return [{"doc_id": "t.docx", "role": "tender", "text": "full text"}]

    monkeypatch.setattr(parse, "build_ocr_fn", fake_ocr)
    monkeypatch.setattr(parse, "parse_raw", fake_parse_raw)
    monkeypatch.setattr(parse, "docs_from_entries", fake_docs_from_entries)

    def extract(docs, _field_paths):
        seen["docs"] = docs
        return {"fields": {"tender.required_validity_days": 90}, "provenance": {}, "confidence": {}}

    out = await worker.advance_write_task(db, task.id, "u1", extract_fn=extract)

    assert out.status == "matrix_ready"
    assert seen["entries"][0]["status"] == "parsed"
    assert seen["docs"] == [{"doc_id": "t.docx", "role": "tender", "text": "full text"}]
    stored = await crud.get_task(db, task.id, "u1")
    assert stored.engine_meta["docs"][0]["status"] == "parsed"
    assert stored.engine_meta["docs"][0]["chars"] == 42
