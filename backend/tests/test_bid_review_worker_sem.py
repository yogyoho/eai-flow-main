"""Task 14 测试:worker 集成 sem/hyb 规则 + 汇总分级(A12 T14 集成约束验收)。

覆盖面(先红后绿):sem 规则经 advance/resume 产条目落库、hyb 候选路径(det 粗筛命中
→模型确认)、need_human 单列统计口径(progress.summary 与 issues API 同口径)、
response.content 分块 list 归一 str(worker 包装层,A12 约束②)、逐规则隔离(模型
不可用/接线失败降级 need_human,兄弟规则照常)、fatal 不被模型降级、dedup 同键合并、
done 帧 progress 记录各阶段耗时;基准确认门语义不破(deep 停 awaiting_confirm 且模型
零调用,confirm 后 resume 才跑 sem)。

测试环境沿 test_bid_review_worker.py 先例:sqlite+aiosqlite 内存库定点建 bid_review
五张表;规则包 monkeypatch 成 tmp_path 最小包(不依赖生产 1.0.0.yaml 内容);模型以
fake 同步 callable 注入(advance_task/resume_confirmed 的 model_fn 参数)。
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review.worker import advance_task, resume_confirmed, summarize_issues
from app.extensions.database import Base

_TABLES = [
    models.ReviewTask.__table__,
    models.ReviewIssue.__table__,
    models.BaselinePackage.__table__,
    models.RulePackMeta.__table__,
    models.ReviewFeedback.__table__,
]

# 最小 sem/hyb/det 三型规则包:sem(S1-001 走模型)、hyb(H1-001 det 粗筛+模型确认)、
# det(D1-001 纯确定性,作兄弟规则/正式违规计数参照)。
_TMP_RULEPACK = """\
conventions:
  on_missing_input: need_human
rules:
  - id: S1-001
    name: 实质性条款逐条响应
    layer: L1
    type: semantic
    applies_to: ["*"]
    inputs: [tender.substantive_clauses]
    check:
      per_clause: true
      verdict_set: [full, partial, none, unclear]
      steps: []
    severity: fatal
    evidence: []
    message_tpl: "实质性条款 {clause_id} 响应为 {verdict}:{reason}"
    fix_tpl: 逐条补实质性响应
    confidence_gate: 0.75
    enabled: true
  - id: H1-001
    name: 业绩达标
    layer: L1
    type: hybrid
    applies_to: ["*"]
    inputs: [bid.similar_performances, tender.min_similar_performance_count]
    check:
      det_expr: "count(bid.similar_performances) >= tender.min_similar_performance_count"
      op: gte
      left: "count(bid.similar_performances)"
      right: tender.min_similar_performance_count
      verdict_set: [full, partial, none, unclear]
    severity: major
    evidence: []
    message_tpl: "类似业绩 {bid.similar_performances} 数量少于招标要求 {tender.min_similar_performance_count} 项"
    fix_tpl: 补附类似业绩证明
    confidence_gate: 0.75
    enabled: true
  - id: D1-001
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
    fix_tpl: 复核报价汇总
    confidence_gate: 1.0
    enabled: true
