# Plan 9 — /review 人工复核工作台 M4(spec §4.6)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复核工作台对齐 spec §4.6——队列口径从 need_human 扩为全量未复核(review_state 投影),加 seg 严重度筛选(默认待人工)、页头 stage-chip「复核中 k/N」、hd-sub 进度注、页脚复核进度条、第四处置项「转待人工」。

**Architecture:** B2 后端补最后一块:IssueOut 加 `review_state` 投影(取该 issue 最新一条 ReviewFeedback.action 映射,四动作端点已有,只差读路径)。前端 ReviewQueueView 改造:`handled` Set→Record(id→action)以并入本地计数;seg 词汇从 ResultsView 导出复用;计数全部客户端算(全量未复核=review_state==="unresolved" 且不在 handled)。

**Tech Stack:** FastAPI + SQLAlchemy(同步 Session)/ pytest+httpx ASGITransport;Next.js 16 / rstest(.dom.tsx happy-dom)。

**Spec:** docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md §4.6(裁决 1 全量队列 / 裁决 6 四 radio / 裁决 7 handled 保留为乐观 UI);原型 docs/designs/2026-10-30-bid-review-ui.html s6。

**行为契约不变:** 反馈四动作端点语义(confirm 不改 verdict/false_positive 翻 verdict/severity_change 只落反馈行)、误报四因必选折 note、快捷键 J/K/Y/N、DocLocateBody 原文对照、权限挂 bid:page:results。

---

### Task 1: B1 后端 review_state 投影(IssueOut + crud 批量查询 + 三端点接线)

**Files:**
- Modify: `backend/app/extensions/bid_review/schemas.py`(IssueOut)
- Modify: `backend/app/extensions/bid_review/crud.py`(latest_feedback_actions)
- Modify: `backend/app/extensions/bid_review/routers.py`(映射表 + 三端点)
- Test: `backend/tests/test_bid_review_feedback.py`

- [x] **Step 1: 写失败测试** — 在 `test_bid_review_feedback.py` 末尾追加(沿用既有 client/_mk_issue 夹具;先看既有测试确认路由前缀再定 path):

```python
def test_review_state_projection(client, make_issue):
    """B2 复核落库投影:review_state = 最新反馈动作映射(spec §4.6 裁决 1)。"""
    make_issue("i1", severity="fatal", verdict="violation", need_human=False)
    make_issue("i2", severity="major", verdict="need_human", need_human=True)

    # 初始:全部 unresolved
    r = client.get("/api/extensions/bid-review/tasks/t1/issues")
    items = {i["id"]: i for i in r.json()["items"]}
    assert items["i1"]["review_state"] == "unresolved"
    assert items["i2"]["review_state"] == "unresolved"

    # confirm → maintained(列表与详情与反馈响应三处同投影)
    r = client.post(
        "/api/extensions/bid-review/issues/i1/feedback",
        json={"action": "confirm"},
    )
    assert r.status_code == 200
    assert r.json()["review_state"] == "maintained"

    # severity_change → severity_changed(只落反馈行,不回写 issue.severity)
    r = client.post(
        "/api/extensions/bid-review/issues/i2/feedback",
        json={"action": "severity_change", "new_severity": "minor"},
    )
    assert r.json()["review_state"] == "severity_changed"
    r = client.get("/api/extensions/bid-review/issues/i2")
    assert r.json()["review_state"] == "severity_changed"
    assert r.json()["severity"] == "major"

    # 最新动作覆盖:need_human → deferred;再 false_positive → false_positive
    r = client.post(
        "/api/extensions/bid-review/issues/i1/feedback",
        json={"action": "need_human"},
    )
    assert r.json()["review_state"] == "deferred"
    r = client.post(
        "/api/extensions/bid-review/issues/i1/feedback",
        json={"action": "false_positive"},
    )
    assert r.json()["review_state"] == "false_positive"

    # 列表终态投影
    r = client.get("/api/extensions/bid-review/tasks/t1/issues")
    items = {i["id"]: i for i in r.json()["items"]}
    assert items["i1"]["review_state"] == "false_positive"
    assert items["i2"]["review_state"] == "severity_changed"
```

(夹具名/路由前缀以既有文件为准,不一致就改为既有写法。)

- [x] **Step 2: 跑红** — `cd /d/eai/eai-flow-main/backend && PYTHONPATH=. uv run pytest tests/test_bid_review_feedback.py -v`;预期 FAIL(`KeyError: 'review_state'`)。

- [x] **Step 3: 实现** —

(a) schemas.py IssueOut(confidence 之后)加:

```python
    # B2 复核落库投影(EAI-CUSTOM 2026-10-31):最新反馈动作 → 复核态,
    # unresolved|maintained|false_positive|severity_changed|deferred;无反馈=unresolved
    review_state: str = "unresolved"
```

