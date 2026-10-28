"""Task 7 测试:bid_review CRUD(owner 隔离 + dedup 合并)——sqlite+aiosqlite 内存库。

偏离 plan 字面(Base.metadata.create_all):共享 Base 的跨模块 FK 在 DDL 排序时炸
(NoReferencedTableError,先例 test_geo_sample_bank_compile.py:949),故只定点建
bid_review 五张表(FK 闭包:issues/baselines→tasks、feedback→issues 均在集合内)。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
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


@pytest.mark.asyncio
async def test_create_and_owner_isolation(db):
    t = await crud.create_task(db, owner_id="u1", mode="quick")
    assert t.status == "created"
    mine = await crud.list_tasks(db, owner_id="u1")
    other = await crud.list_tasks(db, owner_id="u2")
    assert len(mine) == 1 and other == []


@pytest.mark.asyncio
async def test_issue_upsert_dedup(db):
    t = await crud.create_task(db, owner_id="u1")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m", fix="f", evidence=[], dedup_key="L1-009|-|x")
    b = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m", fix="f", evidence=[{"doc_id": "d", "page": 3}], dedup_key="L1-009|-|x")
    assert a.id == b.id, "同 dedup_key 合并且保留多证据"
    got = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    assert len(got) == 1 and len(got[0].evidence) == 1


@pytest.mark.asyncio
async def test_issue_dedup_evidence_union_skips_duplicates(db):
    """evidence 并集去重:同一条证据重复提交不重复追加。"""
    t = await crud.create_task(db, owner_id="u1")
    ev = [{"doc_id": "d", "page": 3}]
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-010", layer="L1", severity="major", verdict="violation", message="m", fix="f", evidence=ev, dedup_key="k2")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-010", layer="L1", severity="major", verdict="violation", message="m", fix="f", evidence=ev, dedup_key="k2")
    assert len(a.evidence) == 1


@pytest.mark.asyncio
async def test_set_status_and_owner_scoped_get(db):
    t = await crud.create_task(db, owner_id="u1", mode="deep")
    await crud.set_status(db, t, "running", progress={"stage": "extract", "pct": 30, "msg": "提取中"})
    got = await crud.get_task(db, task_id=t.id, owner_id="u1")
    assert got is not None and got.status == "running" and got.progress["pct"] == 30
    assert await crud.get_task(db, task_id=t.id, owner_id="u2") is None


@pytest.mark.asyncio
async def test_list_baselines_owner_scoped_and_confirm(db):
    t = await crud.create_task(db, owner_id="u1")
    other = await crud.create_task(db, owner_id="u2")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"clauses": []}))
    db.add(models.BaselinePackage(task_id=other.id, kind="bid", payload={"clauses": []}))
    await db.commit()
    mine = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert len(mine) == 1 and mine[0].kind == "tender"
    await crud.update_baseline(db, mine[0], confirmed=True)
    assert mine[0].confirmed is True


@pytest.mark.asyncio
async def test_record_feedback_owner_gate(db):
    t = await crud.create_task(db, owner_id="u1")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m", fix="f", evidence=[], dedup_key="k1")
    fb = await crud.record_feedback(db, issue_id=a.id, owner_id="u1", action="false_positive", note="误报")
    assert fb is not None and fb.action == "false_positive"
    # 越权:他人 owner 无法对该 issue 记 feedback(owner 过滤走 task 联接)
    assert await crud.record_feedback(db, issue_id=a.id, owner_id="u9", action="confirm") is None


@pytest.mark.asyncio
async def test_add_rulepack_stats_accumulates(db):
    await crud.add_rulepack_stats(db, name="bid-review-core", version="1.0.0", rule_id="L1-009", fp=True)
    meta = await crud.add_rulepack_stats(db, name="bid-review-core", rule_id="L1-009", hit=True, fp=True)
    assert meta.version == "1.0.0"
    assert meta.stats["L1-009"]["fp"] == 2 and meta.stats["L1-009"]["hit"] == 1
