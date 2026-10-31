# 投标审查 UX 重构 · Plan 1:IA 地基 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 侧栏从路由目录变流程导航——共享任务查询、三类计数徽标、「当前任务」chip,后续 7 份页面计划的地基。

**Architecture:** 新增纯工具模块 `nav.ts`(taskHref/状态词表/徽标计数),`hooks.ts` 补共享 `useBidTasks`(layout 徽标与 TasksView 列表同源同缓存),`layout.tsx` 重排导航为流程序并挂徽标与 chip。纯前端,零后端依赖,落地即可用。

**Tech Stack:** Next.js 16 App Router(client components)、TanStack Query 5、rstest(`@rstest/core` + `@testing-library/react`,dom 测试 happy-dom)。

** Spec:** `docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md` §3(信息架构)。
**分支约定:** 直接在 `main-dev-fork` 提交(项目惯例,无 worktree);`git add` 一律 pathspec,禁 `-A/-u/.`。
**本计划刻意不含(spec §7 M1 的两处收窄):** ①新页面点权限 yaml——页面不存在时不发导航项,各页面计划自带;②徽标点击直达 task_id——徽标在 Link 内部,嵌套 `<a>` 非法,直达随任务选择器计划(Plan 3)一起做。

---

### Task 1: `nav.ts` 纯工具模块(TDD)

**Files:**
- Create: `frontend/src/extensions/bid-review/nav.ts`
- Test: `frontend/tests/unit/extensions/bid-review/nav.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/extensions/bid-review/nav.test.ts
import { describe, expect, it } from "@rstest/core";

import {
  firstTaskIdFor,
  sidebarBadges,
  taskHref,
  taskStatusLabel,
} from "@/extensions/bid-review/nav";
import type { TaskOut } from "@/extensions/bid-review/types";

function task(partial: Partial<TaskOut>): TaskOut {
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

describe("taskHref", () => {
  it("任务链页拼 task_id 并编码", () => {
    expect(taskHref("workbench", "abc")).toBe(
      "/bid-review/workbench?task_id=abc",
    );
    expect(taskHref("review", "a b")).toBe("/bid-review/review?task_id=a%20b");
    expect(taskHref("baseline", "x")).toBe("/bid-review/baseline?task_id=x");
    expect(taskHref("tasks", "x")).toBe("/bid-review?task_id=x");
  });
});

describe("taskStatusLabel", () => {
  it("与 TasksView 列表 pill 同词汇,未知状态原样回落", () => {
    expect(taskStatusLabel("awaiting_confirm")).toBe("待基准确认");
    expect(taskStatusLabel("extracting")).toBe("基准提取中");
    expect(taskStatusLabel("failed")).toBe("失败");
    expect(taskStatusLabel("mystery")).toBe("mystery");
  });
});

describe("sidebarBadges", () => {
  it("进行中含三在途态;复核待办是 need_human_count 求和(null=0 禁伪零)", () => {
    const tasks = [
      task({ id: "a", status: "parsing" }),
      task({ id: "b", status: "running" }),
      task({ id: "c", status: "awaiting_confirm" }),
      task({ id: "d", status: "awaiting_confirm" }),
      task({ id: "e", status: "done", need_human_count: 3 }),
      task({ id: "f", status: "done", need_human_count: 2 }),
      task({ id: "g", status: "done", need_human_count: null }),
    ];
    expect(sidebarBadges(tasks)).toEqual({
      running: 2,
      awaitingConfirm: 2,
      reviewTodo: 5,
    });
  });
  it("空列表全零", () => {
    expect(sidebarBadges([])).toEqual({
      running: 0,
      awaitingConfirm: 0,
      reviewTodo: 0,
    });
  });
});

describe("firstTaskIdFor", () => {
  const tasks = [
    task({ id: "run1", status: "extracting" }),
    task({ id: "await1", status: "awaiting_confirm" }),
    task({ id: "todo1", status: "done", need_human_count: 4 }),
  ];
  it("按徽标返回第一个命中任务 id", () => {
    expect(firstTaskIdFor(tasks, "running")).toBe("run1");
    expect(firstTaskIdFor(tasks, "awaitingConfirm")).toBe("await1");
    expect(firstTaskIdFor(tasks, "reviewTodo")).toBe("todo1");
  });
  it("无命中返回 null(徽标隐藏时不会调用,防御)", () => {
    expect(firstTaskIdFor([], "running")).toBeNull();
    expect(
      firstTaskIdFor([task({ id: "d", status: "done" })], "awaitingConfirm"),
    ).toBeNull();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm test`
