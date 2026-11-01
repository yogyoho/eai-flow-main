# Plan 10 — /rules + /metrics 治理页 M5(spec §4.7/§4.8)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 规则库(/rules)与治理看板(/metrics)对齐 spec §4.7/§4.8——B5 规则定义五块抽屉 + 判定算子列 + 层级 seg(全部/L1 实质性/L3 一致性/高误报),B6 FAIL 归因 + 近 6 周误报率趋势,以及 s9↔s10 互跳(高误报段→FAIL 名单锚点,FAIL 行→规则库深链)。

**Architecture:** 后端两个只读端点族:① `GET /rulepacks/{name}/rules`(B5)从已加载生产包投影五块明细(PRECONDITION/EXPR/ON_MISSING_INPUT/MESSAGE_TPL/FIX_TPL)+ `op` 归一(steps 链形态归 "steps"),同时 list_rulepacks 规则投影加 `op`(共享表列);② `GET /metrics/fail_attribution` + `GET /metrics/trends`(B6)从 ReviewFeedback(经 ReviewIssue join 拿 rule_id)聚合,治理域口径同 GET /rulepacks(全库聚合,owner 仅作鉴权)。前端 RulesView 换 seg 词汇 + 抽屉 + 深链(`?rule=`),MetricsView 加锚点/归因 foot/趋势卡/行级互跳。

**Tech Stack:** FastAPI + SQLAlchemy(async)/ pytest+httpx ASGITransport;Next.js 16 / TanStack Query / rstest(.dom.tsx happy-dom)。

**Spec:** docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md §4.7(s9 规则库)、§4.8(s10 看板)、§5 B5/B6 行、§7 里程碑(B5/B6 先于 M5);原型 docs/designs/2026-10-30-bid-review-ui.html s9/s10/ruleDrawer。生产包事实:bid-review-core 1.0.0.yaml,32 规则,layer∈{L1,L3},op∈{lte,gte,eq,and,all,set_eq} 或 steps 链(无 op 键),conventions.on_missing_input=need_human。误报原因折 note 约定 = `误报原因:<四因>;[备注]`(frontend FP_REASONS = 规则误判/证据错位/口径理解不同/基准抽取错误)。

**行为契约不变:** 规则包只读(修订须走版本发布,本页零写路径);伪零纪律(空周 rate=null 不画 0%、无归因不编原因);stats 全库口径(误报率=fp/hit,高误报=hit>0 且 fp/hit≥0.2,rulepack-ui.isHighFp 既有实现)。

---

### Task 1: B5+B6 后端(op 投影 + 五块明细端点 + FAIL 归因 + 周趋势)

**Files:**
- Modify: `backend/app/extensions/bid_review/routers.py`(imports + `_rule_op` + list_rulepacks 投影 + 三端点)
- Create: `backend/tests/test_bid_review_metrics.py`

- [x] **Step 1: 写失败测试** — 新建 `backend/tests/test_bid_review_metrics.py`(夹具照 test_bid_review_feedback.py:ASGITransport 子应用 + current_owner/get_db 双 override + 五张表定点建表):

```python
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

_KNOWN_OPS = {"lte", "gte", "eq", "and", "all", "set_eq", "steps"}


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
        db, task_id=t.id, owner_id="u1", rule_id=rule_id, layer="L1", severity="fatal",
        verdict="violation", message="投标总价 ¥101 超过最高限价 ¥100", dedup_key=dedup_key, need_human=False,
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
    this_monday = datetime.now(UTC).date() - timedelta(days=datetime.now(UTC).weekday())
    cur = by_start[this_monday.isoformat()]
    assert cur["confirmed"] == 1 and cur["fp"] == 0 and cur["rate"] == 0.0
    back_monday = (back.date() - timedelta(days=back.date().weekday())).isoformat()
    assert by_start[back_monday]["fp"] == 1 and by_start[back_monday]["rate"] == 100.0
    assert sum(1 for w in weeks if w["rate"] is None) == 4
```

- [x] **Step 2: 跑红** — `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_metrics.py -v`;预期 404/KeyError FAIL。

- [x] **Step 3: 实现** — routers.py 四处:

(a) imports:`from datetime import UTC, datetime` → `from datetime import UTC, datetime, timedelta`;models 行 → `from app.extensions.bid_review.models import ReviewFeedback, ReviewIssue, RulePackMeta`。

