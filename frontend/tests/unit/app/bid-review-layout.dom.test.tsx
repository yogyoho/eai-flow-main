import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen } from "@testing-library/react";
import type { PropsWithChildren, ReactNode } from "react";

// micro-B 2026-10-29 站内入口回归门:/bid-review/rules(Task 17 落地)此前无任何
// 站内入口可达(e242a00bf 遗留②——nav 注册属 Task 12 范畴遗漏)。锁定 bid-review
// layout 子路由导航(照 contract-price/bid-quote 先例)的三条行为:
// ① 四个已注册页(bid:page:tasks/workbench/baseline/rules)各有一条导航入口;
// ② canPage 拒绝的页入口隐藏(权限点过滤,同 contract-price layout);
// ③ 权限加载中 fail-open 全显(同先例,防权限未就绪时导航闪没)。
const mocks = rs.hoisted(() => ({
  denied: [] as string[],
  loading: false,
}));

rs.mock("next/navigation", () => ({
  usePathname: () => "/bid-review",
  // UX 重构 Plan 1:layout 新增 TaskChip 依赖 useSearchParams(Suspense 内);
  // 本文件断言不带 task_id 的默认态,恒返回空查询串。
  useSearchParams: () => new URLSearchParams(),
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
  usePermission: () => ({
    canPage: (pageId: string) => !mocks.denied.includes(pageId),
    isLoading: mocks.loading,
  }),
  // EAI-CUSTOM: layout 脱壳后自备 providers(原 ShellLayout 提供),测试透传
  PermissionProvider: ({ children }: PropsWithChildren) => <>{children}</>,
}));

// EAI-CUSTOM (2026-10-30 独立子系统改造): layout 不再经 ShellLayout,换为
// 自绘 chrome + StandaloneGate(登录门)。mock 登录态为已登录,门直接放行。
rs.mock("@/extensions/hooks/useAuth", () => ({
  AuthProvider: ({ children }: PropsWithChildren) => <>{children}</>,
  useAuth: () => ({ user: { id: "u1" }, isLoading: false }),
}));

rs.mock("@/components/workspace/workspace-login-redirect", () => ({
  WorkspaceLoginRedirect: () => null,
}));

// UX 重构 Plan 1:layout 消费共享 useBidTasks(侧栏徽标);本文件只测导航契约,
// 徽标恒无数据(data: undefined)→ 不渲染,契约断言不受影响。
rs.mock("@/extensions/bid-review/hooks", () => ({
  bidReviewKeys: { tasks: ["bid-review", "tasks"] },
  useBidTasks: () => ({ data: undefined }),
}));

import BidReviewLayout from "@/app/bid-review/layout";

function renderLayout() {
  return render(
    <BidReviewLayout>
      <div>page body</div>
    </BidReviewLayout>,
  );
}

describe("bid-review layout 子路由导航(micro-B 站内入口)", () => {
  beforeEach(() => {
    mocks.denied = [];
    mocks.loading = false;
  });
  afterEach(cleanup);

  it("四个已注册页各有一条入口,规则库指向 /bid-review/rules", () => {
    renderLayout();
    // 2026-10-30 用户定案:「任务列表」更名「任务总览」(首项即任务工作台,与审查工作台区分)
    expect(
      screen.getByRole("link", { name: "任务总览" }).getAttribute("href"),
    ).toBe("/bid-review");
    expect(
      screen.getByRole("link", { name: "审查工作台" }).getAttribute("href"),
    ).toBe("/bid-review/workbench");
    expect(
      screen.getByRole("link", { name: "基准确认" }).getAttribute("href"),
    ).toBe("/bid-review/baseline");
    expect(
      screen.getByRole("link", { name: "规则库" }).getAttribute("href"),
    ).toBe("/bid-review/rules");
    // children 照常渲染(布局是包装不是替换)
    expect(screen.getByText("page body")).not.toBeNull();
  });

  it("canPage 拒绝的页入口隐藏,其余照常", () => {
    mocks.denied = ["bid:page:rules"];
    renderLayout();
    expect(screen.queryByRole("link", { name: "规则库" })).toBeNull();
    expect(screen.queryByRole("link", { name: "任务总览" })).not.toBeNull();
    expect(screen.queryByRole("link", { name: "审查工作台" })).not.toBeNull();
  });

  it("权限加载中 fail-open 全显(同 contract-price 先例)", () => {
    mocks.loading = true;
    renderLayout();
    expect(screen.queryByRole("link", { name: "规则库" })).not.toBeNull();
    expect(screen.queryByRole("link", { name: "基准确认" })).not.toBeNull();
  });
});