Expected: FAIL——`Cannot find module "@/extensions/bid-review/nav"`(其余套件保持绿)。

- [ ] **Step 3: 写实现**

```ts
// frontend/src/extensions/bid-review/nav.ts
/**
 * 侧栏流程化纯工具(UX 重构 Plan 1 / spec §3)。
 * 任务链页互跳统一走 taskHref(后续逐步替代组件私有 workbenchHref);徽标计数
 * 与「最近命中任务」定位在此,layout 与页面共用同一口径。状态词表与 TasksView
 * 列表 pill 保持同词汇(改一处须同步另一处)。
 */
import type { TaskOut } from "./types";

export type TaskPage = "tasks" | "workbench" | "baseline" | "review";

const PAGE_PATHS: Record<TaskPage, string> = {
  tasks: "/bid-review",
  workbench: "/bid-review/workbench",
  baseline: "/bid-review/baseline",
  review: "/bid-review/review",
};

export function taskHref(page: TaskPage, taskId: string): string {
  return `${PAGE_PATHS[page]}?task_id=${encodeURIComponent(taskId)}`;
}

/** 状态词表(与 TasksView statusPill 同词汇;后端终态无 completed)。 */
export const TASK_STATUS_LABELS: Record<string, string> = {
  created: "已创建",
  parsing: "解析中",
  extracting: "基准提取中",
  awaiting_confirm: "待基准确认",
  running: "进行中",
  done: "已完成",
  failed: "失败",
};

export function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status;
}

/** 在途态(「进行中」徽标口径,同 TasksView seg active)。 */
const ACTIVE_STATUSES = new Set(["parsing", "extracting", "running"]);

export interface SidebarBadges {
  running: number;
  awaitingConfirm: number;
  reviewTodo: number;
}

export function sidebarBadges(tasks: TaskOut[]): SidebarBadges {
  return {
    running: tasks.filter((t) => ACTIVE_STATUSES.has(t.status)).length,
    awaitingConfirm: tasks.filter((t) => t.status === "awaiting_confirm")
      .length,
    reviewTodo: tasks.reduce((sum, t) => sum + (t.need_human_count ?? 0), 0),
  };
}

/** 徽标点击直达用:第一个命中任务 id(列表为 owner 内返回序)。 */
export function firstTaskIdFor(
  tasks: TaskOut[],
  badge: keyof SidebarBadges,
): string | null {
  if (badge === "running") {
    return tasks.find((t) => ACTIVE_STATUSES.has(t.status))?.id ?? null;
  }
  if (badge === "awaitingConfirm") {
    return tasks.find((t) => t.status === "awaiting_confirm")?.id ?? null;
  }
  return tasks.find((t) => (t.need_human_count ?? 0) > 0)?.id ?? null;
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && pnpm test`
Expected: PASS(nav.test.ts 6 用例全绿,全套件无回归)。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/bid-review/nav.ts frontend/tests/unit/extensions/bid-review/nav.test.ts
git commit -m "feat(bid-review): nav.ts 纯工具——taskHref/状态词表/侧栏徽标计数(Plan1 T1)"
```

---

### Task 2: 共享 `useBidTasks` hook + TasksView 改用

**Files:**
- Modify: `frontend/src/extensions/bid-review/hooks.ts`(文件尾追加 hook + import)
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(L24 import、L269-271 查询块)

- [ ] **Step 1: hooks.ts 追加共享 hook**

`hooks.ts` 的 api import 块(L12-21)加入 `listTasks`:

```ts
import {
  adjudicateBaseline,
  confirmTask,
  feedbackIssue,
  fetchBaselines,
  getTask,
  listRulepacks,
  listTaskIssues,
  listTasks,
  type FeedbackBody,
} from "./api";
```

文件尾(`useBidConfirmTask` 之后)追加:

```ts
/** GET /tasks —— 任务列表共享查询(UX 重构 Plan 1):TasksView 列表与 layout
 * 侧栏徽标/任务 chip 同 key(bidReviewKeys.tasks)同缓存,mutation invalidate
 * 一处失效多处同步。 */
