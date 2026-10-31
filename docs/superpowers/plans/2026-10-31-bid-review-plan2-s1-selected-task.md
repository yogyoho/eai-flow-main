# 投标审查 UX 重构 · Plan 2:s1 任务工作台——选中任务模型+统计卡换血(前端批) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地选中任务模型(URL 单一事实源+最新任务 fallback,六页共用)+ s1 统计卡换血为「当前任务体征」+ 行点击选中/可提交判定/操作列——零后端依赖,s1 全量对齐的前半程(D1/D2/D3 裁决,spec 修订 d120ea86c)。

**Architecture:** `useSelectedTask()` hook 封装 `URL ?task_id → 最新任务 → null` fallback 链;layout 四任务链页 nav link 携带 effective task_id(互跳不断档);TasksView 统计卡从跨任务汇总换为选中任务体征(TaskOut 聚合 + 选中任务单条 issues 查询),行点击=选中、跳转走操作列。

**Tech Stack:** Next.js 16 App Router(client components + useSearchParams/Suspense)、TanStack Query 5、rstest(`@rstest/core`,dom 测试 happy-dom)。

**Spec:** `docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md` §3.2(选中任务模型)/§4.1(s1)/§6.10-13(D1-D3)。
**系列位置:** Plan 1(IA 地基,8bfe18e55)已落地。本计划 = 原「Plan 3 任务总览」的前半(用户定案 s1 页先行);**Plan 3 = 后端 B1**(biz_no/project_name/main_unhandled/created_by_name/updated_at/done_at);**Plan 4 = s1 全量对齐批**(9 列真数据+搜索升级+chip 升级)。
**分支约定:** 直接在 `main-dev-fork` 提交;`git add` 一律 pathspec。
**契约演进声明:** micro-A 测试(2026-10-29)锁定的「列表页零 issues 请求」演进为「**仅选中任务一条** `/tasks/{id}/issues` 请求」——统计卡换血需要选中任务的 问题总数/误报数,单条查询不是 N+1 回退(逐任务 N+1 仍然禁止,测试显式断言只发一条且只对选中任务)。

---

### Task 1: `useSelectedTask` hook(dom 测试先行)

**Files:**
- Modify: `frontend/src/extensions/bid-review/hooks.ts`(import 区 + 文件尾)
- Test: `frontend/tests/unit/extensions/bid-review-selected-task.dom.test.tsx`(新建)

- [ ] **Step 1: 写失败测试**

```tsx
// frontend/tests/unit/extensions/bid-review-selected-task.dom.test.tsx
import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// spec §3.2 选中任务模型:effectiveTaskId = URL ?task_id → 最新任务 → null。
// isFallback=true 表示走了最新任务 fallback(非用户显式选择)。
const mocks = rs.hoisted(() => ({
  search: new URLSearchParams(),
  tasks: [] as unknown[],
}));

rs.mock("next/navigation", () => ({
  useSearchParams: () => mocks.search,
}));

// 被测函数在 hooks.ts 里,不 mock 自身。hooks.ts → ./api → @/core/api/fetcher
// (同 tasks-view 测试的既有 mock 惯例),mock fetcher 后 useBidTasks 真实跑
// TanStack Query,listTasks 数据由 responder 供给。
let responder: (path: string) => Response;
rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string) => {
    return responder(path);
  },
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

function task(partial: Record<string, unknown>) {
  return {
    id: "t0",
    owner_id: "o",
    status: "created",
    mode: "deep",
    progress: {},
    error: null,
    engine_meta: {},
    prev_task_id: null,
    created_at: "2026-10-31T00:00:00Z",
    fatal_unhandled: null,
    need_human_count: null,
    ...partial,
  };
}

function renderSel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderHook(() => useSelectedTask(), {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  });
}

describe("useSelectedTask fallback 链(spec §3.2)", () => {
  beforeEach(() => {
    mocks.search = new URLSearchParams();
    responder = () =>
      new Response(JSON.stringify({ items: mocks.tasks }), {
        headers: { "Content-Type": "application/json" },
      });
  });
  afterEach(cleanup);

  it("URL param 优先,task 对象从列表缓存取,isFallback=false", async () => {
    mocks.search = new URLSearchParams("task_id=t2");
    mocks.tasks = [task({ id: "t1" }), task({ id: "t2", status: "done" })];
    const { result } = renderSel();
    // 等列表查询落定
    for (let i = 0; i < 20 && !result.current.task; i++) {
      await new Promise((r) => setTimeout(r, 10));
    }
    expect(result.current.taskId).toBe("t2");
    expect(result.current.task?.id).toBe("t2");
    expect(result.current.isFallback).toBe(false);
  });

  it("无 param 回退最新任务(列表首位),isFallback=true", async () => {
    mocks.tasks = [task({ id: "newest", status: "running" })];
    const { result } = renderSel();
    for (let i = 0; i < 20 && !result.current.task; i++) {
      await new Promise((r) => setTimeout(r, 10));
    }
    expect(result.current.taskId).toBe("newest");
    expect(result.current.isFallback).toBe(true);
  });

  it("空任务列表:taskId=null、task=undefined(页面据此渲染空态)", async () => {
    const { result } = renderSel();
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 10));
    }
    expect(result.current.taskId).toBeNull();
    expect(result.current.task).toBeUndefined();
  });

  it("param 指向不在列表的任务(深链):taskId 保留,task=undefined", async () => {
    mocks.search = new URLSearchParams("task_id=ghost");
    mocks.tasks = [task({ id: "t1" })];
    const { result } = renderSel();
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 10));
    }
    expect(result.current.taskId).toBe("ghost");
    expect(result.current.task).toBeUndefined();
  });
});
```

