"""批三十二：bid-write 不可变修订 + workflow subject 审批闭环。"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import approval, crud, models
from app.extensions.bid_write import routers as R
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA

DOC = {
    "type": "doc",
    "content": [
        {
            "type": "para",
            "attrs": {"slot_id": "s1"},
            "content": [{"type": "text", "text": "投标正文"}],
        }
    ],
}
DOC2 = {
    "type": "doc",
    "content": [
        {
            "type": "para",
            "attrs": {"slot_id": "s1"},
            "content": [{"type": "text", "text": "修改后的正文"}],
        }
    ],
}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        models.WriteTask.__table__,
        models.TaskDocument.__table__,
        models.BidWriteDocumentRevision.__table__,
        models.MatrixRow.__table__,
        models.MaterialEntity.__table__,
        models.MaterialProfile.__table__,
        models.BidWritePolicy.__table__,
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


async def _seed(db):
    return (await crud.create_task(db, "u1")).id


async def _submit(client, task_id, *, reviewers, ast=DOC, **extra):
    body = {"ast": ast, "schema_version": "0.1.0", "reviewer_ids": reviewers, **extra}
    return await client.post(f"/api/extensions/bid-write/tasks/{task_id}/approval/submit", json=body)


@pytest.mark.asyncio
async def test_submit_freezes_revision_and_blocks_edit(owner_client, db):
    task_id = await _seed(db)
    created = await _submit(owner_client, task_id, reviewers=["u2"])
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["revision"]["status"] == "submitted"
    assert body["revision"]["hash_ok"] is True
    assert body["approval"]["status"] == "pending"
    assert body["approval"]["can_act"] is False

    locked = await owner_client.put(f"/api/extensions/bid-write/tasks/{task_id}/document", json={"ast": DOC2, "schema_version": "0.1.0"})
    assert locked.status_code == 409

    revisions = await owner_client.get(f"/api/extensions/bid-write/tasks/{task_id}/revisions")
    assert revisions.status_code == 200
    items = revisions.json()["items"]
    assert len(items) == 1 and items[0]["doc_hash"] == body["revision"]["doc_hash"]


@pytest.mark.asyncio
async def test_reviewer_read_access_and_non_reviewer_forbidden(owner_client, db):
    task_id = await _seed(db)
    created = await _submit(owner_client, task_id, reviewers=["u2"])
    assert created.status_code == 200
    instance_id = created.json()["approval"]["instance_id"]

    async with _client_as(db, "u3") as outsider_client:
        assert (await outsider_client.get(f"/api/extensions/bid-write/tasks/{task_id}/approval")).status_code == 404
        assert (await outsider_client.get(f"/api/extensions/bid-write/tasks/{task_id}/document")).status_code == 404
        denied = await outsider_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved"},
        )
        assert denied.status_code == 403

    async with _client_as(db, "u2") as reviewer_client:
        state = await reviewer_client.get(f"/api/extensions/bid-write/tasks/{task_id}/approval")
        assert state.status_code == 200
        assert state.json()["approval"]["can_act"] is True
        assert (await reviewer_client.get(f"/api/extensions/bid-write/tasks/{task_id}/document")).status_code == 200
        assert (await reviewer_client.get(f"/api/extensions/bid-write/tasks/{task_id}")).status_code == 200
        action = await reviewer_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved", "comment": "同意"},
        )
        assert action.status_code == 200
        assert action.json()["revision"]["status"] == "approved"


@pytest.mark.asyncio
async def test_duplicate_action_conflict(owner_client, db):
    task_id = await _seed(db)
    created = await _submit(owner_client, task_id, reviewers=["u2", "u3"])
    instance_id = created.json()["approval"]["instance_id"]
    async with _client_as(db, "u2") as reviewer_client:
        first = await reviewer_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved"},
        )
        assert first.status_code == 200 and first.json()["approval"]["status"] == "pending"
        duplicate = await reviewer_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved"},
        )
        assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_reject_allows_edit_and_new_revision(owner_client, db):
    task_id = await _seed(db)
    created = await _submit(owner_client, task_id, reviewers=["u2"])
    instance_id = created.json()["approval"]["instance_id"]
    async with _client_as(db, "u2") as reviewer_client:
        rejected = await reviewer_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "rejected", "comment": "金额不一致"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["revision"]["status"] == "rejected"

    editable = await owner_client.put(f"/api/extensions/bid-write/tasks/{task_id}/document", json={"ast": DOC2, "schema_version": "0.1.0"})
    assert editable.status_code == 200
    resubmitted = await _submit(owner_client, task_id, reviewers=["u2"], ast=DOC2)
    assert resubmitted.status_code == 200
    assert resubmitted.json()["revision"]["revision_no"] == 2


@pytest.mark.asyncio
async def test_approve_locks_document_and_revision_tamper_detected(owner_client, db):
    task_id = await _seed(db)
    created = await _submit(owner_client, task_id, reviewers=["u2"])
    revision_id = created.json()["revision"]["id"]
    instance_id = created.json()["approval"]["instance_id"]
    async with _client_as(db, "u2") as reviewer_client:
        approved = await reviewer_client.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved"},
        )
        assert approved.status_code == 200

    locked = await owner_client.put(f"/api/extensions/bid-write/tasks/{task_id}/document", json={"ast": DOC2, "schema_version": "0.1.0"})
    assert locked.status_code == 409
    detail = await owner_client.get(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "approved" and detail.json()["hash_ok"] is True
    assert detail.json()["ast"] == DOC

    # 直接篡改冻结快照后，只读详情必须显示 hash_ok=false（不静默假绿）。
    row = await crud.get_revision(db, revision_id, task_id, "u1")
    row.ast = DOC2
    await db.commit()
    tampered = await owner_client.get(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}")
    assert tampered.status_code == 200 and tampered.json()["hash_ok"] is False


@pytest.mark.asyncio
async def test_document_hash_mismatch_on_submit(owner_client, db):
    task_id = await _seed(db)
    res = await _submit(owner_client, task_id, reviewers=["u2"], document_hash="0" * 64)
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_failed_submit_does_not_half_save_document(owner_client, db):
    task_id = await _seed(db)
    res = await _submit(owner_client, task_id, reviewers=[])
    assert res.status_code == 422
    doc = await owner_client.get(f"/api/extensions/bid-write/tasks/{task_id}/document")
    assert doc.status_code == 200 and doc.json()["ast"] is None


@pytest.mark.asyncio
async def test_workflow_definition_path_is_snapshotted(owner_client, db, monkeypatch):
    task_id = await _seed(db)
    graph = {
        "version": 2,
        "mainGraph": {
            "nodes": [
                {"id": "start", "type": "system:start", "data": {"label": "开始"}},
                {"id": "biz", "type": "review", "data": {"label": "商务负责人", "reviewMode": "all", "reviewer_ids": ["u2"]}},
                {"id": "end", "type": "system:end", "data": {"label": "结束"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "biz"},
                {"id": "e2", "source": "biz", "target": "end"},
            ],
        },
    }

    async def fake_load(_db, definition_id):
        return graph, "商务审批流"

    monkeypatch.setattr(approval, "load_definition_graph", fake_load)
    res = await _submit(owner_client, task_id, reviewers=None, workflow_definition_id="def-1")
    assert res.status_code == 200, res.text
    assert res.json()["approval"]["definition_id"] == "def-1"
    assert res.json()["approval"]["workflow_source"] == "definition"
    assert res.json()["approval"]["current_node_label"] == "商务负责人"
