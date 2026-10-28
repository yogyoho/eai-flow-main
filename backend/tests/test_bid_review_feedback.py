"""Task 16 测试:feedback 复核三连 + 误报回流——confirm/false_positive/severity_change。

false_positive 后:issue ``verdict="false_positive"`` + ``need_human=False`` 落库(A8:
人工回写值仅落库,不经 issue-schema.json emission 校验)、RulePackMeta.stats[rule].fp+=1、
脱敏快照写入 stats[rule].fp_samples(≤20 条滚动,最旧先出);人工 severity_change 允许
任意合法档位(端点校验只拦非法值;模型侧 fatal 降级拦截是 verify 层 normalize_severity
职责)。MCP 侧 false_positive 与工作台同一回流语义(共用 routers.apply_false_positive)。

夹具照 test_bid_review_routers.py(httpx ASGITransport 子应用 + current_owner/get_db 双
override + 后台旁路打桩;偏离 plan 字面同先例:只定点建 bid_review 五张表)。
"""

import json

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
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


def _noop_enqueue(task, files):
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


async def _mk_issue(db, message: str = "投标总价 ¥101 超过最高限价 ¥100", rule_id: str = "L1-009", dedup_key: str = "k1", need_human: bool = False) -> models.ReviewIssue:
    t = await crud.create_task(db, owner_id="u1")
    return await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id=rule_id, layer="L1", severity="fatal", verdict="violation", message=message, dedup_key=dedup_key, need_human=need_human)


@pytest.mark.asyncio
async def test_false_positive_flips_issue_and_backflow_stats(client, db):
    """false_positive 三重回流:issue verdict="false_positive"+need_human=False 落库;
    stats[rule].fp+=1;脱敏快照入 stats[rule].fp_samples(仅判定面,不带 task/owner/evidence)。"""
    issue = await _mk_issue(db, need_human=True)
    r = await client.post(f"/api/extensions/bid-review/issues/{issue.id}/feedback", json={"action": "false_positive", "note": "限价口径含税,规则误报"})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "false_positive" and body["need_human"] is False
    await db.refresh(issue)
    assert issue.verdict == "false_positive" and issue.need_human is False
    fbs = (await db.execute(select(models.ReviewFeedback).where(models.ReviewFeedback.issue_id == issue.id))).scalars().all()
    assert len(fbs) == 1 and fbs[0].action == "false_positive" and fbs[0].note == "限价口径含税,规则误报"
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == R.RULEPACK_NAME))).scalar_one()
    entry = meta.stats["L1-009"]
    assert entry["fp"] == 1
    samples = entry["fp_samples"]
    assert len(samples) == 1
    snap = samples[0]
    assert set(snap.keys()) == {"issue_id", "rule_id", "layer", "severity", "message", "marked_at"}, "快照脱敏:仅判定面字段"
    assert snap["rule_id"] == "L1-009" and snap["layer"] == "L1" and snap["severity"] == "fatal"
    assert snap["message"] == issue.message and snap["issue_id"] == issue.id


@pytest.mark.asyncio
async def test_confirm_adopted_and_severity_change_any_legal_tier(client, db):
    """confirm → adopted+1;人工 severity_change 允许任意合法档位(fatal 亦可人工降级——
    拦模型侧是 verify 层职责),非法档位仍 422;severity 只落反馈行不回写 issue。"""
    issue = await _mk_issue(db, dedup_key="k1")
    assert (await client.post(f"/api/extensions/bid-review/issues/{issue.id}/feedback", json={"action": "confirm"})).status_code == 200
    r = await client.post(f"/api/extensions/bid-review/issues/{issue.id}/feedback", json={"action": "severity_change", "new_severity": "info", "note": "格式瑕疵非实质缺陷"})
    assert r.status_code == 200, "人工降级 fatal→info 应放行(端点不拦人工)"
    await db.refresh(issue)
    assert issue.severity == "fatal", "severity_change 只落反馈行,不回写 issue.severity"
    fbs = (await db.execute(select(models.ReviewFeedback).where(models.ReviewFeedback.issue_id == issue.id))).scalars().all()
    by_action = {f.action: f for f in fbs}
    assert set(by_action) == {"confirm", "severity_change"}, "两条反馈行都落库(id 是 UUID 非时序,断言不依赖行序)"
    assert by_action["severity_change"].new_severity == "info"
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == R.RULEPACK_NAME))).scalar_one()
    assert meta.stats["L1-009"]["adopted"] == 1 and "fp" not in meta.stats["L1-009"]
    assert (await client.post(f"/api/extensions/bid-review/issues/{issue.id}/feedback", json={"action": "severity_change", "new_severity": "huge"})).status_code == 422
    assert (await client.post(f"/api/extensions/bid-review/issues/{issue.id}/feedback", json={"action": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_fp_samples_roll_at_cap_20(client, db):
    """fp_samples ≤20 滚动:第 21 条起最旧样本先出(候选池只留最近 20 条),fp 计数不封顶。"""
    t = await crud.create_task(db, owner_id="u1")
    ids = []
    for i in range(1, 23):
        row = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-003", layer="L3", severity="major", verdict="violation", message=f"误报样本-{i:02d}", dedup_key=f"k{i:02d}")
        ids.append(row.id)
    for iid in ids:
        r = await client.post(f"/api/extensions/bid-review/issues/{iid}/feedback", json={"action": "false_positive"})
        assert r.status_code == 200
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == R.RULEPACK_NAME))).scalar_one()
    entry = meta.stats["L3-003"]
    assert entry["fp"] == 22, "fp 计数不设上限"
    msgs = [s["message"] for s in entry["fp_samples"]]
    assert len(msgs) == 20, "fp_samples 滚动封顶 20"
    assert "误报样本-01" not in msgs and "误报样本-02" not in msgs, "最旧样本先出"
    assert msgs[0] == "误报样本-03" and msgs[-1] == "误报样本-22"


@pytest.mark.asyncio
async def test_mcp_false_positive_same_backflow(db, monkeypatch):
    """MCP 侧 bid_review_feedback false_positive 与工作台同一回流语义(共用
    routers.apply_false_positive):verdict/need_human 落库 + fp_samples 滚动。"""
    from app.extensions.bid_review import mcp

    async def _wrap(session, fn):
        return await fn(session)

    monkeypatch.setattr(mcp, "_run_in_db", lambda fn: _wrap(db, fn))
    t = await crud.create_task(db, owner_id=mcp.MCP_OWNER)
    issue = await crud.add_issue(db, task_id=t.id, owner_id=mcp.MCP_OWNER, rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", dedup_key="mk1", need_human=True)
    out = json.loads((await mcp.handle_call("bid_review_feedback", {"issue_id": issue.id, "action": "false_positive", "note": "误报"}))[0].text)
    assert out["success"] is True and out["feedback_id"]
    await db.refresh(issue)
    assert issue.verdict == "false_positive" and issue.need_human is False
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == mcp.RULEPACK_NAME))).scalar_one()
    assert meta.stats["L1-009"]["fp"] == 1 and len(meta.stats["L1-009"]["fp_samples"]) == 1