export function useBidTasks() {
  return useQuery({ queryKey: bidReviewKeys.tasks, queryFn: listTasks });
}
```

- [ ] **Step 2: TasksView 换用共享 hook**

`TasksView.tsx` L24:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
```

L269-271 查询块(原样:

```ts
const tasksQuery = useQuery({
  queryKey: bidReviewKeys.tasks,
  queryFn: listTasks,
});
```

)替换为:

```ts
const tasksQuery = useBidTasks();
```

import 区加入 `useBidTasks`(与既有 `bidReviewKeys` 同一行或相邻,保持字母序):

```ts
import { bidReviewKeys, useBidTasks } from "@/extensions/bid-review/hooks";
```

注意:`bidReviewKeys` 若仅剩 createTask 的 invalidate 在用则保留 import;`listTasks` import(L30)若不再被引用则从该行移除。以 `pnpm lint`(unused 检查)为准收口。

- [ ] **Step 3: 跑测试+lint 确认无回归**

Run: `cd frontend && pnpm test && pnpm lint && pnpm typecheck`
Expected: 全绿(TasksView 行为不变——同 key 同 queryFn,缓存命中)。若 TasksView 有 dom 测试断言列表渲染,照常通过。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/bid-review/hooks.ts frontend/src/extensions/bid-review/components/TasksView.tsx
git commit -m "feat(bid-review): 共享 useBidTasks——列表与侧栏同源缓存(Plan1 T2)"
```

---

### Task 3: layout 流程化——导航重排+徽标+「当前任务」chip(TDD)

**Files:**
- Modify: `frontend/src/app/bid-review/layout.tsx`
- Test: `frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx`(新建)
- 不动: `frontend/tests/unit/app/bid-review-layout.dom.test.tsx`(micro-B 契约——本任务不改任何 href/label,该测试必须原样保持绿)

- [ ] **Step 1: 写失败测试(新 dom 测试文件)**

```tsx
// frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx
import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";
import type { PropsWithChildren, ReactNode } from "react";

// UX 重构 Plan 1 T3:侧栏流程化三条行为——
// ① 审查闭环组按流程序排列(基准确认在复核工作台之前);
// ② 三类计数徽标(任务总览进行中/基准确认 warn/复核工作台待复核)来自共享任务查询;
// ③ URL 带 task_id 时侧栏渲染「当前任务」chip(id8+状态词)。
const mocks = rs.hoisted(() => ({
  search: new URLSearchParams(),
  tasks: [] as unknown[],
}));

rs.mock("next/navigation", () => ({
  usePathname: () => "/bid-review",
  useSearchParams: () => mocks.search,
}));

rs.mock("next/link", () => {
  const MockLink = ({
    href,
    children,
  }: {
    href: string;
    children: ReactNode;
  }) => <a href={href}>{children}</a>;
  return { default: MockLink };
});

rs.mock("@/core/permissions", () => ({
  usePermission: () => ({ canPage: () => true, isLoading: false }),
  PermissionProvider: ({ children }: PropsWithChildren) => <>{children}</>,
}));

rs.mock("@/extensions/hooks/useAuth", () => ({
  AuthProvider: ({ children }: PropsWithChildren) => <>{children}</>,
  useAuth: () => ({ user: { id: "u1" }, isLoading: false }),
}));

rs.mock("@/components/workspace/workspace-login-redirect", () => ({
  WorkspaceLoginRedirect: () => null,
}));

// layout 只消费 useBidTasks;mock 共享任务查询返回 fixtures。
rs.mock("@/extensions/bid-review/hooks", () => ({
  bidReviewKeys: { tasks: ["bid-review", "tasks"] },
  useBidTasks: () => ({ data: mocks.tasks }),
}));

import BidReviewLayout from "@/app/bid-review/layout";

