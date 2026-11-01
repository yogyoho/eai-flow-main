"""B7 版本 diff(spec §5)测试:GET /tasks/{id}/diff?prev=<task_id> 问题级三态。

匹配键 = dedup_key(rule_id+锚定字段路径,引擎查重同源语义 crud.add_issue);
added/removed 按 severity 降序(致命在前)给前端对比卡片直接渲染;
prev 不存在/不属于同 owner → 404(不泄漏他者任务)。夹具照 test_bid_review_feedback.py。
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


async def _mk_task(db, owner_id: str = "u1", prev_task_id: str | None = None) -> models.ReviewTask:
    t = await crud.create_task(db, owner_id=owner_id)
    if prev_task_id:
        t.prev_task_id = prev_task_id
        await db.commit()
    return t


async def _mk_issue(db, task_id: str, rule_id: str, dedup_key: str, severity: str = "major") -> models.ReviewIssue:
    return await crud.add_issue(
        db,
        task_id=task_id,
        owner_id="u1",
        rule_id=rule_id,
        layer="L1",
        severity=severity,
        verdict="violation",
        message=f"问题 {rule_id}",
        dedup_key=dedup_key,
    )


@pytest.mark.asyncio
async def test_diff_three_states_added_removed_unchanged(client, db):
    """prev 有 k1(k2),cur 有 k2(k3)→ added=[k3], removed=[k1], unchanged=1;
    added 带 rule_id/severity/message 供新增问题列表直渲,removed 只带计数面三字段。"""
    prev = await _mk_task(db)
    cur = await _mk_task(db, prev_task_id=prev.id)
    await _mk_issue(db, prev.id, "L1-009", "k1")
    await _mk_issue(db, prev.id, "L1-010", "k2")
    await _mk_issue(db, cur.id, "L1-010", "k2")
    await _mk_issue(db, cur.id, "L3-005", "k3")
    r = await client.get(f"/api/extensions/bid-review/tasks/{cur.id}/diff", params={"prev": prev.id})
    assert r.status_code == 200
    body = r.json()
    assert body["unchanged_count"] == 1
    assert [a["dedup_key"] if "dedup_key" in a else a["rule_id"] for a in body["added"]] == ["L3-005"]
    assert body["added"][0]["rule_id"] == "L3-005" and body["added"][0]["severity"] == "major"
    assert "message" in body["added"][0]
    assert [x["rule_id"] for x in body["removed"]] == ["L1-009"]
    assert set(body["removed"][0].keys()) == {"rule_id", "severity", "message"}


@pytest.mark.asyncio
async def test_diff_added_sorted_fatal_first(client, db):
    """added 按 severity 降序:致命先于主要(fatal<major)。"""
    prev = await _mk_task(db)
    cur = await _mk_task(db, prev_task_id=prev.id)
    await _mk_issue(db, cur.id, "L1-010", "kb", severity="major")
    await _mk_issue(db, cur.id, "L1-009", "ka", severity="fatal")
    r = await client.get(f"/api/extensions/bid-review/tasks/{cur.id}/diff", params={"prev": prev.id})
    body = r.json()
    assert [a["rule_id"] for a in body["added"]] == ["L1-009", "L1-010"]
    assert body["unchanged_count"] == 0 and body["removed"] == []


@pytest.mark.asyncio
async def test_diff_prev_not_found_or_foreign_404(client, db):
    """prev 不存在 / 属他者 → 404(owner 隔离,不泄漏他者任务存在性)。"""
    cur = await _mk_task(db)
    r = await client.get(f"/api/extensions/bid-review/tasks/{cur.id}/diff", params={"prev": "nope"})
    assert r.status_code == 404
    foreign = await _mk_task(db, owner_id="u2")
    r = await client.get(f"/api/extensions/bid-review/tasks/{cur.id}/diff", params={"prev": foreign.id})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_diff_current_task_not_found_404(client, db):
    """cur 不存在(他者或无)→ 404。"""
    prev = await _mk_task(db)
    r = await client.get("/api/extensions/bid-review/tasks/ghost/diff", params={"prev": prev.id})
    assert r.status_code == 404
