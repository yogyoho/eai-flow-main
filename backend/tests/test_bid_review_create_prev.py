"""B10 版本链入口(spec 2026-11-01 §2.3)测试:POST /tasks prev_task_id。

空串/缺省 → None;非空须存在+属主(404「基准任务不存在」),先校验后建任务
(防孤儿)。≠自身 422 不设:校验先于建任务且新任务 id 服务端生成,prev==self
必然落「不存在」404,422 永不可达——不写死代码。夹具照 test_bid_review_retry.py。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.ReviewTask.__table__,
                models.ReviewIssue.__table__,
                models.BaselinePackage.__table__,
                models.RulePackMeta.__table__,
                models.ReviewFeedback.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _noop_resume(task_id, owner_id):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_resume_after_confirm", _noop_resume)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(R, "_enqueue_docs", lambda task, docs: calls.append(task.id))
    return calls


@pytest.mark.asyncio
async def test_create_with_prev_task_persists(client, db, enqueued):
    """prev_task_id=既有任务 → 200 且落库(TaskOut 投影 + DB 行),后台直推照常。"""
    prev = await crud.create_task(db, owner_id="u1")
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick", "prev_task_id": prev.id})
    assert r.status_code == 200
    assert r.json()["prev_task_id"] == prev.id
    row = await crud.get_task(db, task_id=r.json()["id"], owner_id="u1")
    assert row.prev_task_id == prev.id
    assert enqueued == [r.json()["id"]]


@pytest.mark.asyncio
async def test_create_prev_ghost_404_no_orphan(client, db, enqueued):
    """prev 不存在 → 404「基准任务不存在」且不落任务行(先校验后建,无孤儿)。"""
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick", "prev_task_id": "ghost"})
    assert r.status_code == 404
    assert "基准任务" in r.json()["detail"]
    assert enqueued == []
    assert await crud.list_tasks(db, owner_id="u1") == []


@pytest.mark.asyncio
async def test_create_prev_empty_default_and_foreign_404(client, db, enqueued):
    """缺省/空串 → None;属他者的基准任务同样 404(owner 隔离)。"""
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick"})
    assert r.status_code == 200 and r.json()["prev_task_id"] is None
    r2 = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick", "prev_task_id": "  "})
    assert r2.status_code == 200 and r2.json()["prev_task_id"] is None
    foreign = await crud.create_task(db, owner_id="u2")
    r3 = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick", "prev_task_id": foreign.id})
    assert r3.status_code == 404