function fixture(partial: Record<string, unknown>) {
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

function renderLayout() {
  return render(
    <BidReviewLayout>
      <div>page body</div>
    </BidReviewLayout>,
  );
}

describe("bid-review layout 流程化(Plan 1)", () => {
  beforeEach(() => {
    mocks.search = new URLSearchParams();
    mocks.tasks = [];
  });
  afterEach(cleanup);

  it("审查闭环组按流程序:基准确认排在复核工作台之前", () => {
    renderLayout();
    const links = screen
      .getAllByRole("link")
      .map((l) => l.getAttribute("href"));
    expect(links.indexOf("/bid-review/baseline")).toBeLessThan(
      links.indexOf("/bid-review/review"),
    );
    // 既有页一个不少(micro-B 契约的 href 集不变)
    for (const href of [
      "/bid-review",
      "/bid-review/workbench",
      "/bid-review/baseline",
      "/bid-review/review",
      "/bid-review/rules",
      "/bid-review/metrics",
    ]) {
      expect(links).toContain(href);
    }
  });

  it("徽标:进行中 2 / 基准确认 warn 1 / 复核待复核 5(Σ need_human_count)", () => {
    mocks.tasks = [
      fixture({ id: "a", status: "parsing" }),
      fixture({ id: "b", status: "running" }),
      fixture({ id: "c", status: "awaiting_confirm" }),
      fixture({ id: "d", status: "done", need_human_count: 3 }),
      fixture({ id: "e", status: "done", need_human_count: 2 }),
    ];
    renderLayout();
    const tasksLink = screen.getByRole("link", { name: "任务总览" });
    expect(tasksLink.textContent).toContain("2");
    const baselineLink = screen.getByRole("link", { name: "基准确认" });
    expect(baselineLink.textContent).toContain("1");
    expect(baselineLink.querySelector(".nav-cnt.warn")).not.toBeNull();
    const reviewLink = screen.getByRole("link", { name: "复核工作台" });
    expect(reviewLink.textContent).toContain("5");
  });

  it("计数为零的徽标不渲染;规则治理组无徽标", () => {
    mocks.tasks = [fixture({ id: "a", status: "done" })];
    renderLayout();
    expect(
      screen.getByRole("link", { name: "任务总览" }).querySelector(".nav-cnt"),
    ).toBeNull();
    expect(
      screen.getByRole("link", { name: "规则库" }).querySelector(".nav-cnt"),
    ).toBeNull();
  });

  it("URL 带 task_id 时渲染「当前任务」chip(id8+状态词)", () => {
    mocks.search = new URLSearchParams("task_id=5a8e15b8-8ac4-4141-a7e0-2e125953380b");
    mocks.tasks = [fixture({ id: "5a8e15b8-8ac4-4141-a7e0-2e125953380b", status: "awaiting_confirm" })];
    renderLayout();
    expect(screen.getByText("当前任务")).not.toBeNull();
    expect(screen.getByText("5a8e15b8")).not.toBeNull();
    expect(screen.getByText("待基准确认")).not.toBeNull();
  });

  it("task_id 不在列表中(如直链新任务)chip 仍显示 id8,无状态词", () => {
    mocks.search = new URLSearchParams("task_id=ffffffff-0000");
    renderLayout();
    expect(screen.getByText("当前任务")).not.toBeNull();
    expect(screen.getByText("ffffffff")).not.toBeNull();
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && pnpm test`
Expected: 新文件 FAIL(流程序断言:baseline 在 review 之后不成立;徽标/chip 元素不存在)。既有 micro-B 测试保持绿。

- [ ] **Step 3: 改 layout.tsx**

3a. import 区(L3-15)替换为:

```ts
import {
  BookOpen,
  ClipboardCheck,
  FileText,
  Gauge,
  ListChecks,
  Moon,
  Sun,
  UserCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { QueryClientProvider } from "@/components/query-client-provider";
import { WorkspaceLoginRedirect } from "@/components/workspace/workspace-login-redirect";
import { usePermission, PermissionProvider } from "@/core/permissions";
import {
  useBidTasks,
} from "@/extensions/bid-review/hooks";
import {
  sidebarBadges,
  taskStatusLabel,
  type SidebarBadges,
} from "@/extensions/bid-review/nav";
import type { TaskOut } from "@/extensions/bid-review/types";
import { AuthProvider, useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";
```

3b. `navItems`(L34-81)整块替换——组 0 重排为流程序,挂徽标键;组头注释同步改写:

```ts
// EAI-CUSTOM (2026-10-30 独立子系统改造;2026-10-31 UX 重构 Plan 1 流程化):
// /bid-review 脱离 EAI 壳,自绘原型 chrome(参照 docs/designs/2026-10-30-bid-review-ui.html,
// 样式全量收敛在 .brx 根类)。入口约定:应用中心卡片 target=_blank 新 tab 打开
// (AppCard.tsx),站内其余入口不跳转至此。providers 自备:QueryClientProvider +
// AuthProvider + PermissionProvider;登录门=StandaloneGate。子路由映射到子页面
// 权限点(/api/permissions/me 的 pages)供 canPage 过滤——micro-B 回归门
// (tests/unit/app/bid-review-layout.dom.test.tsx)锁定 href/label 契约,勿改。
// UX 重构 Plan 1:组 0 按审查闭环流程序排列(基准确认→复核工作台),徽标数据
// 来自共享 useBidTasks(badge 键见 SidebarBadges);/workbench 为 results 拆分
// (Plan 6)落地前的暂用路由,届时换 /results + 重定向 shim。
const navItems: Array<{
  href: string;
  label: string;
  icon: typeof ListChecks;
  exact?: boolean;
  pageId: string;
  group: 0 | 1;
  badge?: keyof SidebarBadges;
}> = [
  {
    href: "/bid-review",
    // 2026-10-30 用户定案:「任务总览」——首项即任务工作台(s1),改名与「审查工作台」区分
    label: "任务总览",
    icon: ListChecks,
    exact: true,
    pageId: "bid:page:tasks",
    group: 0,
    badge: "running",
  },
  {
    href: "/bid-review/workbench",
    label: "审查工作台",
    icon: FileText,
    pageId: "bid:page:workbench",
    group: 0,
  },
  {
    href: "/bid-review/baseline",
    label: "基准确认",
    icon: ClipboardCheck,
    pageId: "bid:page:baseline",
    group: 0,
    badge: "awaitingConfirm",
  },
  {
    // EAI-CUSTOM (2026-10-31 二期 spec §五 s6):need_human 队列复核;
    // 挂 bid:page:workbench(同治理域,先例=metrics 挂 bid:page:rules)
    href: "/bid-review/review",
    label: "复核工作台",
    icon: UserCheck,
    pageId: "bid:page:workbench",
    group: 0,
    badge: "reviewTodo",
  },
  {
    href: "/bid-review/rules",
    label: "规则库",
    icon: BookOpen,
    pageId: "bid:page:rules",
    group: 1,
  },
  {
    href: "/bid-review/metrics",
    label: "规则效果",
    icon: Gauge,
    pageId: "bid:page:rules",
    group: 1,
  },
];
```

3c. `BidReviewLayoutContent`(L127-199)整块替换——挂查询、徽标渲染、chip:

```tsx
/** 「当前任务」chip:URL 带 task_id 时显示(id8+状态词;任务不在列表缓存时只显
 * id8)。useSearchParams 需要 Suspense 边界,由调用处包裹。 */
function TaskChip({ tasks }: { tasks: TaskOut[] | undefined }) {
  const taskId = useSearchParams().get("task_id");
  if (!taskId) return null;
  const task = tasks?.find((t) => t.id === taskId);
  return (
    <div className="nav-item" title="当前任务" style={{ cursor: "default" }}>
      <div>
        <div className="g-sub">当前任务</div>
        <div className="brand-row" style={{ gap: 6 }}>
          <span style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 12 }}>
            {taskId.slice(0, 8)}
          </span>
          {task ? <span style={{ fontSize: 12 }}>{taskStatusLabel(task.status)}</span> : null}
        </div>
      </div>
    </div>
  );
}

function BidReviewLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  const { dark, toggle } = useDarkTheme();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading
    ? navItems
    : navItems.filter((n) => canPage(n.pageId));
  const groups = [0, 1].map((g) => visibleItems.filter((n) => n.group === g));
  // 徽标共享查询(与 TasksView 同 key 同缓存);数据未到时徽标不渲染(禁伪零)
  const { data: tasks } = useBidTasks();
  const badges = sidebarBadges(tasks ?? []);

  return (
    <div
      className="brx"
      data-theme={dark === true ? "dark" : dark === false ? "light" : undefined}
    >
      <div className="chrome">
        <aside className="chrome-side">
          <div className="chrome-brand">
            <div className="brand-row">
              <ClipboardCheck
                size={17}
                className="brand-ic"
                aria-hidden="true"
              />
              <div className="brand-txt">
                <h1>投标方案审查</h1>
                <p className="g-sub">Bid Proposal Review</p>
              </div>
            </div>
          </div>
          <Suspense fallback={null}>
            <TaskChip tasks={tasks} />
          </Suspense>
          {groups.map((items, g) =>
            items.length === 0 ? null : (
              <nav className="chrome-group" key={g}>
                <div className="g-label">{GROUP_LABELS[g]}</div>
                {items.map(({ href, label, icon: Icon, exact, badge }) => {
                  const isActive = exact
                    ? pathname === href
                    : pathname.startsWith(href);
                  const count = badge ? badges[badge] : 0;
                  return (
                    <Link
                      key={href}
                      href={href}
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
          <div className="chrome-foot">
            <button
              type="button"
              className="nav-item"
              onClick={toggle}
              title="切换深浅色"
            >
              {dark ? (
                <Sun size={15} className="ic" aria-hidden="true" />
              ) : (
                <Moon size={15} className="ic" aria-hidden="true" />
              )}
              深浅色
            </button>
          </div>
        </aside>
        <main className="chrome-main">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && pnpm test && pnpm lint && pnpm typecheck`
Expected: 新 flow 测试 5 用例绿;**既有 micro-B 测试原样绿**(href/label 未动);lint/typecheck 零错误。若 lint 报 import 字母序,按提示调整。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/bid-review/layout.tsx frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx
git commit -m "feat(bid-review): 侧栏流程化——流程序/三类徽标/当前任务chip(Plan1 T3)"
```

---

### Task 4: 全量验证 + 容器重启走查

- [ ] **Step 1: 前端三件套**

Run: `cd frontend && pnpm test && pnpm lint && pnpm typecheck`
Expected: 全绿。

- [ ] **Step 2: 容器重启(HMR 不可靠,按 CLAUDE.md 惯例)**

Run: `docker compose -p eai-docker restart frontend`
Expected: 容器重启完成;等 30s 后 `:2026/bid-review` 可达(nginx 若 502 先 `docker exec deer-flow-nginx nginx -s reload`,bug-3233 家族)。

- [ ] **Step 3: 真浏览器走查(登录态:CLAUDE.md dev 凭据,:2026/login 本地表单)**

检查点:
1. 侧栏顺序:任务总览→审查工作台→基准确认→复核工作台 | 规则治理组;
2. 有 awaiting_confirm 任务时「基准确认」带橙色 warn 计数;有 done+need_human 任务时「复核工作台」带计数;数量与任务总览列表一致;
3. 从任务总览点进任一任务(带 task_id)→ 侧栏出现「当前任务」chip,显示 id8+状态词;
4. 深浅色切换后徽标/chip 仍可读;
5. `/bid-review/review?task_id=…` 直开(复核页既有功能)不回归。
发现视觉问题(徽标间距/chip 配色)记入 walkthrough notes,Plan 3+ 顺带修,不在本计划扩scope。

- [ ] **Step 4: OpenWolf 收尾(执行会话职责)**

`.wolf/memory.md` 追加一行;`nav.ts`/测试文件如为新建,`.wolf/anatomy.md` 补条目。

---

## Self-Review 记录(已跑)

1. **Spec 覆盖**:spec §3.1 徽标三项 ✓(T1 计数+T3 渲染;「点击直达」显式移入 Plan 3,见头部收窄说明);§3.2 任务 chip ✓(T3;taskHref 工具 ✓ T1,页面逐步换用属各页计划);§3.3 共享 hook ✓(T2)、不引轮询 ✓;§3.4 权限点移入各页计划(头部已说明)。§4 各页改造不在本计划 ✓(系列拆分)。
2. **占位扫描**:无 TBD/「适当处理」;所有代码块完整可粘贴;命令均带期望输出。
3. **类型一致性**:`SidebarBadges` 三键在 nav.ts/T3 navItems/测试 mock 三处一致;`useBidTasks()` 返回 `{data}` 与 TanStack Query 返回形一致;`TASK_STATUS_LABELS` 词表与 TasksView L82-97 实测词表逐字一致(「失败」非「解析失败」)。
