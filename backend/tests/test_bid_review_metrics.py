"""M5 治理页 B5/B6 测试:规则定义五块明细 + list_rulepacks op 投影 + FAIL 归因 + 周趋势。

夹具照 test_bid_review_feedback.py(httpx ASGITransport 子应用 + current_owner/get_db 双
override;只定点建 bid_review 五张表)。归因读 note 首段「误报原因:」(工作台/结果页
折进约定);趋势按自然周(周一始)分桶,空周 rate=None(伪零纪律)。
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db

_KNOWN_OPS = {"lte", "gte", "eq", "and", "all", "set_eq", "att_check", "att_count", "att_missing_rows", "steps"}  # att_* = L2 P1(spec 2026-11-02 §3)+L2-021 指纹通道(spec 2026-11-04)


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


async def _noop_enqueue(task, files):
    return None


async def _noop_resume(task_id, owner_id):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_enqueue_docs", _noop_enqueue)  # 解析旁路
    monkeypatch.setattr(R, "_resume_after_confirm", _noop_resume)  # 续跑旁路
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _mk_issue(db, rule_id: str, dedup_key: str) -> models.ReviewIssue:
    t = await crud.create_task(db, owner_id="u1")
    return await crud.add_issue(
        db,
        task_id=t.id,
        owner_id="u1",
        rule_id=rule_id,
        layer="L1",
        severity="fatal",
        verdict="violation",
        message="投标总价 ¥101 超过最高限价 ¥100",
        dedup_key=dedup_key,
        need_human=False,
    )


@pytest.mark.asyncio
async def test_rulepack_rule_details_b5(client):
    """B5:GET /rulepacks/{name}/rules 五块明细——op 归一(steps 链→"steps")、
    PRECONDITION/EXPR/ON_MISSING_INPUT/MESSAGE_TPL/FIX_TPL 全量投影;未知包名 404;
    list_rulepacks 规则投影同步携带 op。"""
    r = await client.get("/api/extensions/bid-review/rulepacks/bid-review-core/rules")
    assert r.status_code == 200
    body = r.json()
    assert body["pack"]["name"] == "bid-review-core" and body["pack"]["version"]
    items = body["items"]
    assert len(items) >= 20, "生产包 32 规则,投影缺一条都是断供"
    by_id = {i["id"]: i for i in items}
    assert all(set(i) == {"id", "name", "layer", "severity", "type", "op", "precondition", "expr_lines", "on_missing_input", "message_tpl", "fix_tpl", "evidence"} for i in items)
    assert all(i["op"] in _KNOWN_OPS for i in items), "op 只允许白名单算子或 steps 归一"
    # op 形态代表:L1-009(lte)单表达式;steps 形态代表:L1-010(三步加总链)
    lte_rule = by_id["L1-009"]
    assert lte_rule["op"] == "lte" and len(lte_rule["expr_lines"]) == 1 and "lte" in lte_rule["expr_lines"][0]
    assert lte_rule["message_tpl"] and lte_rule["fix_tpl"]
    steps_rule = by_id["L1-010"]
    assert steps_rule["op"] == "steps" and len(steps_rule["expr_lines"]) == 3
    assert all(i["on_missing_input"] == "need_human" for i in items), "conventions 投影到每条规则"
    assert (await client.get("/api/extensions/bid-review/rulepacks/no-such-pack/rules")).status_code == 404
    # list_rulepacks 投影加 op(共享表列「判定」数据源)
    rl = (await client.get("/api/extensions/bid-review/rulepacks")).json()
    assert all("op" in rule and rule["op"] in _KNOWN_OPS for rule in rl["items"][0]["rules"])


@pytest.mark.asyncio
async def test_fail_attribution_b6(client, db):
    """B6 归因:false_positive 反馈按规则聚合误报原因(note 首段「误报原因:」到分号止;
    无前缀 → 未归因,不伪造);top 原因按次数降序。"""
    i1 = await _mk_issue(db, "L1-009", "k1")
    i2 = await _mk_issue(db, "L1-009", "k2")
    i3 = await _mk_issue(db, "L1-010", "k3")
    assert (await client.post(f"/api/extensions/bid-review/issues/{i1.id}/feedback", json={"action": "false_positive", "note": "误报原因:规则误判;补充说明"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{i2.id}/feedback", json={"action": "false_positive", "note": "误报原因:证据错位"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{i3.id}/feedback", json={"action": "false_positive"})).status_code == 200
    r = await client.get("/api/extensions/bid-review/metrics/fail_attribution")
    assert r.status_code == 200
    by_rule = {i["rule_id"]: i for i in r.json()["items"]}
    a1 = by_rule["L1-009"]
    assert a1["total"] == 2 and a1["reasons"] == [{"reason": "规则误判", "count": 1}, {"reason": "证据错位", "count": 1}]
    assert by_rule["L1-010"]["reasons"] == [{"reason": "未归因", "count": 1}]
    # confirm 不进归因
    i4 = await _mk_issue(db, "L1-011", "k4")
    await client.post(f"/api/extensions/bid-review/issues/{i4.id}/feedback", json={"action": "confirm"})
    r2 = await client.get("/api/extensions/bid-review/metrics/fail_attribution")
    assert "L1-011" not in {i["rule_id"] for i in r2.json()["items"]}


@pytest.mark.asyncio
async def test_metrics_trends_b6(client, db):
    """B6 趋势:近 6 周分桶(周一始),rate=fp/(fp+confirm);空周 rate=None(伪零纪律);
    其它动作(severity_change/need_human)不进分母;回填 created_at 生效。"""
    empty = (await client.get("/api/extensions/bid-review/metrics/trends")).json()["weeks"]
    assert len(empty) == 6 and all(w["rate"] is None for w in empty)
    i1 = await _mk_issue(db, "L1-009", "k1")
    i2 = await _mk_issue(db, "L1-010", "k2")
    await client.post(f"/api/extensions/bid-review/issues/{i1.id}/feedback", json={"action": "confirm"})
    await client.post(f"/api/extensions/bid-review/issues/{i2.id}/feedback", json={"action": "false_positive", "note": "误报原因:规则误判"})
    # 把 i2 的反馈回填到 3 周前
    fbs = (await db.execute(select(models.ReviewFeedback))).scalars().all()
    back = datetime.now(UTC).replace(tzinfo=None) - timedelta(weeks=3)
    await db.execute(update(models.ReviewFeedback).where(models.ReviewFeedback.id == fbs[-1].id).values(created_at=back))
    await db.commit()
    weeks = (await client.get("/api/extensions/bid-review/metrics/trends")).json()["weeks"]
    by_start = {w["week_start"]: w for w in weeks}
    now = datetime.now(UTC)
    this_monday = now.date() - timedelta(days=now.weekday())
    cur = by_start[this_monday.isoformat()]
    assert cur["confirmed"] == 1 and cur["fp"] == 0 and cur["rate"] == 0.0
    back_monday = (back.date() - timedelta(days=back.date().weekday())).isoformat()
    assert by_start[back_monday]["fp"] == 1 and by_start[back_monday]["rate"] == 100.0
    assert sum(1 for w in weeks if w["rate"] is None) == 4
