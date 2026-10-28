"""Task 9 测试:bid_review worker——状态机推进(advance_task)+ boot recovery +
infra 失败链 + 确认门续跑(resume_confirmed)。sqlite+aiosqlite 内存库,advance 直注
测试 session/extract_fn(translation worker 可注入惯例);det 规则包 monkeypatch 成
tmp_path 内最小包(不依赖生产 1.0.0.yaml 内容)。

偏离 plan 字面(同 test_bid_review_crud.py 先例):共享 Base 跨模块 FK 在 DDL 排序时炸,
只定点建 bid_review 五张表(FK 闭包在集合内)。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review.worker import advance_task, boot_recovery, resume_confirmed
from app.extensions.database import Base

_TMP_RULEPACK = """\
conventions:
  on_missing_input: need_human
rules:
  - id: T1-001
    name: 测试总价不超限价
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.total_price, tender.max_price]
    check:
      op: lte
      left: bid.total_price
      right: tender.max_price
    severity: fatal
    evidence: []
    message_tpl: "投标总价 {bid.total_price:money} 超过最高限价 {tender.max_price:money}"
    fix_tpl: 复核报价汇总与含税口径
    confidence_gate: 1.0
    enabled: true
  - id: T1-002
    name: 测试缺字段走 need_human
    layer: L3
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.missing_field]
    check:
      op: eq
      left: bid.missing_field
      right: bid.missing_field
    severity: minor
    evidence: []
    message_tpl: 缺字段规则不应产出 violation
    fix_tpl: 补齐字段
    confidence_gate: 1.0
    enabled: true
"""


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


@pytest.fixture
def tmp_rulepack(monkeypatch, tmp_path):
    p = tmp_path / "pack.yaml"
    p.write_text(_TMP_RULEPACK, encoding="utf-8")
    monkeypatch.setattr("app.extensions.bid_review.worker.RULEPACK_PATH", p)
    return p


@pytest.mark.asyncio
async def test_advance_created_to_awaiting_confirm(db):
    """plan Task 9 Step 1:wait_confirm=True 停 awaiting_confirm;基线按 docs role 拆且全部未确认。"""
    t = await crud.create_task(db, owner_id="u1")
    docs = [{"doc_id": "t.pdf", "role": "tender", "text": "x"}, {"doc_id": "b.pdf", "role": "bid", "text": "y"}]
    # confirm_baseline=False:det-only 快审直接跑;True:停在 awaiting_confirm
    await advance_task(db, t.id, owner_id="u1", docs=docs, extract_fn=lambda d, p: {p2: None for p2 in p}, wait_confirm=True)
    await db.refresh(t)
    assert t.status == "awaiting_confirm"
    baselines = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert len(baselines) == 2 and all(not b.confirmed for b in baselines)
    assert {b.kind for b in baselines} == {"tender", "bid"}


@pytest.mark.asyncio
async def test_advance_quick_det_run_to_done(db, tmp_rulepack):
    """wait_confirm=False 快审直跑:parsing→extracting→基线→running→det→done;
    命中规则产 violation(message_tpl money 渲染),缺字段规则产 need_human。"""
    t = await crud.create_task(db, owner_id="u1")
    docs = [{"doc_id": "b.pdf", "role": "bid", "text": "x"}]
    fields = {"bid.total_price": 2000000, "tender.max_price": 1000000, "bid.price_includes_tax": True, "tender.price_includes_tax": True}

    def _extract(d, p):
        return {**{k: None for k in p}, **fields}

    task = await advance_task(db, t.id, owner_id="u1", docs=docs, extract_fn=_extract, wait_confirm=False)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    by_rule = {i.rule_id: i for i in issues}
    assert by_rule["T1-001"].verdict == "violation"
    assert by_rule["T1-001"].message == "投标总价 ¥2,000,000.00 超过最高限价 ¥1,000,000.00"
    assert by_rule["T1-002"].verdict == "need_human"
    assert task.progress["pct"] == 100
    assert task.engine_meta.get("materials_hash")


@pytest.mark.asyncio
async def test_advance_all_null_fields_need_human_not_crash(db, tmp_rulepack):
    """None 值字段剥离守卫:提取全 null → 每条 det 规则 need_human、任务到 done;
    若 None 直进求值器,run_det_rule 的比较算子会 TypeError 崩任务(守卫回归门)。"""
    t = await crud.create_task(db, owner_id="u1")
    task = await advance_task(db, t.id, owner_id="u1", docs=[], extract_fn=lambda d, p: {k: None for k in p}, wait_confirm=False)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    assert issues and all(i.verdict == "need_human" for i in issues)


@pytest.mark.asyncio
async def test_resume_confirmed_runs_det_and_done(db, tmp_rulepack):
    """确认门续跑:awaiting_confirm →(confirm 后)resume_confirmed →running→det→done。"""
    t = await crud.create_task(db, owner_id="u1")
    docs = [{"doc_id": "t.pdf", "role": "tender", "text": "x"}]
    fields = {"bid.total_price": 500, "tender.max_price": 1000, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
    await advance_task(db, t.id, owner_id="u1", docs=docs, extract_fn=lambda d, p: {**{k: None for k in p}, **fields}, wait_confirm=True)
    task = await resume_confirmed(db, t.id, "u1")
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    # 500<=1000 干净:T1-001 不产条目;T1-002 缺字段 → 唯一 need_human
    assert len(issues) == 1 and issues[0].verdict == "need_human" and issues[0].rule_id == "T1-002"


@pytest.mark.asyncio
async def test_boot_recovery_resets_running_to_extracting(db):
    """boot recovery:running→extracting(计划口径),幂等;claimer 以 extracting 入口断点续跑。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.set_status(db, t, "running")
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    assert await boot_recovery(factory) == 1
    await db.refresh(t)
    assert t.status == "extracting"
    assert await boot_recovery(factory) == 0  # 幂等:再跑零命中


@pytest.mark.asyncio
async def test_infra_fail_retries_then_terminal(db):
    """基础设施失败链:attempts<3 回 created 重投(claimer 指数退避),≥3 → failed 终态;
    终态守卫:failed 不复活、attempts 不再累加。"""
    from app.extensions.bid_review import worker

    t = await crud.create_task(db, owner_id="u1")
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    assert await worker._infra_fail(t.id, RuntimeError("boom-1"), "pipeline", factory=factory) == "created"
    assert await worker._infra_fail(t.id, RuntimeError("boom-2"), "pipeline", factory=factory) == "created"
    assert await worker._infra_fail(t.id, RuntimeError("boom-3"), "pipeline", factory=factory) == "failed"
    await db.refresh(t)
    assert t.status == "failed" and "boom-3" in (t.error or "")
    assert t.engine_meta["infra_attempts"] == 3
    assert await worker._infra_fail(t.id, RuntimeError("late"), "pipeline", factory=factory) == "failed"
    await db.refresh(t)
    assert t.engine_meta["infra_attempts"] == 3
