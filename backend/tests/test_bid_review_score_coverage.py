"""B4 评分覆盖度(spec §5)测试:compute_score_coverage 纯函数 + GET /tasks/{id}/score_coverage。

覆盖映射机制:评分办法项抽取时携带 related_paths(抽取层限定为字段字典路径),
与启用规则 inputs 求交——交集非空即覆盖。映射纯机械、可审计;related_paths 缺失
或全未知 → 该项未覆盖(诚实:映射不来就别装覆盖)。夹具照 test_bid_review_diff.py。
"""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.bid_review.engine.extract import compute_score_coverage
from app.extensions.database import Base, get_db


class _FakeRule:
    def __init__(self, rule_id: str, inputs: list[str], enabled: bool = True):
        self.id = rule_id
        self.inputs = inputs
        self.enabled = enabled


# ── 纯函数 ────────────────────────────────────────────────────────────


def test_coverage_intersection_and_counts():
    """related_paths ∩ rule.inputs 非空即覆盖;covered/total 逐项计。"""
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price", "tender.bid_scope"]},
        {"name": "履约信誉分", "max_score": 10, "related_paths": ["tender.bid_scope"]},
    ]
    rules = [
        _FakeRule("L1-009", ["bid.total_price", "tender.max_price"]),
        _FakeRule("L1-002", ["bid.qual_levels"]),
    ]
    out = compute_score_coverage(items, rules)
    assert out["total"] == 2 and out["covered"] == 1
    assert out["items"][0]["covered_by_rules"] == ["L1-009"]
    assert out["items"][1]["covered_by_rules"] == []


def test_coverage_drops_junk_and_disabled_rules():
    """非 dict 项/无名项丢弃;enabled=False 规则不参与;related_paths 缺失 → 未覆盖。"""
    items = ["垃圾", {"max_score": 5}, {"name": "  "}, {"name": "方案分"}]
    rules = [_FakeRule("L3-001", ["tender.project_identity.name"], enabled=False)]
    out = compute_score_coverage(items, rules)
    assert out["total"] == 1
    assert out["items"][0] == {"name": "方案分", "max_score": None, "covered_by_rules": []}
    assert out["covered"] == 0


def test_coverage_empty():
    assert compute_score_coverage([], []) == {"total": 0, "covered": 0, "items": []}


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


async def _mk_baseline(db, task_id: str, scoring_items: list) -> models.BaselinePackage:
    row = models.BaselinePackage(
        task_id=task_id,
        kind="tender",
        payload={"fields": {"tender.scoring_items": scoring_items}},
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_endpoint_coverage_with_intersection(client, db):
    """基线带评分办法项 → {total, covered, items};related_paths 用生产规则包
    真实路径(tender.max_price ∈ L1-009 inputs)验证端到端接线。多行同快照按
    name 去重,不重复计数。"""
    t = await crud.create_task(db, owner_id="u1")
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price"]},
        {"name": "方案分", "max_score": 30, "related_paths": []},
    ]
    await _mk_baseline(db, t.id, items)
    await _mk_baseline(db, t.id, items)  # 第二行同快照(docx 无页拆分场景)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/score_coverage")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["covered"] == 1
    price = next(i for i in body["items"] if i["name"] == "价格分")
    assert price["covered_by_rules"] == ["L1-009"]
    assert next(i for i in body["items"] if i["name"] == "方案分")["covered_by_rules"] == []


@pytest.mark.asyncio
async def test_endpoint_no_scoring_items_zero_projection(client, db):
    """旧任务基线无评分办法项 → {total:0, covered:0, items:[]}(前端据此回落规则命中 meter)。"""
    t = await crud.create_task(db, owner_id="u1")
    await _mk_baseline(db, t.id, [])
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/score_coverage")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "covered": 0, "items": []}


@pytest.mark.asyncio
async def test_endpoint_task_not_found_404(client):
    r = await client.get("/api/extensions/bid-review/tasks/ghost/score_coverage")
    assert r.status_code == 404
