import { afterEach, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

rs.mock("@/extensions/bid-write/hooks", () => ({
  useBidWriteTasks: () => ({
    data: {
      items: [
        {
          id: "task-garbled",
          biz_no: "BW-0001",
          status: "matrix_ready",
          progress: { pct: 100 },
          error: null,
          project_name: "M0 ù¾¼Æ·ÃÉèÏîÄ¿",
          lot_name: "标段一",
          tender_no: "T-2026-1",
          created_at: "2026-11-13T08:00:00Z",
          engine_meta: { matrix_counts: { total: 3, star: 1, blocked: 0 } },
        },
      ],
    },
    error: null,
    isLoading: false,
    isFetching: false,
    refetch: async () => undefined,
  }),
  useCreateBidWriteTask: () => ({
    isPending: false,
    mutateAsync: async () => null,
  }),
  useBidWriteRegistry: () => ({
    data: {
      schema_version: "p0-v1",
      levels: {
        D0: {
          name: "必须通过",
          blk: true,
          render: "TODO_BLOCK",
          pre_review_state: "MISSING",
          retry: "self_refine_max_2",
        },
      },
      items: [
        {
          id: "SK-BL-01",
          skill: "bid_letter",
          name: "投标函主体一致",
          level: "D0",
          blocks_export: true,
          rule_ref: "tender.bidder_rules",
          expr: "主体信息一致",
          human_action: "核对主体信息",
          delegates_to: null,
        },
      ],
    },
    error: null,
    isLoading: false,
    refetch: async () => undefined,
  }),
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write",
  useSearchParams: () => new URLSearchParams(),
}));

import { StageDots } from "@/extensions/bid-write/components/primitives";
import { ProjectsView } from "@/extensions/bid-write/components/ProjectsView";
import { RegistryView } from "@/extensions/bid-write/components/RegistryView";
import {
  PROJECTS_COPY,
  REGISTRY_COPY,
} from "@/extensions/bid-write/copy";

function renderWithQueryClient(ui: React.ReactNode): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

it("StageDots 每个圆点带阶段名 title", () => {
  const { container } = render(<StageDots status="matrix_ready" />);
  const dots = container.querySelectorAll(".stage-dots i");

  expect(dots.length).toBe(6);
  expect(dots[0]?.getAttribute("title")).toContain("解析确认");
  expect(dots[5]?.getAttribute("title")).toContain("导出适配");
});

it("项目列表乱码名兜底，流程说明使用用户语言", () => {
  renderWithQueryClient(<ProjectsView />);

  expect(screen.getByText(PROJECTS_COPY.untitledProject)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /流程说明/ }));

  expect(screen.getByText(PROJECTS_COPY.flowIntro)).toBeTruthy();
  expect(screen.getByText("治理区（跨任务可用）")).toBeTruthy();
  expect(screen.queryByText(/created → parsing/)).toBeNull();
  expect(screen.queryByText(/bidder_profile/)).toBeNull();
  expect(screen.queryByText(/blocked\/draft\/confirmed/)).toBeNull();
  expect(screen.queryByText(/互不推导/)).toBeNull();
  expect(screen.queryByText(/不误伤/)).toBeNull();
  expect(
    screen.getByText("资质素材库与质量规则中心随时可从左侧进入。"),
  ).toBeTruthy();
});

it("注册表页头与等级行为表渲染业务词", () => {
  renderWithQueryClient(<RegistryView />);

  expect(screen.getByText(REGISTRY_COPY.title)).toBeTruthy();
  expect(screen.getByText(REGISTRY_COPY.subtitle)).toBeTruthy();
  expect(screen.getByText("必须通过（阻断导出）")).toBeTruthy();
  expect(screen.getByText("标红并列入待补清单")).toBeTruthy();
  expect(screen.getByText("显示缺失")).toBeTruthy();
  expect(screen.getByText("自动重试最多 2 次")).toBeTruthy();
  expect(screen.queryByText(/TODO_BLOCK/)).toBeNull();
  expect(screen.queryByText(/MISSING/)).toBeNull();
  expect(screen.queryByText(/self_refine/)).toBeNull();
});