实现说明:上面的轮询等待是 rstest dom 环境下等 TanStack Query 落定的最简写法(`waitFor` 亦可,轮询对 happy-dom 定时器更稳)。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm exec rstest run tests/unit/extensions/bid-review-selected-task.dom.test.tsx`
Expected: FAIL——`useSelectedTask` 不存在(import 报错)。

- [ ] **Step 3: 写实现**

`hooks.ts` import 区(`useMutation, useQuery, useQueryClient` 行后)加:

```ts
import { useSearchParams } from "next/navigation";
```

文件尾(`useBidTasks` 之后)追加:

```ts
/** 选中任务模型(spec §3.2,UX 重构 Plan 2):effectiveTaskId = URL ?task_id →
 * 最新任务(列表首位)→ null。六页任务链统一消费;isFallback=true 表示走了
 * 最新任务 fallback(非用户显式选择,页面可据此微调文案)。task 为 undefined
 * 的两种情形:param 深链不在列表缓存 / 任务列表未加载——调用方按「无详情」处理,
 * 不得伪造。 */
export function useSelectedTask() {
  const paramId = useSearchParams().get("task_id");
  const { data: tasks } = useBidTasks();
  const list = tasks ?? [];
  const taskId = paramId ?? list[0]?.id ?? null;
  const task = taskId ? list.find((t) => t.id === taskId) : undefined;
  return { taskId, task, isFallback: !paramId && taskId != null };
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && pnpm exec rstest run tests/unit/extensions/bid-review-selected-task.dom.test.tsx`
Expected: PASS,4 用例全绿。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/bid-review/hooks.ts frontend/tests/unit/extensions/bid-review-selected-task.dom.test.tsx
git commit -m "feat(bid-review): useSelectedTask 选中任务模型——param→最新任务→null fallback 链(Plan2 T1, spec §3.2)"
```

---

### Task 2: layout nav 携带 effective task_id + chip fallback

**Files:**
- Modify: `frontend/src/app/bid-review/layout.tsx`
- Test: `frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx`(追加用例)

- [ ] **Step 1: 追加失败测试(flow dom 测试文件内,describe 末尾)**

```tsx
  it("任务链页 nav link 携带 effective task_id(无 param 回退最新);治理页不带", () => {
    mocks.tasks = [fixture({ id: "newest1" }), fixture({ id: "older2" })];
    renderLayout();
    expect(screen.getByRole("link", { name: /任务总览/ }).getAttribute("href")).toBe(
      "/bid-review?task_id=newest1",
    );
    expect(
      screen.getByRole("link", { name: /审查工作台/ }).getAttribute("href"),
    ).toBe("/bid-review/workbench?task_id=newest1");
    expect(
      screen.getByRole("link", { name: /基准确认/ }).getAttribute("href"),
    ).toBe("/bid-review/baseline?task_id=newest1");
    expect(
      screen.getByRole("link", { name: /复核工作台/ }).getAttribute("href"),
    ).toBe("/bid-review/review?task_id=newest1");
    expect(screen.getByRole("link", { name: "规则库" }).getAttribute("href")).toBe(
      "/bid-review/rules",
    );
  });

  it("URL param 显式选择时 nav link 跟随 param(非最新)", () => {
    mocks.search = new URLSearchParams("task_id=chosen9");
    mocks.tasks = [fixture({ id: "newest1" }), fixture({ id: "chosen9" })];
    renderLayout();
    expect(
      screen.getByRole("link", { name: /基准确认/ }).getAttribute("href"),
    ).toBe("/bid-review/baseline?task_id=chosen9");
  });

  it("chip 回退显示最新任务(无 param 也亮,初始化即有选中态)", () => {
    mocks.tasks = [fixture({ id: "aa11bb22-cccc", status: "running" })];
    renderLayout();
    expect(screen.getByText("当前任务")).not.toBeNull();
    expect(screen.getByText("aa11bb22")).not.toBeNull();
    expect(screen.getByText("进行中")).not.toBeNull();
  });
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm exec rstest run tests/unit/app/bid-review-layout-flow.dom.test.tsx`
Expected: 新 3 用例 FAIL(nav href 无 query;chip 不渲染)。既有 5 用例保持绿。

- [ ] **Step 3: 改 layout.tsx**

3a. import 区:`nav` 导入行加 `taskHref` 与类型 `TaskPage`:

```ts
import {
  sidebarBadges,
  taskHref,
  taskStatusLabel,
  type SidebarBadges,
  type TaskPage,
} from "@/extensions/bid-review/nav";
```

3b. navItems 类型加 `taskPage?: TaskPage` 字段,四个任务链页条目分别挂 `taskPage: "tasks" | "workbench" | "baseline" | "review"`(规则库/规则效果不挂)。

3c. `TaskChip` 改 fallback(整函数替换):

```tsx
/** 「当前任务」chip:显示 effective 选中(URL param → 最新任务 fallback,
 * spec §3.2——初始化即有选中态)。任务不在列表缓存时只显 id8。
 * useSearchParams 需要 Suspense 边界,由调用处包裹。 */
function TaskChip({ tasks }: { tasks: TaskOut[] | undefined }) {
  const list = tasks ?? [];
  const taskId = useSearchParams().get("task_id") ?? list[0]?.id ?? null;
  if (!taskId) return null;
  const task = list.find((t) => t.id === taskId);
  return (
    <div className="nav-item" title="当前任务" style={{ cursor: "default" }}>
      <div>
        <div className="g-sub">当前任务</div>
        <div className="brand-row" style={{ gap: 6 }}>
          <span
            style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12 }}
          >
            {taskId.slice(0, 8)}
          </span>
          {task ? (
            <span style={{ fontSize: 12 }}>{taskStatusLabel(task.status)}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
```

3d. nav 渲染抽出 `TaskNavGroups`(用 useSearchParams 算 effective,给四个任务链页拼 href;useSearchParams 必须在 Suspense 内)。`BidReviewLayoutContent` 中 `{groups.map(...)}` 整块替换为:

```tsx
          <Suspense fallback={null}>
            <TaskNavGroups groups={groups} badges={badges} tasks={tasks} />
          </Suspense>
```

(徽标 `useBidTasks` 查询留在 `BidReviewLayoutContent`,groups/badges/tasks 全部
作为 prop 下传;TaskNavGroups 只补 useSearchParams 算 effective,单订阅零重复请求):

```tsx
/** 审查闭环 nav:任务链页 href 携带 effective task_id(六页互跳不断档,spec §3.2);
 * 治理页 href 保持裸路径。isActive 仍按基路径匹配(query 不参与)。 */
function TaskNavGroups({
  groups,
  badges,
  tasks,
}: {
  groups: Array<Array<(typeof navItems)[number]>>;
  badges: SidebarBadges;
  tasks: TaskOut[] | undefined;
}) {
  const pathname = usePathname();
  const effId = useSearchParams().get("task_id") ?? tasks?.[0]?.id ?? null;
  return (
    <>
      {groups.map((items, g) =>
        items.length === 0 ? null : (
          <nav className="chrome-group" key={g}>
            <div className="g-label">{GROUP_LABELS[g]}</div>
            {items.map(({ href, label, icon: Icon, exact, badge, taskPage }) => {
              const isActive = exact
                ? pathname === href
                : pathname.startsWith(href);
              const linkHref =
                taskPage && effId ? taskHref(taskPage, effId) : href;
              const count = badge ? badges[badge] : 0;
              return (
                <Link
                  key={href}
                  href={linkHref}
                  className={cn("nav-item", isActive && "on")}
                >
                  <Icon size={15} className="ic" aria-hidden="true" />
                  {label}
                  {badge && count > 0 ? (
                    <span
                      className={cn(
                        "nav-cnt",
                        badge === "awaitingConfirm" && "warn",
                      )}
                    >
                      {count}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </nav>
        ),
      )}
    </>
  );
}
```

`BidReviewLayoutContent` 其余不动:徽标查询 `useBidTasks` 留在原处,渲染时把
`groups`/`badges`/`tasks` 三个现成变量传入 `TaskNavGroups`。

- [ ] **Step 4: 跑测试确认通过 + micro-B 不回归**

Run: `cd frontend && pnpm exec rstest run tests/unit/app/bid-review-layout-flow.dom.test.tsx tests/unit/app/bid-review-layout.dom.test.tsx`
Expected: flow 8 用例全绿(5 旧+3 新);micro-B 3 用例绿(mock useBidTasks 返回 data:undefined → effId=null → href 裸路径,契约不变)。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/bid-review/layout.tsx frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx
git commit -m "feat(bid-review): nav 携带 effective task_id+chip 最新任务fallback(Plan2 T2, spec §3.2)"
```

---

### Task 3: TasksView——统计卡换血+行选中+可提交判定+操作列

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx`(契约演进更新)

- [ ] **Step 1: 更新测试(契约演进,先写新断言)**

对 `bid-review-tasks-view.dom.test.tsx` 的修改(整文件重写比逐段改清晰,保留原文件头注释并追加演进说明):

mock 区改造:`next/navigation` mock 增 `useSearchParams`;router mock 改 hoisted 以便断言:

```tsx
const mocks = rs.hoisted(() => ({
  search: new URLSearchParams(),
  routerReplace: (href: string) => {},
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({}),
  usePathname: () => "/bid-review",
  useRouter: () => ({
    push: rs.fn(),
    replace: (href: string) => mocks.routerReplace(href),
    refresh: rs.fn(),
  }),
  useSearchParams: () => mocks.search,
}));
```

`TASK` fixture 不变。`fatalCell` 改取合并格(下标 3→4:任务号/模式/状态/可提交判定/致命·待人工/创建时间/操作):

```tsx
/** 致命/待人工合并格(任务行第 5 列,Plan2 批1;B1 后列名换「致命/主要」)。 */
function fatalCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[4] ?? null;
}
```

`responder` 各用例需处理 `/tasks/{id}/issues`(返回 `{items: IssueOut[]}`,IssueOut 计数字段只需 `verdict`)。断言变更:

- 用例 1(done 填实):行格断言 `"1 / 1"`、`"0 / 0"`;v-hot 断言改 `cell.querySelector(".v-hot")`;卡片断言 `statValue("致命未处理")="1"`、`statValue("待人工复核")="1"`;新增 `statValue("问题总数")`、`statValue("误报已剔除")`(responder 给 t1 返回 3 条 issues,其中 1 条 verdict="false_positive" → "3"/"1");删除 `statValue("已完成")` 断言;新增 `statValue("审查用时")="—"`(B1 前)。
- 用例 2(半程任务):t2 行格 `"—"`;**契约演进**:issues 请求恰一条且只对选中任务——`calls.filter(c=>c.path.includes("/issues")).length===1` 且 `calls.some(c=>c.path.includes("/tasks/t2/issues"))===false`;选中=t1(done)→ `statValue("致命未处理")="1"`(替代原「列表有未定型→全卡 —」断言)。
- 用例 3(null 计数):行格 `"— / —"`;卡片 致命/待人工 `"—"`;问题总数按 issues 真值(responder 给 2 条)→ `"2"`。
- 用例 4(列表失败):`selectedTaskId=null` → issues 查询不使能,`calls.filter(c=>c.path.includes("/issues")).length===0`;卡片全 `"—"`。
- 新增用例 5(可提交判定):t1 done+fatal 1 → 该行第 4 列文本 `"不建议提交"`;t2 done+fatal 0 → `"建议提交"`;再放一个 `status:"awaiting_confirm"` 任务 → `"—"`。
- 新增用例 6(操作列分派):awaiting_confirm 行有 name 为「去基准确认」的链接且 href `/bid-review/baseline?task_id=<id>`;done 行「查看结果」→ `/bid-review/workbench?task_id=<id>`;running 行「查看进度」→ `/bid-review/workbench?task_id=<id>`;failed 行无操作链接。
- 新增用例 7(行点击选中):`fireEvent.click(t2 行)` → `mocks.routerReplace` 以 `"/bid-review?task_id=t2"` 调用;点击后(重渲染,search 仍由 mocks 控制——直接改 `mocks.search = new URLSearchParams("task_id=t2")` 后 `rerender`)t2 行 className 含 `"on"`、t1 行不含。
- 文件头注释追加演进记录:`// 2026-10-31 Plan2 契约演进(spec §4.1 换血+§3.2 选中模型):统计卡=选中任务体征(致命/待人工/问题总数/误报/用时);issues 请求契约从「零请求」演进为「仅选中任务一条」(非 N+1,逐任务请求仍禁止);行点击=选中(router.replace),跳转走操作列;列变 任务号/模式/状态/可提交判定/致命·待人工/创建时间/操作(7 列,B1 后 9 列全量对齐)。`

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm exec rstest run tests/unit/extensions/bid-review-tasks-view.dom.test.tsx`
Expected: FAIL(统计卡标签/列下标/verdict/操作列均不存在)。

- [ ] **Step 3: 改 TasksView.tsx(按区块)**

3a. import 区调整(原 L24-33 基础上:`useMutation, useQueryClient` 保留——s2 新建
mutation 与失效仍用;hooks 行加 `useBidIssues, useSelectedTask`;新增 `taskHref`):

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, ListChecks, Plus, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createTask } from "@/extensions/bid-review/api";
import {
  bidReviewKeys,
  useBidIssues,
  useBidTasks,
  useSelectedTask,
} from "@/extensions/bid-review/hooks";
import { taskHref } from "@/extensions/bid-review/nav";
import { type TaskOut } from "@/extensions/bid-review/types";
import { cn } from "@/lib/utils";
```

3b. 删除本地 `workbenchHref` 函数(L37-40;全文件 `workbenchHref(...)` 调用点换 `taskHref("workbench", ...)`——任务号链接与新建成功跳转两处)。

3c. `HEADERS` 替换(列定义,右对齐列随 FATAL_COL 常量走):

```ts
const HEADERS = [
  "任务号",
  "模式",
  "状态",
  "可提交判定",
  "致命/待人工",
  "创建时间",
  "操作",
];
const FATAL_COL = 4; // 致命/待人工合并格下标(Plan2 批1;B1 后 9 列布局再调)
```

3d. `CountCell` 替换为合并格(原两列合一;伪零纪律不变):

```ts
/**
 * 致命/待人工合并格(原型 s1「3 / 4」习语;Plan2 批1 列名「致命/待人工」,
 * B1 main_unhandled 落地后换「致命/主要」)。计数=GET /tasks 聚合字段;
 * 处理中任务(半程快照)与 null=未统计显 —(伪零纪律);fatal>0 走 .v-hot。
 */
function CountPairCell({
  fatal,
  needHuman,
  gated,
}: {
  fatal: number | null;
  needHuman: number | null;
  gated: boolean;
}) {
  if (gated) {
    return (
      <span className="unmapped-cell num" title="任务未出结果,暂无统计">
        —
      </span>
    );
  }
  return (
    <span className="num">
      <span className={cn(fatal != null && fatal > 0 && "v-hot")}>
        {fatal ?? "—"}
      </span>
      {" / "}
      {needHuman ?? "—"}
    </span>
  );
}
```

3e. 新增两个 cell 组件(放 `CountPairCell` 后):

```ts
/** 可提交判定列(spec §4.1,verdict 定稿口径):done 且 fatal_unhandled>0 →
 * 不建议提交(err);done 且 =0 → 建议提交(ok);其余(未出结果/未统计)—。
 * fatal_unhandled=null 的 done 任务显 —(未经测量不得判「建议提交」)。 */
function VerdictCell({ task }: { task: TaskOut }) {
  if (task.status !== "done" && task.status !== "completed") {
    return <span className="unmapped-cell" title="未出结果,不产生判定">—</span>;
  }
  const fatal = task.fatal_unhandled;
  if (fatal == null) {
    return <span className="unmapped-cell" title="问题统计未取到">—</span>;
  }
  return fatal > 0 ? (
    <span className="pill pill-err">不建议提交</span>
  ) : (
    <span className="pill pill-ok">建议提交</span>
  );
}

/** 操作列状态分派(spec §4.1;failed 的重试解析挂账 B8,不渲染)。 */
function ActionCell({ task }: { task: TaskOut }) {
  if (task.status === "awaiting_confirm") {
    return (
      <Link
        href={taskHref("baseline", task.id)}
        className="btn btn-txt btn-sm"
        onClick={(e) => e.stopPropagation()}
      >
        去基准确认
      </Link>
    );
  }
  if (task.status === "done" || task.status === "completed") {
    return (
      <Link
        href={taskHref("workbench", task.id)}
        className="btn btn-txt btn-sm"
        onClick={(e) => e.stopPropagation()}
      >
        查看结果
      </Link>
    );
  }
  if (task.status === "failed") {
    return <span className="unmapped-cell" title="重试端点(B8)落地前不提供">—</span>;
  }
  return (
    <Link
      href={taskHref("workbench", task.id)}
      className="btn btn-txt btn-sm"
      onClick={(e) => e.stopPropagation()}
    >
      查看进度
    </Link>
  );
}
```

3f. 组件体内(现有 `const tasks = tasksQuery.data ?? [];` 后)接选中模型与体征查询,**删除整段五格统计计算**(L303-325 的 `listOk/awaitingCount/runningCount/doneCount/statTasks/allMeasured/fatalCount/needHumanCount`——跨任务汇总退役):

```ts
  // 选中任务模型(spec §3.2):无 param 回退最新任务;统计卡=选中任务体征
  const { taskId: selectedId, task: selectedTask } = useSelectedTask();
  // 选中任务的体征明细(问题总数/误报数);仅一条请求(非 N+1),半程态不使能
  const selectedResulted =
    selectedTask != null && RESULT_STATUSES.has(selectedTask.status);
  const issuesQuery = useBidIssues(selectedResulted ? selectedId : null);
  const issues = issuesQuery.data;
  const issueTotal = selectedResulted && issues ? issues.length : null;
  const falsePositiveCount =
    selectedResulted && issues
      ? issues.filter((i) => i.verdict === "false_positive").length
      : null;
  /** 体征格值:半程态/未统计/加载失败一律 —(伪零纪律)。 */
  const vital = (v: number | null | undefined) =>
    selectedResulted && v != null && !issuesQuery.isError ? v : ("—" as const);
  const fatalVital = selectedTask
    ? vital(RESULT_STATUSES.has(selectedTask.status) ? selectedTask.fatal_unhandled : null)
    : ("—" as const);
  const needHumanVital = selectedTask
    ? vital(RESULT_STATUSES.has(selectedTask.status) ? selectedTask.need_human_count : null)
    : ("—" as const);
```

3g. metric-strip 渲染整块替换(L370-416 的 pending 骨架+五格;骨架保留,数据格换血):

```tsx
      {/* ── metric-strip = 当前任务体征(spec §4.1 换血;跨任务计数在侧栏徽标)── */}
      {tasksQuery.isPending ? (
        <div className="metric-strip" aria-hidden="true">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="metric-cell">
              <span className="metric-label">
                <span className="sk" style={{ width: 56, height: 12 }} />
              </span>
              <span className="metric-value">
                <span className="sk" style={{ width: 32, height: 20 }} />
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="metric-strip">
          <div className="metric-cell err">
            <span className="metric-label">致命未处理</span>
            <span className="metric-value num">{fatalVital}</span>
          </div>
          <div className="metric-cell warn">
            <span className="metric-label">
              <span className="dot dot-warn"></span>待人工复核
            </span>
            <span className="metric-value num">{needHumanVital}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">问题总数</span>
            <span className="metric-value num">{vital(issueTotal)}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label">误报已剔除</span>
            <span className="metric-value num">{vital(falsePositiveCount)}</span>
          </div>
          <div className="metric-cell">
            <span className="metric-label" title="B1 done_at 落地后提供">
              审查用时
            </span>
            <span className="metric-value num">—</span>
          </div>
        </div>
      )}
```

3h. 表体渲染:表头右对齐列(FATAL_COL 与末列)——两个 `HEADERS.map` 处的 `className={cn(i >= 3 && i <= 4 && "r")}` 均替换为:

```tsx
className={cn((i === FATAL_COL || i === HEADERS.length - 1) && "r")}
```

3i. 行渲染(L542-582 `<tbody>` map)整块替换——选中高亮+点击选中+新列:

```tsx
                    {filtered.map((t) => {
                      const st = statusPill(t.status);
                      const mp = modePill(t.mode);
                      const gated = !RESULT_STATUSES.has(t.status);
                      return (
                        <tr
                          key={t.id}
                          className={cn(
                            "cursor-pointer",
                            t.id === selectedId && "on",
                          )}
                          title="点击选中该任务"
                          onClick={() =>
                            router.replace(taskHref("tasks", t.id))
                          }
                        >
                          <td>
                            <Link
                              href={taskHref("workbench", t.id)}
                              className="mono"
                              title={t.id}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {t.id.slice(0, 8)}
                            </Link>
                          </td>
                          <td>
                            <span className={cn("pill", mp.cls)}>{mp.label}</span>
                          </td>
                          <td>
                            <span className={cn("pill", st.cls)}>
                              {st.dot ? (
                                <span className={cn("dot", st.dot)}></span>
                              ) : null}
                              {st.label}
                            </span>
                          </td>
                          <td>
                            <VerdictCell task={t} />
                          </td>
                          <td className="r">
                            <CountPairCell
                              fatal={gated ? null : t.fatal_unhandled}
                              needHuman={gated ? null : t.need_human_count}
                              gated={gated}
                            />
                          </td>
                          <td className="num">{formatDate(t.created_at)}</td>
                          <td className="r">
                            <ActionCell task={t} />
                          </td>
                        </tr>
                      );
                    })}
```

3j. 骨架表体(L453-476 aria-hidden 区)行内 td 数 6→7(复制一格任意位置),表头骨架同用新 HEADERS。`tbl-foot` 文案不动。

3k. CSS 加选中行样式(`frontend/src/app/bid-review/bid-review.css` L320 hover 规则后):

```css
.brx .tbl tbody tr.on {background:var(--main-10);}
.brx .tbl tbody tr.on:hover {background:var(--main-10);}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && pnpm exec rstest run tests/unit/extensions/bid-review-tasks-view.dom.test.tsx && pnpm exec eslint src/extensions/bid-review/components/TasksView.tsx`
Expected: 全部用例 PASS;lint 干净。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/bid-review/components/TasksView.tsx frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx frontend/src/app/bid-review/bid-review.css
git commit -m "feat(bid-review): s1 统计卡换血为选中任务体征+行选中+可提交判定+操作列(Plan2 T3, D1/D2/D3)"
```

---

### Task 4: 三任务链页接 useSelectedTask(死空态退役)

**Files:**
- Modify: `frontend/src/app/bid-review/workbench/page.tsx`
- Modify: `frontend/src/app/bid-review/baseline/page.tsx`
- Modify: `frontend/src/app/bid-review/review/page.tsx`

- [ ] **Step 1: 三个 page.tsx 同改(各文件 Content 函数)**

`workbench/page.tsx` 示例(baseline/review 同构,View 名对应换):

```tsx
"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { useSelectedTask } from "@/extensions/bid-review/hooks";
import { WorkbenchView } from "@/extensions/bid-review/components/WorkbenchView";

function WorkbenchContent() {
  // 选中任务模型(spec §3.2):URL param → 最新任务 fallback;null 仅当零任务
  const { taskId } = useSelectedTask();
  return <WorkbenchView taskId={taskId} />;
}

export default function BidReviewWorkbenchPage() {
  return (
    <>
      <Toaster />
      <Suspense
        fallback={
          <div className="text-muted-foreground flex items-center justify-center p-6 text-sm">
            加载中...
          </div>
        }
      >
        <WorkbenchContent />
      </Suspense>
    </>
  );
}
```

baseline/review 两文件同改(仅 `BaselineView`/`ReviewQueueView` 名不同,import 字母序按各文件现有顺序调整)。

- [ ] **Step 2: 验证**

Run: `cd frontend && pnpm exec rstest run tests/unit/extensions/ && pnpm typecheck 2>&1 | grep -v contract-price | grep -v docmgr || true`
Expected: extensions 域测试全绿(baseline/review 队列 dom 测试直接测 View 组件、传显式 taskId,不受影响);typecheck 仅剩已知预存错误(contract-price/docmgr)。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/bid-review/workbench/page.tsx frontend/src/app/bid-review/baseline/page.tsx frontend/src/app/bid-review/review/page.tsx
git commit -m "feat(bid-review): 任务链三页接 useSelectedTask——无 param 显最新任务,死空态退役(Plan2 T4)"
```

---

### Task 5: 全量验证 + 容器走查

- [ ] **Step 1: 前端三件套(我的领域)**

Run: `cd frontend && pnpm exec rstest run tests/unit/app/bid-review-layout.dom.test.tsx tests/unit/app/bid-review-layout-flow.dom.test.tsx tests/unit/extensions/ && pnpm exec eslint src/app/bid-review src/extensions/bid-review`
Expected: 全绿。全套件允许仅存已知预存失败(scheduled-tasks 1 处);typecheck 允许仅存 contract-price/docmgr 预存错误。

- [ ] **Step 2: 容器重启**

Run: `docker compose -p eai-docker restart frontend`
等 60s;若 `:2026/bid-review` 502 → `docker exec deer-flow-nginx nginx -s reload`(bug-3233 家族)。

- [ ] **Step 3: 真浏览器走查(登录态,:2026/login)**

检查点:
1. 进 `/bid-review`(无 param)→ 列表第一行(最新任务)即高亮选中;侧栏 chip 显示该任务 id8+状态;
2. 点另一行 → 该行高亮、chip 切换、URL 变 `?task_id=…`;刷新后选中保持;
3. 侧栏点「基准确认」→ URL 携带选中 task_id,页面直接显示该任务基准(不再是死空态);「复核工作台」「审查工作台」同理;
4. 统计卡显示选中任务的 致命/待人工/问题总数/误报/用时(—);半程任务选中时四格 —;
5. awaiting_confirm 行「去基准确认」、done 行「查看结果」、在途行「查看进度」直达正确;行点击不再整行跳转;
6. done+fatal>0 行显「不建议提交」红 pill;done+fatal=0 显「建议提交」绿 pill;
7. 规则库/规则效果页不受影响(无 query)。

- [ ] **Step 4: OpenWolf 收尾**

`.wolf/memory.md` 追加执行条目;新建测试文件补 `.wolf/anatomy.md`;如走查发现视觉微调项记入 cerebrum(留给 Plan 4)。

---

## Self-Review 记录(已跑)

1. **Spec 覆盖**:§3.2 选中模型四要素 ✓(T1 hook/T2 nav 携带+chip fallback/T3 行选中/T4 三页接入);§4.1 统计卡换血 ✓(T3f/3g)、可提交判定 ✓(T3e)、操作列 ✓(T3e,failed 不渲染 ✓)、致命/待人工合并格(批1 形态,B1 后切「致命/主要」)✓;§6.10-13 三裁决全落 ✓。9 列全量对齐明确不在本计划(Plan 4)。
2. **占位扫描**:无 TBD;所有代码块完整;baseline/review 两文件与 workbench「同构同改」但给了完整可粘贴模板与差异说明(View 名/导入序)。
3. **类型一致性**:`useSelectedTask` 返回 `{taskId, task, isFallback}` 三处消费一致;`taskHref(page, id)` 与 nav.ts Plan 1 导出一致;`TaskPage` 四值与 navItems taskPage/TaskNavGroups 一致;CountPairCell props 与调用点一致;测试 mock(`useSearchParams`/`routerReplace` hoisted)与实现依赖一致;`useBidIssues(null)` 不使能与 useBidIssues 现契约(`enabled: Boolean(taskId)`)一致。
4. **契约演进显式化**:micro-A「零 issues 请求」→「仅选中任务一条」在文件头声明 + 计划头声明 + 测试断言落实(恰一条/无逐任务)。