(b) list_rulepacks 上方加助手 + 规则投影加 op:

```python
def _rule_op(chk: dict) -> str | None:
    """判定算子投影(B5,M5 §4.7):op 形态回白名单原值,steps 链形态归一 "steps"
    (表列 mono 展示;加载器保证非 steps 必有 op)。"""
    if "steps" in chk:
        return "steps"
    return chk.get("op")
```

list_rulepacks 的 rules 行加 `"op": _rule_op(r.check or {})`(inputs 之后)。

(c) list_rulepacks 之后加 B5 端点:

```python
@router.get("/rulepacks/{name}/rules")
async def rulepack_rule_details(name: str, owner_id: str = Depends(current_owner)):
    """规则定义五块明细(B5,M5 §4.7,治理页只读抽屉):PRECONDITION / EXPR /
    ON_MISSING_INPUT / MESSAGE_TPL / FIX_TPL。EXPR 取 steps/all/values 链或
    `left op right` 单式;on_missing_input 从包级 conventions 投影到每条。本页零写
    路径——修订须走规则包版本发布;name 不匹配生产包 404(当前单包 bid-review-core)。"""
    pack = worker.load_rulepack(worker.RULEPACK_PATH)
    if name != pack.name:
        raise HTTPException(status_code=404, detail=f"未知规则包 {name}")
    items = []
    for r in pack.rules:
        chk = r.check or {}
        if "steps" in chk:
            expr_lines = [str(e) for e in chk.get("steps", [])]
        elif "all" in chk:
            expr_lines = [str(e) for e in chk.get("all", [])]
        elif "values" in chk:
            expr_lines = [str(e) for e in chk.get("values", [])]
        else:
            expr_lines = [f"{chk.get('left', '')} {chk.get('op', '')} {chk.get('right', '')}"]
        items.append(
            {
                "id": r.id,
                "name": r.name,
                "layer": r.layer,
                "severity": r.severity,
                "type": r.type,
                "op": _rule_op(chk),
                "precondition": str(chk["precondition"]) if "precondition" in chk else None,
                "expr_lines": expr_lines,
                "on_missing_input": str(pack.conventions.get("on_missing_input") or "") or None,
                "message_tpl": r.message_tpl,
                "fix_tpl": r.fix_tpl,
                "evidence": list(r.evidence or []),
            }
        )
    return {"pack": {"name": pack.name, "version": pack.version}, "items": items}
```

(d) B6 两端点 + 归因助手(紧随其后):

```python
@router.get("/metrics/fail_attribution")
async def metrics_fail_attribution(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """FAIL 归因(B6,M5 §4.8):false_positive 反馈经 ReviewIssue join 取 rule_id,
    按规则聚合误报原因(note 首段「误报原因:X」折进约定,到首个分号止;无前缀 →
    未归因,不伪造)。治理域口径同 GET /rulepacks:全库聚合,owner 仅作鉴权。"""
    rows = (
        await db.execute(
            select(ReviewIssue.rule_id, ReviewFeedback.note)
            .join(ReviewFeedback, ReviewFeedback.issue_id == ReviewIssue.id)
            .where(ReviewFeedback.action == "false_positive")
        )
    ).all()
    agg: dict[str, dict[str, int]] = {}
    for rule_id, note in rows:
        reason = _fp_reason_of(note)
        bucket = agg.setdefault(rule_id, {})
        bucket[reason] = bucket.get(reason, 0) + 1
    items = [
        {
            "rule_id": rid,
            "total": sum(counts.values()),
            "reasons": [{"reason": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda kv: -kv[1])],
        }
        for rid, counts in sorted(agg.items(), key=lambda kv: -sum(kv[1].values()))
    ]
    return {"items": items}


def _fp_reason_of(note: object) -> str:
    """误报原因折 note 约定(工作台/结果页同口径):「误报原因:」后到首个分号止;
    无前缀或空白 → 未归因。"""
    s = str(note or "")
    if s.startswith("误报原因:"):
        return s[len("误报原因:"):].split(";")[0].strip() or "未归因"
    return "未归因"


@router.get("/metrics/trends")
async def metrics_trends(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """近 6 周误报率趋势(B6,M5 §4.8):ReviewFeedback 按自然周(周一始)分桶,
    周误报率 = false_positive / (false_positive + confirm);其余动作不进分母。
    空周 rate=None——伪零纪律:无回流数据的周不给 0%。"""
    fbs = (await db.execute(select(ReviewFeedback).where(ReviewFeedback.action.in_(("false_positive", "confirm"))))).scalars().all()
    today = datetime.now(UTC).date()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=i) for i in range(5, -1, -1)]
    buckets: dict = {s: [0, 0] for s in starts}
    for fb in fbs:
        d = fb.created_at.date() if fb.created_at is not None else None
        if d is None:
            continue
        mon = d - timedelta(days=d.weekday())
        if mon in buckets:
            buckets[mon][0 if fb.action == "false_positive" else 1] += 1
    weeks = []
    for s in starts:
        fp, confirmed = buckets[s]
        weeks.append(
            {
                "week_start": s.isoformat(),
                "fp": fp,
                "confirmed": confirmed,
                "rate": round(fp / (fp + confirmed) * 100, 1) if (fp + confirmed) > 0 else None,
            }
        )
    return {"weeks": weeks}
```