"""

# hyb det 粗筛通过(零候选,不进语义管线)的字段;det D1-001 干净
_FIELDS_CLEAN = {"bid.similar_performances": ["业1", "业2", "业3"], "tender.min_similar_performance_count": 3, "bid.total_price": 500, "tender.max_price": 1000}
# hyb det 粗筛命中(1 < 3,产候选交模型确认)
_FIELDS_HYB_HIT = {"bid.similar_performances": ["业绩A"], "tender.min_similar_performance_count": 3, "bid.total_price": 500, "tender.max_price": 1000}
# det 正式违规(总价超限价):汇总分级 fatal 计数参照
_FIELDS_FATAL = {"bid.similar_performances": ["业1", "业2", "业3"], "tender.min_similar_performance_count": 3, "bid.total_price": 2000000, "tender.max_price": 1000000}

# 证据锚点文本(doc_text page 1 全文;归一相似度按 verify 契约)
_DOC_TEXT = "业绩A 中标通知书 ★ 实质性条款响应表"
_DOCS = [{"doc_id": "b.pdf", "role": "bid", "text": _DOC_TEXT}]

_EV = {"doc_id": "b.pdf", "page": 1, "text": "业绩A 中标通知书"}


def _vd(*entries) -> str:
    return json.dumps({"verdicts": list(entries)}, ensure_ascii=False)


def _fake_model(responses: dict, calls: list):
    """按规则卡中「规则:<id>」路由响应的同步 fake model_fn;值为 BaseException 时抛出
    (模型不可用/接线失败),content 支持 str 与 LangChain 分块 list 双形态。"""

    def _fn(messages):
        card = messages[0]["content"]
        rid = next((r for r in responses if f"规则:{r} " in card), "?")
        calls.append(rid)
        out = responses[rid]
        if isinstance(out, BaseException):
            raise out
        return type("M", (), {"content": out})()

    return _fn


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def sem_rulepack(monkeypatch, tmp_path):
    p = tmp_path / "pack.yaml"
    p.write_text(_TMP_RULEPACK, encoding="utf-8")
    monkeypatch.setattr("app.extensions.bid_review.worker.RULEPACK_PATH", p)
    return p


def _stub_extract(monkeypatch, fields: dict) -> None:
    from app.extensions.bid_review import worker

    def _extract(d, p):
        return {**{k: None for k in p}, **fields}

    monkeypatch.setattr(worker, "_default_extract_fn", lambda: _extract)


# ── sem 规则管线落库 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_sem_rule_produces_persisted_issue(db, sem_rulepack):
    """plan Task 14 Step 1:quick 直跑对 sem 规则跑 run_sem_rule(fake model 注入),
    模型 verdict=none(未响应)→ violation 条目落库(clause_id/dedup_key/engine 侧
    fatal 严重度);hyb det 通过零候选零模型调用(调用序列仅 S1-001)。"""
    calls: list[str] = []
    model = _fake_model({"S1-001": _vd({"clause_id": "★1", "verdict": "none", "confidence": 0.9, "reason": "未实质性响应", "evidence": [_EV]})}, calls)
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    assert calls == ["S1-001"], f"sem 规则应调用模型、hyb det 通过零候选不得调用,实际 {calls}"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    assert len(issues) == 1
    row = issues[0]
    assert row.rule_id == "S1-001" and row.verdict == "violation" and row.severity == "fatal"
    assert row.clause_id == "★1" and row.dedup_key, "sem 条目应携带 clause_id 与 verify 层 dedup_key"


@pytest.mark.asyncio
async def test_hyb_candidate_confirmed_by_model(db, sem_rulepack):
    """hyb 候选路径(A12 §4.4 全文语义:「hybrid:先 det 粗筛,候选进 LLM 判定」):
    det 粗筛命中(1<3)产候选交模型确认,模型 none=确认违规 → violation 条目落库。"""
    calls: list[str] = []
    model = _fake_model(
        {
            "S1-001": _vd({"clause_id": "★1", "verdict": "full", "confidence": 0.95, "reason": "已完整响应", "evidence": [_EV]}),
            "H1-001": _vd({"clause_id": "-", "verdict": "none", "confidence": 0.9, "reason": "业绩数量不足坐实", "evidence": [_EV]}),
        },
        calls,
    )
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_HYB_HIT}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    assert sorted(calls) == ["H1-001", "S1-001"], "hyb det 命中候选应进模型确认"
    by_rule = {i.rule_id: i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1")}
    assert by_rule["H1-001"].verdict == "violation" and by_rule["H1-001"].severity == "major", "模型确认候选后应产 violation(粗筛不再短路终局)"
    assert "S1-001" not in by_rule, "模型 full=干净条款不产条目"


@pytest.mark.asyncio
async def test_hyb_unclear_need_human_survives_pipeline(db, sem_rulepack):
    """A12 γ 回归门(集成级):hyb 候选模型判 unclear → need_human 条目必须存活出管线
    落库(不得静默 refuted),并在汇总分级中单列待人工。"""
    model = _fake_model(
        {
            "S1-001": _vd({"clause_id": "★1", "verdict": "full", "confidence": 0.95, "reason": "已完整响应", "evidence": [_EV]}),
            "H1-001": _vd({"clause_id": "-", "verdict": "unclear", "confidence": 0.9, "reason": "材料不足以判定业绩有效性", "evidence": [_EV]}),
        },
        [],
    )
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_HYB_HIT}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    hyb = [i for i in issues if i.rule_id == "H1-001"]
    assert hyb and hyb[0].need_human is True and hyb[0].verdict == "unclear", "unclear+need_human 条目必须存活出管线"
    assert task.progress["summary"]["need_human"] >= 1, "待人工条目应单列进汇总待人工计数"


# ── 汇总分级(A12 T14 约束①)─────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_grades_need_human_separately(db, sem_rulepack):
    """need_human 单列统计口径:正式违规计数(fatal/major/minor/info)不含 need_human
    条目,待人工单列;条目不删(仍全量落库)。det 正式 fatal 违规 + sem unclear 待人工。"""
    model = _fake_model(
        {"S1-001": _vd({"clause_id": "★1", "verdict": "unclear", "confidence": 0.9, "reason": "材料不足", "evidence": [_EV]})},
        [],
    )
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_FATAL}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    assert {(i.rule_id, i.need_human) for i in issues} == {("D1-001", False), ("S1-001", True)}, "条目不删:正式违规与待人工条目都落库"
    assert task.progress["summary"] == {"fatal": 1, "major": 0, "minor": 0, "info": 0, "need_human": 1}, "致命计数不含 need_human 条目(sem fatal 条目入待人工,不入 fatal)"


def test_summarize_issues_accepts_orm_and_dict():
    """summarize_issues 双形态(ORM 行/引擎 dict)与 worker progress、issues API 共用,
    两侧口径一致;未知严重度按 info 兜底计。"""

    class Row:
        severity = "minor"
        need_human = False

    assert summarize_issues([Row(), {"severity": "fatal", "need_human": False}, {"severity": "fatal", "need_human": True}, {"severity": "?", "need_human": False}]) == {
        "fatal": 1,
        "major": 0,
        "minor": 1,
        "info": 1,
        "need_human": 1,
    }


# ── 模型接线包装(A12 T14 约束②)─────────────────────────────────────


@pytest.mark.asyncio
async def test_content_chunk_list_normalized_to_str(db, sem_rulepack):
    """response.content 分块 list 归一(LangChain 分块形态:list 时拼接各 text 部件)
    在 worker 模型包装层完成——不归一则 check_schema 两试皆败→整规则静默空产出。"""
    chunk_a = '{"verdicts": [{"clause_id": "★1", "verdict": "none", "confidence": 0.9,'
    chunk_b = ' "reason": "未实质性响应", "evidence": [{"doc_id": "b.pdf", "page": 1, "text": "业绩A 中标通知书"}]}]}'
    model = _fake_model({"S1-001": [{"type": "text", "text": chunk_a}, {"type": "text", "text": chunk_b}]}, [])
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    issues = [i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1") if i.rule_id == "S1-001"]
    assert len(issues) == 1 and issues[0].verdict == "violation", "分块 list content 应拼接归一为 str 后正常过 schema"


# ── 逐规则隔离 + 生产缺口 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_crash_isolated_to_need_human(db, sem_rulepack):
    """T9 先例(9cda4828b)扩展到 sem:模型不可用/接线失败(抛异常)该规则降级
    need_human 条目,兄弟 det 规则照常产出(fatal violation),任务照常 done(禁整任务崩)。"""
    model = _fake_model({"S1-001": RuntimeError("model endpoint down")}, [])
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_FATAL}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done", "单规则模型异常不得把任务打 failed"
    by_rule = {i.rule_id: i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1")}
    assert by_rule["S1-001"].need_human is True and by_rule["S1-001"].verdict == "need_human"
    assert by_rule["D1-001"].verdict == "violation", "兄弟 det 规则不受模型异常影响,应照常产出 violation"


@pytest.mark.asyncio
async def test_default_model_gap_degrades_sem_rule_not_crash(db, sem_rulepack, monkeypatch):
    """无可用模型(config 空且 env 未设)时 _default_model_fn 退化为显式缺口 → sem
    规则逐规则降级 need_human 而非崩任务——绝不静默假交付(生产模型接线落地后,
    本测试锁的是无模型回退路径,monkeypatch 空配置使判定确定性)。"""
    from types import SimpleNamespace

    monkeypatch.setattr("deerflow.config.get_app_config", lambda: SimpleNamespace(models=[]))
    monkeypatch.delenv("EAI_BID_REVIEW_MODEL", raising=False)
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False)
    assert task.status == "done"
    by_rule = {i.rule_id: i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1")}
    assert by_rule["S1-001"].need_human is True, "未接线模型下 sem 规则应显式降级 need_human"


@pytest.mark.asyncio
async def test_model_fatal_not_downgraded_and_dedup_merged(db, sem_rulepack):
    """plan Task 14 Step 1 断言:fatal 不被模型降级(模型侧 severity=minor,规则定义
    fatal 为准);dedup 同键合并(同 clause 同 doc 两条 verdict → 单行多证据)。"""
    entry = {"clause_id": "★1", "verdict": "none", "confidence": 0.9, "reason": "未实质性响应", "severity": "minor", "evidence": [_EV]}
    entry2 = {**entry, "evidence": [{"doc_id": "b.pdf", "page": 2, "text": "实质性条款响应表"}]}
    model = _fake_model({"S1-001": _vd(entry, entry2)}, [])
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    rows = [i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1") if i.rule_id == "S1-001"]
    assert len(rows) == 1, "同 dedup_key 两条模型 verdict 应合并为单行"
    assert rows[0].severity == "fatal", "模型侧 minor 不得降级规则定义的 fatal(normalize_severity)"
    assert len(rows[0].evidence) == 2, "合并条目应保留多证据"


# ── 确认门语义不破 + 各阶段耗时 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_deep_gate_stops_before_model_then_resume_runs_sem(db, sem_rulepack):
    """基准确认门语义不破(T15 已锁,勿碰):deep 任务停 awaiting_confirm 且 sem 模型
    零调用;confirm 后 resume_confirmed 才对 sem 规则跑 run_sem_rule,done 帧 progress
    记录 review 阶段耗时与汇总分级。"""
    calls: list[str] = []
    model = _fake_model({"S1-001": _vd({"clause_id": "★1", "verdict": "none", "confidence": 0.9, "reason": "未实质性响应", "evidence": [_EV]})}, calls)
    t = await crud.create_task(db, owner_id="u1", mode="deep")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=True, model_fn=model)
    assert task.status == "awaiting_confirm"
    assert calls == [], "确认门前不得跑 sem 规则(模型零调用)"

    done = await resume_confirmed(db, t.id, "u1", model_fn=model)
    assert done.status == "done"
    assert calls == ["S1-001"], "确认后 sem 规则应进模型管线"
    assert isinstance(done.progress["durations"].get("review"), (int, float)) and done.progress["durations"]["review"] >= 0
    issues = [i for i in await crud.list_issues(db, task_id=t.id, owner_id="u1") if i.rule_id == "S1-001"]
    assert len(issues) == 1 and issues[0].verdict == "violation"


@pytest.mark.asyncio
async def test_quick_done_progress_records_stage_durations(db, sem_rulepack):
    """quick 直跑 done 帧:progress.durations 记录 parsing/extracting/review 各阶段耗时
    (数值、≥0);summary 与落库条目同口径。"""
    model = _fake_model({"S1-001": _vd({"clause_id": "★1", "verdict": "full", "confidence": 0.95, "reason": "已完整响应", "evidence": [_EV]})}, [])
    t = await crud.create_task(db, owner_id="u1")

    def _extract(d, p):
        return {**{k: None for k in p}, **_FIELDS_CLEAN}

    task = await advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=_extract, wait_confirm=False, model_fn=model)
    assert task.status == "done"
    durations = task.progress["durations"]
    assert {"parsing", "extracting", "review"} <= set(durations), f"各阶段耗时缺项:{durations}"
    assert all(isinstance(v, (int, float)) and v >= 0 for v in durations.values())
    assert task.progress["summary"]["need_human"] == 0 and task.progress["summary"]["fatal"] == 0, "干净案汇总应全零"
