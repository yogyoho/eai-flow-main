"""Task 10 测试:bid_review 8 端点——httpx ASGITransport + 独立 FastAPI 子应用挂 router;
auth 依赖 current_owner 与 get_db 双 override 到 sqlite 内存库;_enqueue_docs /
_resume_after_confirm 后台旁路(monkeypatch;plan Task 10 Step 1 夹具方式)。

偏离 plan 字面(同 test_bid_review_crud.py 先例):只定点建 bid_review 五张表(共享 Base
跨模块 FK 的 DDL 排序问题);plan 夹具样例未 override get_db,此处补上(端点经
Depends(get_db) 取会话,不 override 会打到生产 extensions DB)。
"""

import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models, worker
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
    """同步 no-op(plan 夹具同款形态;_enqueue_docs 本体即同步 create_task 包装)。"""


async def _noop_resume(task_id, owner_id):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    # current_owner = routers 内模块级 auth 依赖(必须模块级,dependency_overrides 才能打桩)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_enqueue_docs", _noop_enqueue)  # 解析旁路
    monkeypatch.setattr(R, "_resume_after_confirm", _noop_resume)  # 续跑旁路
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.asyncio
async def test_task_lifecycle(client, db):
    """plan Task 10 Step 1 原样:创建(默认 quick)→详情含 progress→规则包清单。"""
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick"})
    assert r.status_code == 200 and r.json()["status"] == "created"
    tid = r.json()["id"]
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{tid}")
    assert r2.json()["id"] == tid
    assert "progress" in r2.json()
    r3 = await client.get("/api/extensions/bid-review/rulepacks")
    assert r3.status_code == 200
    items = r3.json()["items"]
    assert items and items[0]["name"] == "bid-review-core" and items[0]["rule_count"] > 0
    assert all({"id", "name", "layer", "severity", "type"} <= set(rule) for rule in items[0]["rules"])


@pytest.mark.asyncio
async def test_create_task_with_files_persists_docs(client, db):
    """multipart 上传(tender+bid 各一份)→ 文档解码落 engine_meta.docs(role 逐份标注),
    任务保持 created(后台 advance 被打桩旁路)。"""
    r = await client.post(
        "/api/extensions/bid-review/tasks",
        data={"mode": "deep"},
        files=[("tender_files", ("t.txt", b"TENDER TEXT", "text/plain")), ("bid_files", ("b.txt", b"BID TEXT", "text/plain"))],
    )
    assert r.status_code == 200 and r.json()["mode"] == "deep" and r.json()["status"] == "created"
    t = await crud.get_task(db, task_id=r.json()["id"], owner_id="u1")
    docs = t.engine_meta["docs"]
    assert [d["role"] for d in docs] == ["tender", "bid"]
    assert docs[0]["doc_id"] == "t.txt" and docs[0]["text"] == "TENDER TEXT"
    assert docs[1]["text"] == "BID TEXT"


@pytest.mark.asyncio
async def test_create_task_rejects_bad_mode(client):
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "bogus"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks_owner_filter_and_cross_owner_404(client, db):
    mine = await crud.create_task(db, owner_id="u1")
    other = await crud.create_task(db, owner_id="u2")
    r = await client.get("/api/extensions/bid-review/tasks")
    assert {i["id"] for i in r.json()["items"]} == {mine.id}
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{other.id}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_confirm_flips_baselines_and_owner_gate(client, db):
    """确认门(仅 UI):基线全量翻转 confirmed;他人任务 404。"""
    t = await crud.create_task(db, owner_id="u1")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    db.add(models.BaselinePackage(task_id=t.id, kind="bid", payload={"fields": {}, "materials_hash": "x"}))
    await crud.set_status(db, t, "awaiting_confirm")
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 200
    baselines = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert all(b.confirmed for b in baselines)
    other = await crud.create_task(db, owner_id="u2")
    r2 = await client.post(f"/api/extensions/bid-review/tasks/{other.id}/confirm")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_issues_list_and_detail_owner_gated(client, db):
    t = await crud.create_task(db, owner_id="u1")
    other_t = await crud.create_task(db, owner_id="u2")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[{"doc_id": "b.pdf", "page": 1}], dedup_key="k1")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/issues")
    assert r.status_code == 200 and r.json()["items"][0]["id"] == a.id
    r2 = await client.get(f"/api/extensions/bid-review/issues/{a.id}")
    assert r2.status_code == 200 and r2.json()["rule_id"] == "L1-009"
    # 他人任务的 issues 列表 404;他人 issue 详情 404
    assert (await client.get(f"/api/extensions/bid-review/tasks/{other_t.id}/issues")).status_code == 404
    leaked = await crud.add_issue(db, task_id=other_t.id, owner_id="u2", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m", fix="f", evidence=[], dedup_key="k9")
    assert (await client.get(f"/api/extensions/bid-review/issues/{leaked.id}")).status_code == 404
    assert (await client.get("/api/extensions/bid-review/issues/nonexistent")).status_code == 404


@pytest.mark.asyncio
async def test_feedback_writes_row_and_rulepack_stats(client, db):
    """feedback 三连:ReviewFeedback 落行 + RulePackMeta.stats 回流(false_positive→fp+1,
    confirm→adopted+1);非法 action/new_severity 422。"""
    t = await crud.create_task(db, owner_id="u1")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "false_positive", "note": "误报"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "confirm"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "severity_change", "new_severity": "major"})).status_code == 200
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == "bid-review-core"))).scalar_one()
    assert meta.stats["L1-009"]["fp"] == 1 and meta.stats["L1-009"]["adopted"] == 1
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "bogus"})).status_code == 422
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "severity_change", "new_severity": "huge"})).status_code == 422


