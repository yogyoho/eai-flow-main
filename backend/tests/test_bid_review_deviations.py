"""B9 响应偏离表(spec 2026-11-01 §1.2)测试:deviation_counts 纯函数 + GET /tasks/{id}/deviations。

数据源=基线 payload.fields["deviation.items"](抽取期 LLM 逐条对照招标↔投标);
基线每行同全量快照 → 按 item 名跨行去重(B4 手法);counts 服务端算(单一事实源):
tender_items=kind≠extra / bid_items=kind≠missing / negative+missing+extra 直计。
旧任务/未抽出 → 零投影 {counts 全 0, items:[]}(诚实,不装数据)。
夹具照 test_bid_review_score_coverage.py。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.bid_review.engine.extract import deviation_counts
from app.extensions.database import Base, get_db

ITEM_MATCH = {"item": "工期", "tender_req": "540日历天", "bid_response": "540日历天", "kind": "match", "severity": None, "evidence": {"role": "bid", "quote": "工期540日历天", "page": 3}}
ITEM_MISSING = {"item": "投标保证金", "tender_req": "10万元", "bid_response": None, "kind": "missing", "severity": "fatal", "evidence": {"role": "tender", "quote": "保证金10万元", "page": 5}}
ITEM_NEGATIVE = {"item": "质保期", "tender_req": "3年", "bid_response": "2年", "kind": "negative", "severity": "major", "evidence": {"role": "bid", "quote": "质保期2年", "page": 12}}
ITEM_EXTRA = {"item": "免费培训", "tender_req": None, "bid_response": "免费培训", "kind": "extra", "severity": "major", "evidence": None}
ITEM_POSITIVE = {"item": "工期承诺", "tender_req": "540日历天", "bid_response": "500日历天", "kind": "positive", "severity": None, "evidence": None}


# ── 纯函数 ────────────────────────────────────────────────────────────


def test_counts_semantics():
    """tender_items=kind≠extra(增项不在招标清单)/bid_items=kind≠missing(漏项无响应);类别直计。"""
    items = [ITEM_MATCH, ITEM_MISSING, ITEM_NEGATIVE, ITEM_EXTRA, ITEM_POSITIVE]
    assert deviation_counts(items) == {"tender_items": 4, "bid_items": 4, "negative": 1, "missing": 1, "extra": 1}


def test_counts_empty_and_junk():
    """空/None → 全 0;非 dict 项丢弃;dict 但 kind 缺失 → 计入两侧、不落类别。"""
    assert deviation_counts([]) == deviation_counts(None) == {"tender_items": 0, "bid_items": 0, "negative": 0, "missing": 0, "extra": 0}
    out = deviation_counts(["垃圾", {"item": "无名项", "kind": "match"}])
    assert out == {"tender_items": 1, "bid_items": 1, "negative": 0, "missing": 0, "extra": 0}


# ── 端点 ──────────────────────────────────────────────────────────────


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


async def _mk_baseline(db, task_id: str, items: list) -> models.BaselinePackage:
    row = models.BaselinePackage(
        task_id=task_id,
        kind="tender",
        payload={"fields": {"deviation.items": items}},
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_endpoint_projection_dedup_and_counts(client, db):
    """真投影:items 原样(不去内部字段)+counts 服务端算;两行同快照按 item 名去重。"""
    t = await crud.create_task(db, owner_id="u1")
    items = [ITEM_MATCH, ITEM_MISSING, ITEM_NEGATIVE, ITEM_EXTRA]
    await _mk_baseline(db, t.id, items)
    await _mk_baseline(db, t.id, items)  # 第二行同快照(docx 无页拆分场景)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/deviations")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"tender_items": 3, "bid_items": 3, "negative": 1, "missing": 1, "extra": 1}
    assert [i["item"] for i in body["items"]] == ["工期", "投标保证金", "质保期", "免费培训"]  # 保序+去重
    assert body["items"][1] == ITEM_MISSING  # 结构原样透传


@pytest.mark.asyncio
async def test_endpoint_zero_projection_without_field(client, db):
    """旧任务基线无 deviation.items(或基线缺失)→ counts 全 0 + items [](前端空态引导)。"""
    t = await crud.create_task(db, owner_id="u1")
    row = models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {"tender.max_price": 100}})
    db.add(row)
    await db.commit()
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/deviations")
    assert r.status_code == 200
    assert r.json() == {"counts": {"tender_items": 0, "bid_items": 0, "negative": 0, "missing": 0, "extra": 0}, "items": []}

    t2 = await crud.create_task(db, owner_id="u1")  # 连基线都没有
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{t2.id}/deviations")
    assert r2.status_code == 200 and r2.json()["items"] == []


@pytest.mark.asyncio
async def test_endpoint_ghost_404(client):
    r = await client.get("/api/extensions/bid-review/tasks/ghost/deviations")
    assert r.status_code == 404
