import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";
import type { PropsWithChildren, ReactNode } from "react";

// UX 重构 Plan 1 T3:侧栏流程化三条行为——
// ① 审查闭环组按流程序排列(基准确认在复核工作台之前);
// ② 三类计数徽标(任务总览进行中/基准确认 warn/复核工作台待复核)来自共享任务查询;
// ③ URL 带 task_id 时侧栏渲染「当前任务」chip(id8+状态词)。
// 徽标 span 会并入 link 的 accessible name,名字断言用 regex。
// micro-B 回归门(tests/unit/app/bid-review-layout.dom.test.tsx)锁定 href/label
// 契约——本任务不改任何 href/label,该测试须原样保持绿。
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
    const links = screen.getAllByRole("link").map((l) => l.getAttribute("href"));
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
    expect(screen.getByRole("link", { name: /任务总览/ }).textContent).toContain(
      "2",
    );
    const baselineLink = screen.getByRole("link", { name: /基准确认/ });
    expect(baselineLink.textContent).toContain("1");
    expect(baselineLink.querySelector(".nav-cnt.warn")).not.toBeNull();
    expect(screen.getByRole("link", { name: /复核工作台/ }).textContent).toContain(
      "5",
    );
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

  // 2026-10-31 用户定案:选中任务号不进侧栏(摘 chip),随各页页头标题展示
  // (TaskTitleTag,原型「审查结果 · TBR-…」习语)。
  it("侧栏不再渲染「当前任务」chip(任务号改页头标题展示)", () => {
    mocks.search = new URLSearchParams("task_id=5a8e15b8-8ac4-4141-a7e0-2e125953380b");
    mocks.tasks = [
      fixture({
        id: "5a8e15b8-8ac4-4141-a7e0-2e125953380b",
        status: "awaiting_confirm",
      }),
    ];
    renderLayout();
    expect(screen.queryByText("当前任务")).toBeNull();
  });

  // UX 重构 Plan 2 T2(spec §3.2):nav 携带 effective task_id——六页互跳不断档,
  // 初始化(fallback 最新)即有选中态;治理页(规则库/规则效果)保持裸路径。
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
});