# ── Task 14:issues 列表 API 汇总分级(A12 T14 集成约束①)──────────────


@pytest.mark.asyncio
async def test_issues_list_summary_grades_need_human_separately(client, db):
    """T14 A12 约束①:issues 列表 API 响应带 summary(汇总分级)——正式违规计数
    (fatal/major/minor/info)不含 need_human 条目,待人工单列;条目不删(items 仍
    全量返回,工作台待人工格与 verdict 过滤消费)。与 worker progress.summary 共用
    worker.summarize_issues,两侧口径一致。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="fatal", verdict="unclear", message="材料不足", fix="补响应", evidence=[], dedup_key="k2", need_human=True)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-001", layer="L3", severity="minor", verdict="violation", message="页眉不一致", fix="替换", evidence=[], dedup_key="k3")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/issues")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3, "need_human 条目仍在清单(单列不删除,待人工格消费)"
    assert body["summary"] == {"fatal": 1, "major": 0, "minor": 1, "info": 0, "need_human": 1}, "致命计数不含 need_human 条目(fatal sem 条目入待人工)"


# ── Task 15:确认门端点收紧 + MCP 无 confirm 断言 ─────────────────────


@pytest.mark.asyncio
async def test_confirm_gate_rejects_non_awaiting_confirm(client, db):
    """Task 15:confirm 端点校验 status==awaiting_confirm——其余状态(created/done 等)
    直接投续跑一律 409,且基线不得被翻转(确认门是唯一续跑通道,不可旁路/重复确认)。"""
    t = await crud.create_task(db, owner_id="u1")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    await db.commit()
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 409, "created(未到基线确认门)不得 confirm 续跑"
    baselines = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert all(not b.confirmed for b in baselines), "409 时基线不得被翻转"
    await crud.set_status(db, t, "done")
    assert (await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")).status_code == 409, "done 终态重复确认拒绝"


@pytest.mark.asyncio
async def test_awaiting_confirm_needs_confirm_to_run(client, db, monkeypatch):
    """Task 15:awaiting_confirm 未 confirm 的任务——worker claim 跳过(领取集只有
    created/extracting);唯一放行通道是 POST /confirm(触发续跑后台)。"""
    t = await crud.create_task(db, owner_id="u1", mode="deep")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    await crud.set_status(db, t, "awaiting_confirm")
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    assert await worker._claim_next(factory) is None, "确认门未过的任务 claim 必须跳过"

    resumed: list[tuple[str, str]] = []
    released = asyncio.Event()

    async def _spy_resume(task_id, owner_id):
        resumed.append((task_id, owner_id))
        released.set()

    monkeypatch.setattr(R, "_resume_after_confirm", _spy_resume)
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 200
    await asyncio.wait_for(released.wait(), timeout=2)
    assert resumed and resumed[0] == (t.id, "u1"), "confirm 必须经续跑通道把任务推向 running"


def test_mcp_tools_expose_no_confirm_gate():
    """Task 15 静态断言:MCP 工具键集与 handler 表均无 confirm/baseline_confirm 类工具——
    基线确认门仅工作台 UI,agent 不可代确认(设计文档 §4.3/§4.8)。"""
    from app.extensions.bid_review import mcp

    assert len(mcp.TOOLS) == 7
    assert all("confirm" not in name for name in mcp.TOOLS), "MCP 绝不暴露确认门"
    assert all("confirm" not in name for name in mcp._HANDLERS), "handler 表同样不得有 confirm 类"
