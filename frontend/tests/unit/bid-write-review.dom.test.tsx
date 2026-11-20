import { expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { ReviewView } from "@/extensions/bid-write/components/ReviewView";
import { REVIEW_COPY } from "@/extensions/bid-write/copy";

rs.mock("@/extensions/bid-write/hooks", () => ({
  useBidWriteGaps: () => ({
    data: null,
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