(b) crud.py 加(record_feedback 旁;ReviewFeedback 已 import):

```python
def latest_feedback_actions(db: Session, issue_ids: list[str]) -> dict[str, str]:
    """issue_id → 最新一次复核反馈动作(B2 review_state 投影;空入参→空表)。

    同 created_at 时按自增 id 定序,保证同秒连投的最新动作胜出。
    """
    if not issue_ids:
        return {}
    rows = (
        db.query(ReviewFeedback)
        .filter(ReviewFeedback.issue_id.in_(issue_ids))
        .order_by(ReviewFeedback.created_at.asc(), ReviewFeedback.id.asc())
        .all()
    )
    latest: dict[str, str] = {}
    for r in rows:
        latest[r.issue_id] = r.action
    return latest
```

(c) routers.py(feedback_issue 端点附近)加映射表 + 投影助手:

```python
# B2 复核落库投影(EAI-CUSTOM 2026-10-31):反馈动作 → review_state
_REVIEW_ACTION_STATE = {
    "confirm": "maintained",
    "false_positive": "false_positive",
    "severity_change": "severity_changed",
    "need_human": "deferred",
}


def _with_review_state(issue, states: dict[str, str]) -> IssueOut:
    out = IssueOut.model_validate(issue)
    out.review_state = states.get(issue.id, "unresolved")
    return out
```

(d) 三处接线:
- `list_task_issues`:`IssueOut.model_validate(i)` 换批量投影:

```python
    states = crud.latest_feedback_actions(db, [i.id for i in issues])
    return {
        "items": [_with_review_state(i, states) for i in issues],
        "summary": worker.summarize_issues(issues),
    }
```

- `get_issue_detail`:`return IssueOut.model_validate(issue)` 换
  `return _with_review_state(issue, crud.latest_feedback_actions(db, [issue.id]))`。
- `feedback_issue`:末尾 `await db.refresh(issue); return issue` 换:

```python
    await db.refresh(issue)
    out = IssueOut.model_validate(issue)
    out.review_state = _REVIEW_ACTION_STATE.get(body.action, "unresolved")
    return out
```

- [x] **Step 4: 跑绿** — 同命令 PASS(既有 6 测不回归)。
- [x] **Step 5: 重启网关 + lint** — `docker compose -p eai-docker restart gateway`;`cd backend && make lint`;`git add app/extensions/bid_review/schemas.py app/extensions/bid_review/crud.py app/extensions/bid_review/routers.py tests/test_bid_review_feedback.py && git commit -m "feat(bid-review): issues投影加review_state(最新反馈动作映射,B2收尾,Plan9 T1,spec §4.6)"`

---

### Task 2: T2 前端类型 + SEG 词汇导出

**Files:**
- Modify: `frontend/src/extensions/bid-review/types.ts`(IssueOut)
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`(导出)

- [x] **Step 1:** types.ts IssueOut `confidence` 后加(旧网关容忍缺省):

```ts
  /** B2 复核投影(unresolved|maintained|false_positive|severity_changed|deferred);旧网关无此字段。 */
  review_state?: string;
```

- [x] **Step 2:** ResultsView.tsx 的 `type SevFilter` 加 export、`const SEG_OPTIONS` 加 export(消费方 ReviewQueueView 已 import 该文件,无环)。
- [x] **Step 3: 跑绿** — `cd /d/eai/eai-flow-main/frontend && pnpm typecheck 2>&1 | grep -c "error TS"` 计数不增。
- [x] **Step 4: 提交** — `git add src/extensions/bid-review/types.ts src/extensions/bid-review/components/ResultsView.tsx && git commit -m "feat(bid-review): IssueOut.review_state类型+SEG_OPTIONS导出(Plan9 T2,spec §4.6)"`

---

### Task 3: T3 队列口径全量未复核 + seg 筛选 + stage-chip + 进度注/页脚

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ReviewQueueView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-review-queue.dom.test.tsx`

- [x] **Step 1: 写失败测试** — 测试文件末尾追加新 `it`(夹具复用 `issue()` helper,review_state 走 over):

