import { expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";

import { GenerateView } from "@/extensions/bid-write/components/GenerateView";
import { GENERATE_COPY } from "@/extensions/bid-write/copy";

rs.mock("@/extensions/bid-write/hooks", () => ({
  useGenerateTask: () => ({
    data: null,
    error: null,
    isPending: false,
    mutateAsync: async () => null,
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
  cleanup();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <GenerateView />
    </QueryClientProvider>,
  );
}

it("页头与空状态使用业务文案，不含内核术语", () => {
  renderView();
  expect(
    screen
      .getAllByText(new RegExp(GENERATE_COPY.subtitle))
      .length,
  ).toBeGreaterThan(0);
  expect(screen.getByText(GENERATE_COPY.boqEmptyTitle)).toBeTruthy();
  expect(screen.getByText(GENERATE_COPY.boqEmptyHint)).toBeTruthy();
  expect(screen.getByText(GENERATE_COPY.paramsTitle)).toBeTruthy();
  expect(screen.getByText(GENERATE_COPY.runHint)).toBeTruthy();
  expect(screen.queryByText(/旋钮/)).toBeNull();
  expect(screen.queryByText(/meta\.knobs/)).toBeNull();
  expect(screen.queryByText(/boq_items/)).toBeNull();
});

it("无清单时折叠报价指标并提示参数写入位置", () => {
  renderView();
  expect(screen.queryAllByText("已出价")).toHaveLength(0);
  expect(screen.queryAllByText(/报价预[览选]合计/)).toHaveLength(0);
  expect(
    screen.getByText("本次未提取到工程量清单，报价相关指标不适用。"),
  ).toBeTruthy();
  expect(
    screen.getByText(GENERATE_COPY.FIELD_TARGETS.warranty_period),
  ).toBeTruthy();
});
