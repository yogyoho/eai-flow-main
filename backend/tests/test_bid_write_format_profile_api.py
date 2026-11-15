"""FormatProfile 落库与 API:解析后旁路提取、GET 空态、POST 重提取、owner 隔离。"""

from __future__ import annotations

import io

import httpx
import pytest
import pytest_asyncio
from docx import Document
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import parse
from app.extensions.bid_write import crud, models, worker
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA


def _tender_docx() -> bytes:
    document = Document()
    document.add_paragraph("投标文件目录")
    document.add_paragraph("一  投标函")
    document.add_paragraph("一、投标函", style="Heading 1")
    document.add_paragraph("致：________（招标人名称）")
    document.add_paragraph("我方承诺本投标文件真实有效，并承担相应法律责任。")
    document.add_paragraph("第七章 合同条款", style="Heading 1")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                models.WriteTask.__table__,
                models.BidWriteFormatProfile.__table__,
                SA.WorkflowSubjectInstance.__table__,
                SA.WorkflowSubjectReview.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def api_app(db):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    return app


@pytest_asyncio.fixture
async def client(api_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app), base_url="http://t") as http:
        yield http


@pytest.fixture(autouse=True)
def isolated_task_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(parse, "task_dir", lambda owner, task: tmp_path / owner / task)


async def _seed_task(db: AsyncSession, *, with_docx: bool = True) -> models.WriteTask:
    task = await crud.create_task(db, "u1")
    if with_docx:
        entry = parse.save_raw("u1", task.id, "tender", "招标文件.docx", _tender_docx())
    else:
        entry = {"doc_id": "招标文件.pdf", "role": "tender", "kind": "pdf", "slug": "pdf", "status": "raw"}
    task.engine_meta = {"docs": [entry]}
    await db.commit()
    await db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_get_before_extract_returns_null_profile(client, db):
    task = await _seed_task(db)

    response = await client.get(f"/api/extensions/bid-write/tasks/{task.id}/format-profile")

    assert response.status_code == 200
    assert response.json() == {"profile": None, "profile_hash": "", "schema_version": "", "source": None, "updated_at": None}


@pytest.mark.asyncio
async def test_extract_persists_profile_and_get_returns_it(client, db):
    task = await _seed_task(db)

    response = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/format-profile/extract")
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["supported"] is True
    assert payload["profile"]["format_section"]["chapter_count"] == 1
    assert payload["profile_hash"] == payload["profile"]["profile_hash"]
    assert payload["source"]["doc_id"] == "招标文件.docx"

    row = await crud.get_format_profile(db, task.id, "u1")
    assert row is not None and row.profile_hash == payload["profile_hash"]
    assert row.source_sha256 == payload["profile"]["source"]["sha256"]

    fetched = (await client.get(f"/api/extensions/bid-write/tasks/{task.id}/format-profile")).json()
    assert fetched["profile"]["profile_hash"] == payload["profile_hash"]


@pytest.mark.asyncio
async def test_extract_without_docx_returns_422(client, db):
    task = await _seed_task(db, with_docx=False)

    response = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/format-profile/extract")

    assert response.status_code == 422
    assert "DOCX" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_is_not_visible_to_other_owner(client, db, api_app):
    task = await _seed_task(db)
    api_app.dependency_overrides[R.current_owner] = lambda: "u2"

    response = await client.get(f"/api/extensions/bid-write/tasks/{task.id}/format-profile")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_worker_helper_returns_none_when_no_tender_docx(db):
    task = await _seed_task(db, with_docx=False)

    assert await worker.extract_task_format_profiles(db, task, "u1") is None