- [x] **Step 4: 跑绿** — 同命令 PASS;再 `PYTHONPATH=. uv run pytest tests/test_bid_review_feedback.py tests/test_bid_review_routers.py -v` 不回归。
- [x] **Step 5: 重启网关 + lint** — `docker compose -p eai-docker restart gateway`;`cd backend && make lint`(contract_price 外来 WIP 的 F401 不算);`git add app/extensions/bid_review/routers.py tests/test_bid_review_metrics.py && git commit -m "feat(bid-review): B5规则五块明细+B6 FAIL归因/周趋势端点(Plan10 T1,spec §4.7/§4.8)"`

---

### Task 2: T2 前端类型 + fetchers + hooks

**Files:**
- Modify: `frontend/src/extensions/bid-review/api.ts`
- Modify: `frontend/src/extensions/bid-review/hooks.ts`

- [x] **Step 1:** api.ts 规则包端点区(listRulepacks 之后)加:

```ts
/** GET /rulepacks/{name}/rules 行(B5 五块明细,routers.rulepack_rule_details)。 */
export interface RuleExprOut {
  id: string;
  name: string;
  layer: string;
  severity: string;
  type: string;
  /** 判定算子:lte/gte/eq/and/all/set_eq;steps 链形态归一为 "steps"。 */
  op: string | null;
  precondition: string | null;
  expr_lines: string[];
  on_missing_input: string | null;
  message_tpl: string;
  fix_tpl: string;
  evidence: string[];
}

/** GET /metrics/fail_attribution 行(B6:FAIL 规则误报原因聚合,次数降序)。 */
export interface FailAttrItem {
  rule_id: string;
  total: number;
  reasons: { reason: string; count: number }[];
}

/** GET /metrics/trends 行(B6:近 6 周误报率;rate null=该周无回流,伪零纪律)。 */
export interface TrendWeek {
  week_start: string;
  fp: number;
  confirmed: number;
  rate: number | null;
}
```

```ts
/** GET /rulepacks/{name}/rules —— 规则定义五块明细(B5;当前单包 bid-review-core)。 */
export function fetchRuleExprs(name: string): Promise<RuleExprOut[]> {
  return request<{ items: RuleExprOut[] }>(`/rulepacks/${name}/rules`).then((r) => r.items);
}

/** GET /metrics/fail_attribution —— FAIL 规则误报原因聚合(B6,治理域全库口径)。 */
export function fetchFailAttribution(): Promise<FailAttrItem[]> {
  return request<{ items: FailAttrItem[] }>("/metrics/fail_attribution").then((r) => r.items);
}

/** GET /metrics/trends —— 近 6 周误报率(B6)。 */
export function fetchBidTrends(): Promise<TrendWeek[]> {
  return request<{ weeks: TrendWeek[] }>("/metrics/trends").then((r) => r.weeks);
}
```

- [x] **Step 2:** hooks.ts — bidReviewKeys 加三键;import 增 fetchBidTrends/failAttribution fetchers;末尾加三 hook:

```ts
  ruleExprs: (name: string) => ["bid-review", "ruleExprs", name] as const,
  failAttribution: ["bid-review", "failAttribution"] as const,
  trends: ["bid-review", "trends"] as const,
```

