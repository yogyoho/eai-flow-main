import { afterEach, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ReviewView } from "@/extensions/bid-write/components/ReviewView";
import { REVIEW_COPY } from "@/extensions/bid-write/copy";
import { gatesFromData } from "@/extensions/bid-write/helpers";

rs.mock("@/extensions/bid-write/hooks", () => ({
  useBidWriteGaps: () => ({
    data: null,
    error: null,
    isLoading: false,
    refetch: async () => undefined,
  }),
  useDeliveryGates: () => ({
    gates: gatesFromData({
      matrixBlocked: null,
      assertionsBlocked: null,
      noMaterialCount: null,
      revisionApproved: null,
    }),
    blocked: false,
  }),
  useBidWriteRegistry: () => ({
    data: {
      schema_version: "1.0.0",
      levels: {
        D0: {
          name: "阻断",
          blk: true,
          render: "TODO_BLOCK",
          pre_review_state: "MISSING",
          retry: "self_refine_max_2",
        },
        D1: {
          name: "降级",
          blk: false,
          render: "MARK_YELLOW",
          pre_review_state: "UNKNOWN",
          retry: "self_refine_max_1",
        },
        D2: {
          name: "提示",
          blk: false,
          render: "BOARD_ONLY",
          pre_review_state: null,
          retry: "none",
        },
        D3: {
          name: "静默",
          blk: false,
          render: "NONE",
          pre_review_state: null,
          retry: "none",
        },
      },
      items: [
        {
          id: "SK-BL-004",
          skill: "bid_letter",
          name: "投标函主体一致",
          level: "D0",
          blocks_export: true,
          rule_ref: "L1-016",
          expr: "投标人名称与 material.bidder_profile 完全一致",
          human_action: "核对营业执照主体信息",
          delegates_to: null,
        },
      ],
    },
    error: null,
    isLoading: false,
    refetch: async () => undefined,
  }),
  useSelectedWriteTask: () => ({
    taskId: "t1",
    task: { id: "t1", status: "matrix_ready", project_name: "测试项目" },
    tasks: [{ id: "t1", status: "matrix_ready", project_name: "测试项目" }],
    isLoading: false,
    error: null,
  }),
}));

afterEach(() => {
  cleanup();
});

function renderView(): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ReviewView />
    </QueryClientProvider>,
  );
}

it("底部说明使用业务文案，不含端点/级别术语", () => {
  renderView();
  expect(screen.getByText(REVIEW_COPY.bottomNote)).toBeTruthy();
  expect(screen.queryByText(/只读结果端点/)).toBeNull();
  expect(screen.queryByText(/blocks_export/)).toBeNull();
});

it("页头动作移除重跑入口并展示检查快照说明", () => {
  renderView();
  expect(screen.queryByRole("button", { name: /重跑断言/ })).toBeNull();
  expect(screen.getByText(REVIEW_COPY.snapshotBadge)).toBeTruthy();
});

it("页头首位提供回退到工作台的链接", () => {
  renderView();
  const backLink = screen.getByRole("link", { name: "← 上一步" });
  expect(backLink.getAttribute("href")).toContain(
    "/bid-write/workbench?task_id=t1",
  );
});

it("质量规则说明默认收起，展开后展示等级行为与规则明细", () => {
  renderView();

  const trigger = screen.getByRole("button", { name: "质量规则说明" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("等级行为")).toBeNull();
  expect(screen.queryByText("投标函主体一致")).toBeNull();

  fireEvent.click(trigger);

  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("等级行为")).toBeTruthy();
  expect(
    screen.getByText(
      "D0 必须通过：阻止导出，标红并列入待补清单，自动重试最多 2 次",
    ),
  ).toBeTruthy();
  expect(
    screen.getByText(
      "D1 建议：不阻断导出，标黄提醒，显示未知，自动重试最多 1 次",
    ),
  ).toBeTruthy();
  expect(screen.getByText("投标函主体一致")).toBeTruthy();
  expect(screen.getByText("SK-BL-004")).toBeTruthy();
  expect(screen.getByText("核对营业执照主体信息")).toBeTruthy();
});
