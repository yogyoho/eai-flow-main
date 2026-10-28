"""Task 9 测试:bid_review worker——状态机推进(advance_task)+ boot recovery +
infra 失败链 + 确认门续跑(resume_confirmed)。sqlite+aiosqlite 内存库,advance 直注
测试 session/extract_fn(translation worker 可注入惯例);det 规则包 monkeypatch 成
tmp_path 内最小包(不依赖生产 1.0.0.yaml 内容)。

fix-round(2026-10-29 评审):补 claim 路径回归门——_claim_next/_run_claimed/
bid_review_claimer_loop 全链(评审 missing#4:_claim_next 置 parsing 后 advance_task
以 created 入口二次置换守卫零命中早退,claimed 任务死锁 parsing,MCP start 任务全
悬挂;重投链同坑)。claim 系测试自建 StaticPool 引擎(claimer 自开短会话,内存库
须共享单连接);sqlite 无 FOR UPDATE SKIP LOCKED 方言,实现按 dialect 注入锁子句。

偏离 plan 字面(同 test_bid_review_crud.py 先例):共享 Base 跨模块 FK 在 DDL 排序时炸,
只定点建 bid_review 五张表(FK 闭包在集合内)。
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review.worker import advance_task, boot_recovery, resume_confirmed
from app.extensions.database import Base

_TABLES = [
    models.ReviewTask.__table__,
    models.ReviewIssue.__table__,
    models.BaselinePackage.__table__,
    models.RulePackMeta.__table__,
    models.ReviewFeedback.__table__,
]

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
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def claim_env():
    """claim 路径测试环境(_claim_next/_run_claimed/claimer_loop 自开短会话):
    sqlite :memory: 每连接独立库,须 StaticPool 共享单连接,claimer 的短会话才能
    看见测试写入的任务行。"""
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _stub_extract(monkeypatch, fields: dict) -> None:
    """_run_claimed 内部取 worker._default_extract_fn() 装配,monkeypatch 模块函数
    注入字段快照(未声明的提取路径填 None 走 need_human 通路)。"""
    from app.extensions.bid_review import worker

    def _extract(d, p):
        return {**{k: None for k in p}, **fields}

    monkeypatch.setattr(worker, "_default_extract_fn", lambda: _extract)


_DOCS = [{"doc_id": "b.pdf", "role": "bid", "text": "x"}]
_FIELDS = {"bid.total_price": 2000000, "tender.max_price": 1000000, "bid.price_includes_tax": True, "tender.price_includes_tax": True}


async def _mk_docs_task(factory) -> str:
    """建一个带上传文档(engine_meta.docs,worker._load_docs 取数源)的 quick 任务。"""
    async with factory() as s:
        t = await crud.create_task(s, owner_id="u1")
        t.engine_meta = {"docs": _DOCS}
        await s.commit()
        return t.id


@pytest.fixture
def tmp_rulepack(monkeypatch, tmp_path):
    p = tmp_path / "pack.yaml"
    p.write_text(_TMP_RULEPACK, encoding="utf-8")
    monkeypatch.setattr("app.extensions.bid_review.worker.RULEPACK_PATH", p)
    return p


_CRASH_RULEPACK = """\
conventions:
  on_missing_input: need_human
rules:
  - id: T1-101
    name: 测试类型偏差规则求值崩溃
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
    fix_tpl: 复核报价汇总
    confidence_gate: 1.0
    enabled: true
  - id: T1-102
    name: 测试兄弟规则照常执行
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.subtotal, bid.total_price]
    check:
      op: eq
      left: bid.subtotal
      right: bid.total_price
    severity: major
    evidence: []
    message_tpl: "合计 {bid.subtotal:money} 与总价 {bid.total_price:money} 不一致"
    fix_tpl: 重算合计
    confidence_gate: 1.0
    enabled: true
