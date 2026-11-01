"""B8 重试解析(spec §4.1 操作列)测试:POST /tasks/{id}/retry。

仅 failed 终态可重试(其余 409:done/awaiting_confirm 不复活,created/在途不双跑,
owner 隔离 404)。重试 = 清 error + infra_attempts 归零 + 回 created + 后台直推
_enqueue_docs;解析幂等:失败文档条目仍是 raw,重入 parsing 只补解析失败文档,
已解析条目不重复跑 OCR。夹具照 test_bid_review_diff.py。
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


async def _mk_failed_task(db, owner_id: str = "u1") -> models.ReviewTask:
    t = await crud.create_task(db, owner_id=owner_id)
    t.status = "failed"
    t.error = "pipeline: RuntimeError('ocr down')"
    t.engine_meta = {"infra_attempts": 3, "last_infra_error": "pipeline:RuntimeError"}
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_retry_failed_task_resets_and_reenqueues(client, db, enqueued):
    """failed → 200:status 回 created、error 清空、infra_attempts 归零、后台直推一次。"""
    t = await _mk_failed_task(db)
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/retry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    assert body["error"] is None
    await db.refresh(t)
    assert t.status == "created"
    assert t.error is None
    assert (t.engine_meta or {}).get("infra_attempts") == 0
    assert enqueued == [t.id]


@pytest.mark.asyncio
async def test_retry_non_failed_409(client, db, enqueued):
    """done / awaiting_confirm / created 在途 → 409(终态不复活,不双跑)。"""
    for status in ("done", "awaiting_confirm", "created"):
        t = await crud.create_task(db, owner_id="u1")
        t.status = status
        await db.commit()
        r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/retry")
        assert r.status_code == 409, status
    assert enqueued == []


@pytest.mark.asyncio
async def test_retry_task_not_found_or_foreign_404(client, db, enqueued):
    """不存在 / 属他者 → 404(owner 隔离)。"""
    r = await client.post("/api/extensions/bid-review/tasks/ghost/retry")
    assert r.status_code == 404
    foreign = await _mk_failed_task(db, owner_id="u2")
    r = await client.post(f"/api/extensions/bid-review/tasks/{foreign.id}/retry")
    assert r.status_code == 404
    assert enqueued == []
