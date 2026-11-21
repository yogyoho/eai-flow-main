import { afterEach, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";

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
