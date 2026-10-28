"""Task 11 测试:bid_review MCP 七工具——直接调 handle_call(不过 stdio);_run_in_db
打桩注入测试 session(plan 夹具方式);断言绝无 confirm 工具(基线确认门仅工作台 UI)。

偏离 plan 字面:MCP stdio 子进程无用户身份(translation/mcp.py R7 同款边界),七工具一律
按服务级 owner(MCP_OWNER)隔离——测试任务建在 MCP_OWNER 名下(plan 样例 owner_id="u1"
对 MCP 工具恒不可见,那正是隔离语义本身)。
"""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, mcp, models
from app.extensions.database import Base


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


async def _wrap(session, fn):
    """_run_in_db 打桩:直接以现成 session 调 fn(等价真身 `async with factory() as
    session: return await func(session)` 分支;plan 样例的 R 上下文壳与 contract_price
    同款 func(session) 契约不符——fn(R()) 会把壳当 session 用,遂直传 session)。"""
    return await fn(session)


@pytest.fixture
def patched_run_in_db(db, monkeypatch):
    monkeypatch.setattr(mcp, "_run_in_db", lambda fn: _wrap(db, fn))


def _out(payload) -> dict:
    return json.loads(payload[0].text)


@pytest.mark.asyncio
async def test_tools_readonly_and_no_confirm(db, patched_run_in_db):
    """plan Task 11 Step 1 原样:status 读回 created;工具注册表绝不含 confirm 类工具。"""
    t = await crud.create_task(db, owner_id=mcp.MCP_OWNER)
    out = _out(await mcp.handle_call("bid_review_status", {"task_id": t.id}))
    assert out["status"] == "created"
    assert len(mcp.TOOLS) == 7
    assert not any("confirm" in n for n in mcp.TOOLS), "MCP 绝不暴露确认门"


@pytest.mark.asyncio
async def test_start_creates_task_under_service_owner(db, patched_run_in_db):
    out = _out(await mcp.handle_call("bid_review_start", {"mode": "quick", "tender_doc_note": "招标.pdf", "bid_doc_note": "投标.pdf"}))
    assert out["success"] is True and out["workbench_url"]
    t = await crud.get_task(db, task_id=out["task_id"], owner_id=mcp.MCP_OWNER)
    assert t is not None and t.mode == "quick"
    assert t.engine_meta["tender_doc_note"] == "招标.pdf"
    # 其他 owner 的任务对 MCP 不可见(隔离语义)
    ui_task = await crud.create_task(db, owner_id="u1")
    assert _out(await mcp.handle_call("bid_review_status", {"task_id": ui_task.id}))["success"] is False
    bad = _out(await mcp.handle_call("bid_review_start", {"mode": "bogus"}))
    assert bad["success"] is False


@pytest.mark.asyncio
async def test_issues_issue_and_feedback(db, patched_run_in_db):
    t = await crud.create_task(db, owner_id=mcp.MCP_OWNER)
    a = await crud.add_issue(db, task_id=t.id, owner_id=mcp.MCP_OWNER, rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[{"doc_id": "b.pdf", "page": 1}], dedup_key="k1")
    issues = _out(await mcp.handle_call("bid_review_issues", {"task_id": t.id}))
    assert issues["count"] == 1 and issues["issues"][0]["id"] == a.id
    filtered = _out(await mcp.handle_call("bid_review_issues", {"task_id": t.id, "severity": "minor"}))
    assert filtered["count"] == 0
    one = _out(await mcp.handle_call("bid_review_issue", {"issue_id": a.id}))
    assert one["rule_id"] == "L1-009" and one["evidence"]
    fb = _out(await mcp.handle_call("bid_review_feedback", {"issue_id": a.id, "action": "false_positive", "note": "误报"}))
    assert fb["success"] is True and fb["feedback_id"]
    meta = await crud.add_rulepack_stats(db, name="bid-review-core", rule_id="L1-009", hit=True)
    assert meta.stats["L1-009"]["fp"] == 1
    bad = _out(await mcp.handle_call("bid_review_feedback", {"issue_id": a.id, "action": "bogus"}))
    assert bad["success"] is False


@pytest.mark.asyncio
async def test_baseline_get_readonly_and_rulepacks(db, patched_run_in_db):
    t = await crud.create_task(db, owner_id=mcp.MCP_OWNER)
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {"tender.max_price": 100}, "materials_hash": "h"}))
    await db.commit()
    out = _out(await mcp.handle_call("bid_review_baseline_get", {"task_id": t.id}))
    assert out["success"] is True and len(out["baselines"]) == 1
    assert out["baselines"][0]["kind"] == "tender"
    assert "工作台" in out["note"], "baseline_get 只读,确认门指向工作台 UI"
    packs = _out(await mcp.handle_call("bid_review_rulepacks", {}))
    assert packs["success"] is True and packs["items"][0]["name"] == "bid-review-core"


@pytest.mark.asyncio
async def test_unknown_tool(db, patched_run_in_db):
    out = await mcp.handle_call("nonexistent", {})
    assert "Unknown tool" in out[0].text