"""


@pytest.fixture
def crash_rulepack(monkeypatch, tmp_path):
    p = tmp_path / "crash.yaml"
    p.write_text(_CRASH_RULEPACK, encoding="utf-8")
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
async def test_rule_crash_isolated_to_need_human(db, crash_rulepack):
    """fix-round 评审项:单规则求值意外(KeyError 之外,如 str 与 float 比较 TypeError)被
    _run_det_stage 逐规则隔离降级 need_human——兄弟规则照常执行、任务照常到 done;
    禁止单个字段类型偏差把整条审查任务经 _infra_fail 重试 3 次打 failed(可用性失败)。"""
    t = await crud.create_task(db, owner_id="u1")
    fields = {"bid.total_price": "一百万整", "tender.max_price": 1000000, "bid.subtotal": 999}

    def _extract(d, p):
        return {**{k: None for k in p}, **fields}

    task = await advance_task(db, t.id, owner_id="u1", docs=[], extract_fn=_extract, wait_confirm=False)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    by_rule = {i.rule_id: i for i in issues}
    assert by_rule["T1-101"].verdict == "need_human" and by_rule["T1-101"].need_human is True, "崩溃规则应逐规则隔离降级 need_human"
    assert by_rule["T1-102"].verdict == "violation", "兄弟规则不受单规则崩溃影响,应照常产出 violation"


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


# ── fix-round(2026-10-29 评审)claim 路径回归门 ─────────────────────────


@pytest.mark.asyncio
async def test_claim_next_and_run_claimed_process_created_task(claim_env, tmp_rulepack, monkeypatch):
    """评审 missing#1:_claim_next 领取 created(置 parsing 领取标记)→ _run_claimed 以
    parsing(claimer 已持有)入口直进管线 → done。旧实现返回 entry=created,advance_task
    守卫二次置换 created→parsing 零命中早退,任务死锁 parsing——created 领取路径不可用。"""
    from app.extensions.bid_review import worker

    monkeypatch.setattr(worker, "get_session_factory", lambda: claim_env)
    _stub_extract(monkeypatch, _FIELDS)
    task_id = await _mk_docs_task(claim_env)

    claimed = await worker._claim_next(claim_env)
    assert claimed is not None and claimed[0] == task_id, "created 任务应被领取"
    assert claimed[1] == "parsing", "领取标记态 parsing 应作为 advance_task 的已持有入口返回"
    final = await worker._run_claimed(task_id, claimed[1])
    assert final == "done", f"领取任务应跑完整管线到 done,实际 {final}"
    async with claim_env() as s:
        row = await crud.get_task(s, task_id, "u1")
        assert row.status == "done"
        assert {i.rule_id for i in await crud.list_issues(s, task_id=task_id, owner_id="u1")} == {"T1-001", "T1-002"}


@pytest.mark.asyncio
async def test_claimer_loop_processes_created_task_to_done(claim_env, tmp_rulepack, monkeypatch):
    """评审 Consequence A 回归门:MCP bid_review_start 仅建任务,常驻 claimer 是 created
    任务唯一引擎——bid_review_claimer_loop 端到端把 created 任务跑到 done。"""
    from app.extensions.bid_review import worker

    monkeypatch.setattr(worker, "get_session_factory", lambda: claim_env)
    monkeypatch.setattr(worker, "POLL_SECONDS", 0.01)
    _stub_extract(monkeypatch, _FIELDS)
    task_id = await _mk_docs_task(claim_env)

    stop = asyncio.Event()
    loop_task = asyncio.create_task(worker.bid_review_claimer_loop(stop))
    done = False
    for _ in range(100):
        await asyncio.sleep(0.05)
        async with claim_env() as s:
            row = await crud.get_task(s, task_id, "u1")
            if row is not None and row.status == "done":
                done = True
                break
    stop.set()
    await asyncio.wait_for(loop_task, timeout=5)
    assert done, "claimer loop 应在时限内把 created 任务跑到 done(旧实现死锁 parsing)"


@pytest.mark.asyncio
async def test_infra_requeued_created_task_is_reclaimed_to_done(claim_env, tmp_rulepack, monkeypatch):
    """评审 Consequence B 回归门:_infra_fail 回 created 重投(attempts<3)的任务必须可被
    再领取并跑完——旧实现重投任务领取后同样死锁 parsing,重投链从未兑现。"""
    from app.extensions.bid_review import worker

    monkeypatch.setattr(worker, "get_session_factory", lambda: claim_env)

    def _boom(d, p):
        raise RuntimeError("boom-extract")

    monkeypatch.setattr(worker, "_default_extract_fn", lambda: _boom)
    task_id = await _mk_docs_task(claim_env)

    claimed = await worker._claim_next(claim_env)
    assert claimed is not None and claimed[1] == "parsing"
    with pytest.raises(RuntimeError):
        await worker._run_claimed(task_id, claimed[1])
    assert await worker._infra_fail(task_id, RuntimeError("boom-extract"), "pipeline", factory=claim_env) == "created", "attempts<3 应回 created 重投"

    _stub_extract(monkeypatch, _FIELDS)  # 故障恢复后重投任务应能跑完
    claimed2 = await worker._claim_next(claim_env)
    assert claimed2 is not None and claimed2[0] == task_id, "重投的 created 任务应可被再领取"
    assert await worker._run_claimed(task_id, claimed2[1]) == "done"
    async with claim_env() as s:
        row = await crud.get_task(s, task_id, "u1")
        assert row.status == "done"
        assert row.engine_meta.get("infra_attempts") == 1, "重试计数应保留"


@pytest.mark.asyncio
async def test_claimer_loop_requeue_reaches_terminal_failed(claim_env, tmp_rulepack, monkeypatch):
    """评审 Consequence B 终态回归门:基础设施失败经 claimer 重投链——attempts<3 回
    created 重投、超限 → failed 终态 + error 落库(重试语义经重投真实兑现,任务不悬挂)。"""
    from app.extensions.bid_review import worker

    monkeypatch.setattr(worker, "get_session_factory", lambda: claim_env)
    monkeypatch.setattr(worker, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "MAX_INFRA_RETRIES", 2)  # 加速:2 次即终态

    def _boom(d, p):
        raise RuntimeError("boom-extract")

    monkeypatch.setattr(worker, "_default_extract_fn", lambda: _boom)
    task_id = await _mk_docs_task(claim_env)

    stop = asyncio.Event()
    loop_task = asyncio.create_task(worker.bid_review_claimer_loop(stop))
    failed = False
    for _ in range(100):
        await asyncio.sleep(0.05)
        async with claim_env() as s:
            row = await crud.get_task(s, task_id, "u1")
            if row is not None and row.status == "failed":
                failed = True
                break
    stop.set()
    await asyncio.wait_for(loop_task, timeout=5)
    assert failed, "claimer loop 重投链应在超限后把任务打到 failed 终态"
    async with claim_env() as s:
        row = await crud.get_task(s, task_id, "u1")
        assert row.engine_meta.get("infra_attempts") == 2
        assert "boom" in (row.error or "")


@pytest.mark.asyncio
async def test_boot_recovery_resets_parsing_to_extracting(db):
    """fix-round 评审项:parsing 是 claim 领取标记,进程死亡窗口会遗留 parsing 任务——
    boot recovery 与 running 一并重置 extracting(断点续跑),claim 领取态不留死态。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.set_status(db, t, "parsing")
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    assert await boot_recovery(factory) == 1
    await db.refresh(t)
    assert t.status == "extracting"
