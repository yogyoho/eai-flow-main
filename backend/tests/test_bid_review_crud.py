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
async def test_empty_dedup_key_never_merges(db):
    """评审修复(Important#2):空 dedup_key 不参与查重——两条各自成行,第二条
    完整保留自己的 rule_id/verdict/message/evidence,不发生跨问题合并黑洞
    (旧行为:dedup_key 均为 "" 时第二条命中第一条,字段被静默丢弃只做证据并集)。"""
    t = await crud.create_task(db, owner_id="u1")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m1", fix="f1", evidence=[], dedup_key="")
    b = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L2-001", layer="L2", severity="major", verdict="need_human", message="m2", fix="f2", evidence=[{"doc_id": "d", "page": 1}], dedup_key="")
    assert a.id != b.id
    assert b.rule_id == "L2-001" and b.verdict == "need_human" and b.message == "m2" and len(b.evidence) == 1
    got = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    assert len(got) == 2


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


# ── B1(2026-10-31,Plan3 T2/T3):biz_no 生成 + done_at 落点 ──────────────


@pytest.mark.asyncio
async def test_create_task_biz_no_format_and_sequence(db):
    """B1:biz_no=TBR-{当日}-{seq:04d},同日递增。"""
    t1 = await crud.create_task(db, owner_id="u1")
    t2 = await crud.create_task(db, owner_id="u1")
    from datetime import UTC, datetime

    prefix = f"TBR-{datetime.now(UTC).strftime('%Y%m%d')}-"
    assert t1.biz_no == f"{prefix}0001"
    assert t2.biz_no == f"{prefix}0002"


def test_seq_of_parses_tail():
    """max(biz_no) 尾段解析:畸形/None 返回 None(从 0001 重开)。"""
    assert crud._seq_of("TBR-20261031-0007") == 7
    assert crud._seq_of(None) is None
    assert crud._seq_of("junk") is None


@pytest.mark.asyncio
async def test_set_status_done_at(db):
    """B1:done 落 done_at 一次(幂等,非 done 不动)。"""
    t = await crud.create_task(db, owner_id="u1")
    t = await crud.set_status(db, t, "running", progress={"stage": "x", "pct": 1})
    assert t.done_at is None
    t = await crud.set_status(db, t, "done")
    done1 = t.done_at
    assert done1 is not None
    t = await crud.set_status(db, t, "done")  # 重放幂等
    assert t.done_at == done1