```tsx
  it("M4 §4.6:全量未复核队列+seg筛选(默认待人工)+stage-chip+页脚进度;转待人工→need_human", async () => {
    const MIX = {
      items: [
        // 致命违规:不在默认段,「全部」段可达
        issue("i1", {
          severity: "fatal",
          verdict: "violation",
          need_human: false,
        }),
        // need_human:默认段唯一入队项
        issue("i2"),
        // 已复核维持:全量口径下也不入队
        issue("i3", { review_state: "maintained", need_human: false }),
      ],
    };
    responder = (path) => {
      if (path.endsWith("/issues")) return jsonRes(MIX);
      if (path.includes("/feedback")) return jsonRes({});
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      return jsonRes({}, 404);
    };
    renderReview();

    // 默认段=待人工:仅 i2;stage-chip 复核中 1/1
    expect(await screen.findByText(/复核中 1\/1/)).toBeTruthy();
    expect(screen.getByText(/R-i2/)).toBeTruthy();
    expect(screen.queryByText(/R-i1/)).toBeNull();

    // hd-sub 进度注 + 页脚:已复核 1(维持 1)/ 待复核 2
    expect(screen.getByText(/已复核 1/)).toBeTruthy();
    expect(screen.getByText(/本任务复核进度 1 \/ 3/)).toBeTruthy();

    // 切「全部」→ i1 滑入(i3 maintained 仍排除)
    fireEvent.click(screen.getByRole("button", { name: /全部/ }));
    expect(await screen.findByText(/R-i1/)).toBeTruthy();
    expect(screen.getByText(/复核中 1\/2/)).toBeTruthy();

    // 第四处置项:转待人工 → POST action=need_human
    fireEvent.click(screen.getByRole("radio", { name: /转待人工/ }));
    fireEvent.click(screen.getByRole("button", { name: "转待人工并下一条" }));
    await waitFor(() => {
      const fb = calls.find(
        (c) => c.path === "/api/extensions/bid-review/issues/i1/feedback",
      );
      expect(fb).toBeTruthy();
      const body = JSON.parse(fb!.init!.body as string) as { action: string };
      expect(body.action).toBe("need_human");
    });
    // 本地 handled 推进(裁决 7):页脚待复核收敛 2→1
    await waitFor(() => expect(screen.getByText(/待复核 1/)).toBeTruthy());
  });
```

- [x] **Step 2: 跑红** — `pnpm test bid-review-review-queue`;预期 FAIL(找不到 复核中 1/1)。

- [x] **Step 3: 实现** — ReviewQueueView.tsx 六处:

(a) import 增补:ResultsView 行加 `SEG_OPTIONS`,`type SevFilter`(api.ts 的 FeedbackAction 已含 need_human,无类型增量);types 行已有 IssueOut。

```ts
import {
  FP_REASONS,
  SEG_OPTIONS,
  renderIssueMessage,
  sevPillBrx,
  type SevFilter,
} from "@/extensions/bid-review/components/ResultsView";
```

(b) `handled` Set→Record(id→action,并纳入计数);队列口径全量未复核;seg state:

```ts
  // 队列口径(M4 §4.6 裁决 1)= 全量未复核:review_state==="unresolved" 且
  // 不在本会话 handled;handled 记 id→最新动作,供维持/误报计数(裁决 7:
  // 本地集合仅乐观 UI,服务端 review_state 真源,重取后语义收敛)。
  const [handled, setHandled] = useState<Record<string, string>>({});
  const [seg, setSeg] = useState<SevFilter>("human");
  const stateOf = (i: IssueOut) => handled[i.id] ?? i.review_state ?? "unresolved";
  const pending = useMemo(
    () => (issuesQuery.data ?? []).filter((i) => stateOf(i) === "unresolved"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issuesQuery.data, handled],
  );
  const segOf = (i: IssueOut) =>
    seg === "all"
      ? true
      : seg === "human"
        ? i.need_human
        : i.severity === seg;
  const queue = useMemo(() => pending.filter(segOf), [pending, seg]);
```

(useMemo 依赖 stateOf/segOf 闭包引用 handled/seg——直接内联过滤逻辑到 useMemo 更稳,实现时以能过 lint 为准。)

(c) 计数(pending 定义后):

```ts
  const reviewedTotal = (issuesQuery.data ?? []).length - pending.length;
  const maintained = (issuesQuery.data ?? []).filter(
    (i) => stateOf(i) === "maintained",
  ).length;
  const fpTotal = (issuesQuery.data ?? []).filter(
    (i) => stateOf(i) === "false_positive",
  ).length;
```

(d) submit onSuccess toast 加 need_human 分支;handled 写 Record:

```ts
          toast.success(
            a === "confirm"
              ? "已确认问题"
              : a === "false_positive"
                ? "已标误报(回流评测集)"
                : a === "need_human"
                  ? "已转待人工(不计违规)"
                  : "已调整严重度",
          );
          setHandled((m) => ({ ...m, [current.id]: a }));
```

按钮 label 三元链加分支:`action === "need_human" ? "转待人工并下一条"`(排在 severity_change 之前判,注意顺序)。

(e) 页头:ph-actions 首位插 stage-chip;ph-sub 改带计数(原型 s6 句式):

