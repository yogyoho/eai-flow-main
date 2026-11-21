"""Task-level lifecycle transitions for the bid-write delivery flow."""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import approval, crud, models, schemas
from app.extensions.bid_write import export as export_module
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA

AST = {"type": "doc", "content": []}


def _gate() -> dict:
    return {
        "blocked": False,
        "reasons": [],
        "watermark": None,
        "assertion_counts": {"PASS": 1},
        "rule_counts": {"FAIL": 0},
        "l1_fatal_fail": [],
        "l4": None,
        "scope_note": "test",
        "schema_version": "0.1.0",
        "results": [],
    }


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        models.WriteTask.__table__,
        models.MatrixRow.__table__,
        models.MaterialEntity.__table__,
        models.MaterialProfile.__table__,
        models.BidWritePolicy.__table__,
        models.TaskDocument.__table__,
        models.BidWriteDocumentRevision.__table__,
        models.BidWriteFormatProfile.__table__,
        models.BidWriteRevisionFormatProfile.__table__,
        models.BidWriteExport.__table__,
        SA.WorkflowSubjectInstance.__table__,
        SA.WorkflowSubjectReview.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _client_as(db, user_id: str):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest_asyncio.fixture
async def owner_client(db):
    async with _client_as(db, "u1") as client:
        yield client


async def _submit(owner_client, task_id: str):
    return await owner_client.post(
        f"/api/extensions/bid-write/tasks/{task_id}/approval/submit",
        json={"ast": AST, "schema_version": "0.1.0", "reviewer_ids": ["u2"]},
    )


async def _decide(db, task_id: str, action: str):
    async with _client_as(db, "u2") as reviewer:
        state = await reviewer.get(f"/api/extensions/bid-write/tasks/{task_id}/approval")
        assert state.status_code == 200, state.text
        instance_id = state.json()["approval"]["instance_id"]
        acted = await reviewer.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": action},
        )
        assert acted.status_code == 200, acted.text


@pytest.mark.asyncio
async def test_new_task_defaults_to_active_and_api_exposes_lifecycle(db, owner_client):
    task = await crud.create_task(db, "u1")
    assert task.lifecycle == "active"

    response = await owner_client.get(f"/api/extensions/bid-write/tasks/{task.id}")
    assert response.status_code == 200
    assert response.json()["lifecycle"] == "active"


@pytest.mark.asyncio
async def test_set_lifecycle_updates_task(db):
    task = await crud.create_task(db, "u1")

    updated = await crud.set_lifecycle(db, task, "delivered")

    assert updated.lifecycle == "delivered"
    refreshed = await crud.get_task(db, task.id, "u1")
    assert refreshed is not None and refreshed.lifecycle == "delivered"


@pytest.mark.asyncio
async def test_write_task_out_includes_lifecycle(db):
    task = await crud.create_task(db, "u1")

    payload = schemas.WriteTaskOut.model_validate(task)

    assert payload.lifecycle == "active"


@pytest.mark.asyncio
async def test_submission_moves_to_reviewing_and_rejection_returns_to_active(db, owner_client, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", lambda *_args, **_kwargs: {"status": "ok", "blocked": False})
    task = await crud.create_task(db, "u1")

    submitted = await _submit(owner_client, task.id)
    assert submitted.status_code == 200, submitted.text
    reviewing = await crud.get_task(db, task.id, "u1")
    assert reviewing is not None and reviewing.lifecycle == "reviewing"

    await _decide(db, task.id, "rejected")
    revision = await crud.latest_revision(db, task.id, "u1")
    assert revision is not None and revision.status == "rejected"
    active = await crud.get_task(db, task.id, "u1")
    assert active is not None and active.lifecycle == "active"


@pytest.mark.asyncio
async def test_approval_keeps_reviewing_and_delivery_marks_delivered(db, owner_client, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", lambda *_args, **_kwargs: {"status": "ok", "blocked": False})

    async def fake_gate(*_args, **_kwargs):
        return _gate()

    monkeypatch.setattr(export_module, "run_export_gate", fake_gate)
    task = await crud.create_task(db, "u1")

    submitted = await _submit(owner_client, task.id)
    assert submitted.status_code == 200, submitted.text
    revision_id = submitted.json()["revision"]["id"]
    await _decide(db, task.id, "approved")
    reviewing = await crud.get_task(db, task.id, "u1")
    assert reviewing is not None and reviewing.lifecycle == "reviewing"

    response = await owner_client.post(f"/api/extensions/bid-write/tasks/{task.id}/revisions/{revision_id}/export")
    assert response.status_code == 200, response.text
    delivered = await crud.get_task(db, task.id, "u1")
    assert delivered is not None and delivered.lifecycle == "delivered"