```ts
/** GET /rulepacks/{name}/rules(B5)——规则库抽屉数据源;RulesView 挂载即取(32 条小表)。 */
export function useBidRuleExprs(name: string | null) {
  return useQuery({
    queryKey: bidReviewKeys.ruleExprs(name ?? ""),
    queryFn: () => fetchRuleExprs(name ?? ""),
    enabled: !!name,
  });
}

/** GET /metrics/fail_attribution(B6)——看板 FAIL 归因 foot。 */
export function useBidFailAttribution() {
  return useQuery({ queryKey: bidReviewKeys.failAttribution, queryFn: fetchFailAttribution });
}

/** GET /metrics/trends(B6)——看板近 6 周误报率。 */
export function useBidTrends() {
  return useQuery({ queryKey: bidReviewKeys.trends, queryFn: fetchBidTrends });
}
```

- [x] **Step 3: 跑绿** — `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep "error TS" | grep -cv "contract-price"` 计数不增(基线 9 全在 contract-price)。
- [x] **Step 4: 提交** — `git add src/extensions/bid-review/api.ts src/extensions/bid-review/hooks.ts && git commit -m "feat(bid-review): B5/B6前端类型+fetchers+hooks(Plan10 T2)"`

---

### Task 3: T3 RulesView 层级 seg + 判定列 + 规则抽屉 + 互跳/深链

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/rulepack-ui.tsx`(RuleStatsRow.op + 判定列 + onRuleClick)
- Modify: `frontend/src/extensions/bid-review/components/RulesView.tsx`(seg 词汇 + 抽屉 + 互跳)
- Modify: `frontend/src/app/bid-review/rules/page.tsx`(Suspense 包裹,useSearchParams 前置要求)
- Test: `frontend/tests/unit/extensions/bid-review-rulepack-views.dom.test.tsx`

- [x] **Step 1: 写失败测试** — 测试文件改造 + 追加:
  (a) 模块顶加 `let mockParams = new URLSearchParams();`,next/navigation mock 补 `useSearchParams: () => mockParams;`,beforeEach 重置 `mockParams = new URLSearchParams();`;
  (b) PACK 夹具三条规则各加 `op: "lte" | "steps" | "gte"`;responder 改按路径分流(rulepacks → packPayload,`/rules` → EXPRS,`/metrics/fail_attribution` → ATTR,`/metrics/trends` → TRENDS);
  (c) 既有「sem 1」type-seg 测试改写为层级 seg(点「L1 实质性」→ 仅 L1 规则);
  (d) 新测试:

```tsx
  it("M5 §4.7:判定算子列+规则定义抽屉五块(B5)+修订走版本发布 foot;层级 seg 高误报段互跳", async () => {
    renderRules();
    // 判定列:mono 算子(steps 归一)
    expect(await screen.findByText("判定")).toBeTruthy();
    expect(screen.getAllByText("steps").length).toBeGreaterThan(0);
    // 点规则 id → 抽屉五块
    fireEvent.click(screen.getByText("R-001"));
    expect(await screen.findByText("PRECONDITION")).toBeTruthy();
    expect(screen.getByText(/EXPR · lte/)).toBeTruthy();
    expect(screen.getByText("MESSAGE_TPL")).toBeTruthy();
    expect(screen.getByText("FIX_TPL")).toBeTruthy();
    expect(screen.getByText(/修订须走规则包版本发布/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.queryByText("MESSAGE_TPL")).toBeNull();
    // 高误报段 → 看板 FAIL 名单锚点(互跳①)
    fireEvent.click(screen.getByRole("button", { name: /高误报/ }));
    expect(await screen.findByText(/查看 FAIL 名单/)).toBeTruthy();
    const link = screen.getByText("查看 FAIL 名单").closest("a");
    expect(link!.getAttribute("href")).toBe("/bid-review/metrics#fail-list");
  });

  it("M5 §4.7:?rule= 深链直达抽屉(互跳②反向,FAIL 行→规则库)", async () => {
    mockParams = new URLSearchParams("rule=R-002");
    renderRules();
    expect(await screen.findByText("规则定义 · R-002")).toBeTruthy();
    expect(await screen.findByText("MESSAGE_TPL")).toBeTruthy();
  });
```

(EXPRS 夹具 = `{pack:{name:"bid-review-core",version:"1.0.0"},items:[R-001 op lte precondition/expr_lines/message_tpl/fix_tpl 全量, R-002 op steps, R-003 op gte]}`,形状照 RuleExprOut。)

- [x] **Step 2: 跑红** — `pnpm test bid-review-rulepack-views`;预期 FAIL。

- [x] **Step 3: 实现** —

(a) rulepack-ui.tsx:`RuleStatsRow` 加 `op?: string | null;`;RuleStatsTable props 加 `onRuleClick?: (id: string) => void;`;表头「严重度」后插 `<th>判定</th>`;行内对应位置插 `<td><code className="k">{row.op ?? "—"}</code></td>`;规则 id 单元格在 onRuleClick 存在时渲染为可点:

```tsx
<td>
  {onRuleClick ? (
    <button type="button" className="k" style={{ cursor: "pointer" }} onClick={() => onRuleClick(row.key)}>
      {row.key}
    </button>
  ) : (
    <code className="k">{row.key}</code>
  )}
</td>
```

(b) RulesView.tsx:
- import 增 `useSearchParams`(next/navigation)、`useBidRuleExprs`(hooks)、`isHighFp`(rulepack-ui,已有则免)、`type RulePackRule`/`type RuleExprOut`(api)。
- TYPE_FILTERS/FILTER_LABELS 替换为:

```ts
// M5 §4.7:seg 从类型词汇换层级词汇——L1 实质性 / L3 一致性 / 高误报(误报率≥20%)
const LAYER_FILTERS = ["all", "L1", "L3", "highfp"] as const;
type LayerFilter = (typeof LAYER_FILTERS)[number];
const LAYER_LABELS: Record<LayerFilter, string> = { all: "全部", L1: "L1 实质性", L3: "L3 一致性", highfp: "高误报" };
```

- 组件内:`const searchParams = useSearchParams();` + `const [drawerRule, setDrawerRule] = useState<string | null>(() => searchParams.get("rule"));`(深链只读一次,懒初始化);`const exprQuery = useBidRuleExprs(pack?.name ?? null);`(pack 为既有规则包状态变量,以实际命名为准)。
- seg 过滤谓词换:`f === "all" ? true : f === "highfp" ? isHighFp(pack.stats[r.id]) : r.layer === f`;段计数同谓词;aria-label 改「层级筛选」。
- 高误报段激活时 seg 行下插互跳 note-bar(互跳①):

```tsx
{layer === "highfp" ? (
  <div className="note-bar warnbar" style={{ margin: "10px 16px 0" }}>
    <span style={{ flex: 1 }}>高误报段:误报率 ≥ 20% 且有命中的规则——先到看板确认 FAIL 归因,再决定是否修订。</span>
    <Link href="/bid-review/metrics#fail-list" className="btn btn-sec btn-sm">查看 FAIL 名单</Link>
  </div>
) : null}
```

- 建 rows 时带 op:`{ key: r.id, rule: r.name, op: r.op, stat: pack.stats[r.id], ... }`(以 RuleStatsTable 现有行形为准)。
- RuleStatsTable 调用传 `onRuleClick={setDrawerRule}`。
- 文件末尾(RulesView 函数外)加抽屉组件,函数内渲染 `{drawerRule ? <RuleDrawer ruleId={drawerRule} query={exprQuery} onClose={() => setDrawerRule(null)} /> : null}`:

```tsx
/** 规则定义抽屉(B5,原型 ruleDrawer):五块 expr-block 只读 + 版本发布 foot。 */
function RuleDrawer({
  ruleId,
  query,
  onClose,
}: {
  ruleId: string;
  query: { data?: RuleExprOut[]; isPending: boolean };
  onClose: () => void;
}) {
  const d = (query.data ?? []).find((x) => x.id === ruleId);
  return (
    <div className="drawer-wrap open" role="dialog" aria-label={`规则定义 ${ruleId}`}>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="drawer" style={{ maxWidth: 560 }}>
        <div className="drawer-hd">
          <h3>规则定义 · {ruleId}</h3>
          <button type="button" className="x" aria-label="关闭" onClick={onClose}>✕</button>
        </div>
        {!d ? (
          <div className="note-bar">
            <span>{query.isPending ? "规则定义加载中…" : "未找到该规则定义(规则包可能已更新)"}</span>
          </div>
        ) : (
          <>
            <div className="expr-block">
              <div className="expr-hd">PRECONDITION</div>
              <pre>{d.precondition ?? "(无前置条件)"}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">EXPR{d.op ? ` · ${d.op}` : ""}</div>
              <pre>{d.expr_lines.join("\n")}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">ON_MISSING_INPUT</div>
              <pre>{d.on_missing_input ?? "(未约定)"}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">MESSAGE_TPL</div>
              <pre>{d.message_tpl}</pre>
            </div>
            <div className="expr-block">
              <div className="expr-hd">FIX_TPL</div>
              <pre>{d.fix_tpl || "(无)"}</pre>
            </div>
            <div className="tbl-foot">本页只读 · 修订须走规则包版本发布(新版本号 + 评测对照)</div>
          </>
        )}
      </div>
    </div>
  );
}
```

(c) rules/page.tsx 用 Suspense 包 `<RulesView />`(useSearchParams 预渲染要求):

```tsx
import { Suspense } from "react";

import { RulesView } from "@/extensions/bid-review/components/RulesView";

export default function BidRulesPage() {
  return (
    <Suspense fallback={null}>
      <RulesView />
    </Suspense>
  );
}
```

- [x] **Step 4: 跑绿** — `pnpm test bid-review-rulepack-views` PASS(含既有 metric-strip/FAIL 名单/零回流测试)。
- [x] **Step 5: 提交** — `git add src/extensions/bid-review/components/rulepack-ui.tsx src/extensions/bid-review/components/RulesView.tsx src/app/bid-review/rules/page.tsx tests/unit/extensions/bid-review-rulepack-views.dom.test.tsx && git commit -m "feat(bid-review): /rules层级seg+判定列+规则五块抽屉+高误报互跳/深链(Plan10 T3,spec §4.7)"`

---

### Task 4: T4 MetricsView FAIL 锚点 + 归因 foot + 周趋势卡 + 行级互跳

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/MetricsView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-rulepack-views.dom.test.tsx`

- [x] **Step 1: 写失败测试** — 追加:

```tsx
  it("M5 §4.8:周趋势 6 柱+回流闭环注+FAIL 归因 foot+FAIL 行深链规则库(互跳②)", async () => {
    renderMetrics();
    expect(await screen.findByText("周趋势")).toBeTruthy();
    expect(document.querySelectorAll(".t-col").length).toBe(6);
    expect(screen.getByText(/回流闭环生效/)).toBeTruthy();
    expect(screen.getByText(/L-101 集中在「规则误判」/)).toBeTruthy();
    const failLink = screen.getByText("R-001").closest("a");
    expect(failLink!.getAttribute("href")).toBe("/bid-review/rules?rule=R-001");
  });

  it("M5 §4.8:无回流时趋势空态不画 0%(伪零纪律)", async () => {
    responder = (path) => {
      if (path.includes("/metrics/fail_attribution")) return jsonRes({ items: [] });
      if (path.includes("/metrics/trends")) return jsonRes({ weeks: TREND_EMPTY });
      return jsonRes(packPayload);
    };
    renderMetrics();
    expect(await screen.findByText(/尚无回流数据/)).toBeTruthy();
    expect(document.querySelectorAll(".t-col").length).toBe(0);
  });
```

(ATTR 夹具 = `{items:[{rule_id:"R-001",total:4,reasons:[{reason:"规则误判",count:3},{reason:"证据错位",count:1}]}]}`;TRENDS = 6 周 2 周有值;TREND_EMPTY = 6 周 rate 全 null。FAIL 夹具规则 id 用夹具中实际 FAIL 的那条,R-001 按现夹具调整。)

- [x] **Step 2: 跑红** — `pnpm test bid-review-rulepack-views`;预期 FAIL。
- [x] **Step 3: 实现** — MetricsView.tsx:
  - import `Link`(next/link)+ `useBidFailAttribution, useBidTrends`(hooks)。
  - 组件内:`const attrQuery = useBidFailAttribution(); const trendQuery = useBidTrends();` + `const attrMap = new Map((attrQuery.data ?? []).map((a) => [a.rule_id, a]));`
  - FAIL 名单卡容器加 `id="fail-list"`,card-hd hd-sub 补「复核回流归因」。
  - FAIL 表规则 id 单元格换 `<Link className="k" href={`/bid-review/rules?rule=${r.id}`}>{r.id}</Link>`(互跳②)。
  - FAIL 表后插归因 foot(tbl-foot):

```tsx
{failRows.length > 0 ? (
  <div className="tbl-foot">
    {(attrQuery.data ?? []).length > 0
      ? `FAIL 规则的误报样本已由复核回流自动归因:${failRows
          .map((r) => {
            const a = attrMap.get(r.id);
            const top = a?.reasons[0];
            return top ? `${r.id} 集中在「${top.reason}」(${top.count}/${a.total})` : `${r.id} 误报样本尚无归因(原因未填)`;
          })
          .join(" · ")}`
      : "FAIL 规则的误报样本尚无归因——复核标误报时请选原因(误报必填原因是回流数据质量的前提)。"}
  </div>
) : null}
```

(failRows = 既有 FAIL 名单数组变量,以实际命名为准;`a?.reasons[0]` 在 noUncheckedIndexedAccess 下需判空,已判。)
  - 逐规则统计卡与 FAIL 卡之间插周趋势卡:

```tsx
<div className="card" style={{ marginBottom: 12 }}>
  <div className="card-hd">
    <h3>周趋势</h3>
    <span className="hd-sub">近 6 周 · 误报率 = 误报 /(误报+维持)</span>
  </div>
  {weeks.some((w) => w.rate != null) ? (
    <div style={{ padding: "12px 16px" }}>
      <div className="trend" role="img" aria-label="近 6 周误报率柱状图">
        {weeks.map((w) => {
          const maxRate = Math.max(...weeks.map((x) => x.rate ?? 0), 1);
          const h = w.rate == null ? 4 : Math.max(8, Math.round((w.rate / maxRate) * 96));
          return (
            <div className="t-col" key={w.week_start}>
              <div className="t-bar" style={{ height: h }} title={`${w.week_start} 误报 ${w.fp} · 维持 ${w.confirmed}`} />
              <div className="t-lb">{w.rate == null ? "—" : `${w.rate}%`}</div>
              <div className="t-wk">{w.week_start.slice(5)}</div>
            </div>
          );
        })}
      </div>
      <div className="note-bar" style={{ marginTop: 12 }}>
        <span>回流闭环生效:复核误报 → 自动归因 → 评测样本 → 规则修订;「—」为无回流数据的周(伪零纪律,不画 0%)。</span>
      </div>
    </div>
  ) : (
    <div className="tbl-foot">尚无回流数据——周趋势随人工复核产生(标误报/维持即入桶)。</div>
  )}
</div>
```

(`const weeks = trendQuery.data ?? [];` 组件内先取。)

- [x] **Step 4: 跑绿** — `pnpm test bid-review-rulepack-views` PASS。
- [x] **Step 5: 提交** — `git add src/extensions/bid-review/components/MetricsView.tsx tests/unit/extensions/bid-review-rulepack-views.dom.test.tsx && git commit -m "feat(bid-review): /metrics FAIL锚点+归因foot+周趋势卡+行级互跳(Plan10 T4,spec §4.8)"`

---

### Task 5: T5 收尾

- [x] **Step 1:** `cd /d/eai/eai-flow-main/frontend && pnpm exec prettier --write src/extensions/bid-review/components/MetricsView.tsx src/extensions/bid-review/components/RulesView.tsx src/extensions/bid-review/components/rulepack-ui.tsx src/extensions/bid-review/api.ts src/extensions/bid-review/hooks.ts tests/unit/extensions/bid-review-rulepack-views.dom.test.tsx`(增量单独 style commit)
- [x] **Step 2:** `pnpm test bid-review` 全量 0 fail;`pnpm lint` bid-review 范围 0 error;`pnpm typecheck` 非 contract-price 旧债 0 新增
- [x] **Step 3:** 后端 `PYTHONPATH=. uv run pytest tests/test_bid_review_metrics.py tests/test_bid_review_feedback.py -v` 复验;gateway 已重启
- [x] **Step 4:** plan 全部 `- [x]`;`.wolf/memory.md` + `.wolf/anatomy.md` 记账(RulesView/MetricsView 行数变化);提交 `git add -f ../docs/superpowers/plans/2026-11-01-bid-review-plan10-rules-metrics-m5.md ../.wolf/memory.md ../.wolf/anatomy.md && git commit -m "chore(bid-review): Plan10 收尾——计划勾选+wolf记账"`

---

## 挂账(非本计划)

- /results 复核进度卡改读 B2 review_state(spec §4.5 L118)——M5 后单独小 commit。
- B3 页级置信 / B4 评分覆盖度 / B7 版本对比 / 报告 PDF / B8 重试解析;规则启停/评测 runner/s7/s8 整屏挂账(spec 裁决 9)。
