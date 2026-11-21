// 批卅六:③「重建正文」按钮——确认后 mutateAsync 携带 regenerate_document=true;
// 取消确认不调用。旋钮合并语义不变(开始生成不带开关)。
import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

const mutateCalls: unknown[] = [];

rs.mock("@/extensions/bid-write/hooks", () => ({
  useSelectedWriteTask: () => ({
    taskId: "t1",
    task: {
      id: "t1",
      biz_no: "TBW-1",
      status: "matrix_ready",
      progress: {},
      error: null,
      project_name: "重建回归",
      lot_name: null,
      tender_no: null,
      created_at: null,
      engine_meta: {
        fields: {
          "tender.boq_items": [{ id: "1.1", name: "设备", qty: 2, unit: "套" }],
        },
        knobs: {},
        docs: [],
      },
    },
    isLoading: false,
    error: null,
  }),
  useGenerateTask: () => ({
    mutateAsync: async (input: unknown) => {
      mutateCalls.push(input);
      return { verdict: {}, blocked: false, biz_no: "TBW-1", status: "matrix_ready" };
    },
    isPending: false,
    data: null,
    error: null,
  }),
}));

import { GenerateView } from "@/extensions/bid-write/components/GenerateView";

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  cleanup();
  mutateCalls.length = 0;
});

describe("GenerateView 重建正文", () => {
  it("确认后 regenerate_document=true 透传", async () => {
    const confirmSpy = rs
      .spyOn(window, "confirm")
      .mockImplementation(() => true);
    render(<GenerateView />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "重建正文" }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(mutateCalls).toHaveLength(1);
    const body = mutateCalls[0] as { knobs: Record<string, unknown> };
    expect(body.knobs.regenerate_document).toBe(true);
    confirmSpy.mockRestore();
  });

  it("取消确认不发起请求", async () => {
    const confirmSpy = rs
      .spyOn(window, "confirm")
      .mockImplementation(() => false);
    render(<GenerateView />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "重建正文" }));
    expect(mutateCalls).toHaveLength(0);
    confirmSpy.mockRestore();
  });
});