```tsx
        <div className="ph-actions">
          <span className="stage-chip">
            复核中 {Math.min(safeIdx + 1, queue.length)}/{queue.length}
          </span>
          <Link
            href={`/bid-review/results?task_id=${taskId}`}
            className="btn btn-sec btn-sm"
          >
            返回结果页
          </Link>
        </div>
```

```tsx
          <div className="ph-sub">
            复核队列 {pending.length} 项 · 已复核 {reviewedTotal}(维持{" "}
            {maintained} / 误报 {fpTotal}) · 未判定 ≠ 通过 · 误报自动回流评测集
          </div>
```

(f) 右 card:card-hd 与 toolbar 之间插 seg 行;card 末尾(form 块后)插页脚 tbl-foot:

```tsx
            <div
              className="seg"
              role="group"
              aria-label="严重度筛选"
              style={{ padding: "10px 16px 0" }}
            >
              {SEG_OPTIONS.map((opt) => {
                const n = pending.filter((i) =>
                  opt.value === "all"
                    ? true
                    : opt.value === "human"
                      ? i.need_human
                      : i.severity === opt.value,
                ).length;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className={cn(seg === opt.value && "on")}
                    aria-pressed={seg === opt.value}
                    onClick={() => {
                      setSeg(opt.value);
                      setIdx(0);
                    }}
                  >
                    {opt.label} {n}
                  </button>
                );
              })}
            </div>
```

```tsx
            <div
              className="tbl-foot"
              style={{ justifyContent: "space-between" }}
            >
              <span>
                本任务复核进度 {reviewedTotal} / {(issuesQuery.data ?? []).length}
              </span>
              <span>
                维持 {maintained} · 误报 {fpTotal} · 待复核 {pending.length}
              </span>
            </div>
```

- [x] **Step 4: 跑绿** — `pnpm test bid-review-review-queue` PASS(既有 2 测不回归:夹具均 need_human 无 review_state,默认段行为不变)。
- [x] **Step 5: 提交** — `git add src/extensions/bid-review/components/ReviewQueueView.tsx tests/unit/extensions/bid-review-review-queue.dom.test.tsx && git commit -m "feat(bid-review): /review 全量未复核队列+seg筛选+stage-chip+页脚进度(Plan9 T3,spec §4.6)"`

---

### Task 4: T4 四 radio(转待人工)+ 快捷键不变

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ReviewQueueView.tsx`

(与 T3 同文件,若 T3 已连带落 T4 的 radio/label/toast 改动,此任务仅补测试断言与查漏。)

- [x] **Step 1:** radiogroup「处置判定」severity_change label 之后追加第四项(radio 顺序保持 确认/误报/严重度调整/转待人工,既有测试 radios[1]=误报 不破):

```tsx
                  <label
                    style={{ display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <input
                      type="radio"
                      name="review-action"
                      checked={action === "need_human"}
                      onChange={() => setAction("need_human")}
                    />
                    转待人工(引擎无法判定,挂起不计违规)
                  </label>
```

- [x] **Step 2:** 快捷键 effect 不动(Y 确认 / N 选中误报语义不变;need_human 无快捷键)。
- [x] **Step 3: 跑绿** — `pnpm test bid-review-review-queue` PASS。
- [x] **Step 4: 提交** — `git add src/extensions/bid-review/components/ReviewQueueView.tsx && git commit -m "feat(bid-review): /review 四处置radio——加转待人工need_human(Plan9 T4,spec §4.6裁决6)"`

---

### Task 5: T5 收尾

- [x] **Step 1:** `cd /d/eai/eai-flow-main/frontend && pnpm exec prettier --write src/extensions/bid-review/components/ReviewQueueView.tsx src/extensions/bid-review/components/ResultsView.tsx src/extensions/bid-review/types.ts tests/unit/extensions/bid-review-review-queue.dom.test.tsx`
- [x] **Step 2:** `pnpm test bid-review` 全量(69+ 用例 0 fail)
- [x] **Step 3:** `pnpm lint` bid-review 范围 0 error;`pnpm typecheck` 非 contract-price 旧债 0 新增
- [x] **Step 4:** prettier 增量单独 style commit;plan 全部 `- [x]`;`.wolf/memory.md`+`anatomy.md` 记账;提交 `git add -f ../docs/superpowers/plans/2026-10-31-bid-review-plan9-review-m4.md ../.wolf/memory.md ../.wolf/anatomy.md && git commit -m "chore(bid-review): Plan9 收尾——计划勾选+wolf记账"`

---

## 挂账(非本计划)

- 复核进度卡(/results 左列)改读 B2 review_state(spec §4.5 L118)——随 M5 或单独小 commit,不在 M4 范围。
- B3 页级置信 / B4 评分覆盖度 / B5-B7 版本对比 / 报告 PDF / B8 重试解析。
