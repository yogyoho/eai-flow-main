// 批三十四回归:保存成功后文档来源必须切换为云端(否则审批面板仍显示不可提交)。
import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

const putCalls: unknown[] = [];

rs.mock("@/extensions/bid-write/api", () => ({
  ApiError: class ApiError extends Error {},
  assertTaskDocument: async () => null,
  getTaskDocument: async () => ({
    ast: null,
    schema_version: "",
    updated_at: null,
  }),
  putTaskDocument: async (_taskId: string, body: unknown) => {
    putCalls.push(body);
    return {
      ast: (body as { ast: unknown }).ast,
      schema_version: "0.2.0",
      updated_at: "2026-11-15T01:00:00Z",
    };
  },
}));

rs.mock("@/extensions/bid-write/hooks", () => ({
  useSelectedWriteTask: () => ({
    taskId: "t1",
    task: {
      id: "t1",
      biz_no: "TBW-1",
      status: "matrix_ready",
      progress: {},
      error: null,
      project_name: "回归项目",
      lot_name: null,
      tender_no: null,
      created_at: null,
      engine_meta: { fields: {}, knobs: {}, docs: [] },
    },
    isLoading: false,
    error: null,
  }),
  useBidWriteMatrix: () => ({
    data: { items: [], total: 0 },
    isLoading: false,
    error: null,
    refetch: async () => undefined,
  }),
  useBidWriteGaps: () => ({
    data: { items: [], assertions: null },
    isLoading: false,
    error: null,
  }),
  useTaskMetrics: () => ({ data: { metrics: null, run_at: null } }),
}));

rs.mock("@/extensions/bid-write/components/ApprovalPanel", () => ({
  ApprovalPanel: () => null,
}));

rs.mock("@/extensions/bid-write/editor/BidWriteEditor", async () => {
  const { demoWorkbenchAst } =
    await import("@/extensions/bid-write/editor/demo");
  const { forwardRef, useEffect, useImperativeHandle } = await import("react");
  const MockEditor = forwardRef(function MockEditor(
    props: {
      onDocChange?: (ast: unknown, flags: unknown) => void;
      ariaLabel?: string;
    },
    ref,
  ) {
    useImperativeHandle(ref, () => ({
      undo: () => undefined,
      redo: () => undefined,
      serializeNow: () => demoWorkbenchAst(),
      scrollToSection: () => true,
    }));
    const onDocChange = props.onDocChange;
    useEffect(() => {
      onDocChange?.(demoWorkbenchAst(), { canUndo: false, canRedo: false });
    }, [onDocChange]);
    return <div data-testid="mock-editor" aria-label={props.ariaLabel} />;
  });
  return { BidWriteEditor: MockEditor };
});

import { WorkbenchView } from "@/extensions/bid-write/components/WorkbenchView";

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  cleanup();
  putCalls.length = 0;
});

describe("WorkbenchView 保存来源", () => {
  it("保存成功后从演示文档切到云端文档", async () => {
    render(<WorkbenchView />, { wrapper });
    expect(await screen.findByText("演示文档")).toBeTruthy();
    expect(
      await screen.findByLabelText("投标正文编辑器（演示文档）"),
    ).toBeTruthy();
    expect(await screen.findByTestId("mock-editor")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("云端文档")).toBeTruthy();
    expect(
      await screen.findByLabelText("投标正文编辑器（云端文档）"),
    ).toBeTruthy();
    expect(putCalls).toHaveLength(1);
  });
});
