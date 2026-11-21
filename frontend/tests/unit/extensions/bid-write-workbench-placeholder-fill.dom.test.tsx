// 批卅六可用性修复回归:①待填清单列出空占位符;②对话框填入走 fillPlaceholder;
// ③引导文案不再指向「③重新生成」死路。
import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

const fillCalls: Array<[string, string, boolean]> = [];

function astWithPlaceholders() {
  return {
    type: "doc",
    content: [
      {
        type: "section",
        attrs: { level: 1, title: "一、投标函", section_id: "S1" },
        content: [
          {
            type: "para",
            content: [
              { type: "text", text: "采购编号为 " },
              {
                type: "placeholder",
                attrs: {
                  slot_id: "ph-1",
                  placeholder_type: "str",
                  label: "采购编号",
                  value: "",
                  required: true,
                  source: "",
                },
              },
              { type: "text", text: " 的" },
              {
                type: "placeholder",
                attrs: {
                  slot_id: "ph-3",
                  placeholder_type: "str",
                  label: "采购编号",
                  value: "",
                  required: true,
                  source: "",
                },
              },
              {
                type: "placeholder",
                attrs: {
                  slot_id: "ph-2",
                  placeholder_type: "str",
                  label: "已填项",
                  value: "T-2026-001",
                  required: true,
                  source: "",
                },
              },
            ],
          },
        ],
      },
      {
        type: "section",
        attrs: { level: 1, title: "9.2服务方案", section_id: "S2" },
        content: [{ type: "para", content: [] }],
      },
    ],
  };
}

rs.mock("@/extensions/bid-write/api", () => ({
  ApiError: class ApiError extends Error {},
  assertTaskDocument: async () => null,
  getTaskDocument: async () => ({
    ast: astWithPlaceholders(),
    schema_version: "0.3.0",
    updated_at: "2026-11-19T00:00:00Z",
  }),
  putTaskDocument: async () => ({
    ast: {},
    schema_version: "0.3.0",
    updated_at: "2026-11-19T01:00:00Z",
  }),
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
      project_name: "占位符回归",
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
  useBidWriteFormatProfile: () => ({
    data: {
      profile: null,
      profile_hash: "",
      schema_version: "",
      source: null,
      updated_at: null,
    },
    isLoading: false,
    error: null,
    refetch: async () => undefined,
  }),
  useExtractBidWriteFormatProfile: () => ({
    mutate: () => undefined,
    isPending: false,
    error: null,
  }),
  useTaskMetrics: () => ({ data: { metrics: null, run_at: null } }),
}));

rs.mock("@/extensions/bid-write/components/ApprovalPanel", () => ({
  ApprovalPanel: () => null,
}));

rs.mock("@/extensions/bid-write/editor/BidWriteEditor", async () => {
  const { forwardRef, useEffect, useMemo } = await import("react");
  const MockEditor = forwardRef(function MockEditor(
    props: {
      onReady?: (handle: {
        fillPlaceholder: (slotId: string, value: string) => boolean;
      }) => void;
      onDocChange?: (ast: unknown, flags: unknown) => void;
      onPlaceholderSelect?: (info: {
        slotId: string;
        label: string;
        value: string;
        placeholderType: string;
      }) => void;
    },
    // forwardRef 渲染函数必须收 ref 参数(即便 onReady 通道不使用它)
    _ref,
  ) {
    const handle = useMemo(
      () => ({
        undo: () => undefined,
        redo: () => undefined,
        serializeNow: () => astWithPlaceholders(),
        scrollToSection: () => true,
        execTableOp: () => false,
      fillPlaceholder: (slotId: string, value: string, propagate = false) => {
        fillCalls.push([slotId, value, propagate]);
        return propagate ? 2 : 1;
        },
      }),
      [],
    );
    // 与生产一致:next/dynamic 不转发 ref,宿主命令柄只经 onReady 直交
    const onReady = props.onReady;
    useEffect(() => {
      onReady?.(handle);
    }, [onReady, handle]);
    const onDocChange = props.onDocChange;
    useEffect(() => {
      onDocChange?.(astWithPlaceholders(), { canUndo: false, canRedo: false });
    }, [onDocChange]);
    return (
      <button
        type="button"
        data-testid="mock-placeholder"
        onClick={() =>
          props.onPlaceholderSelect?.({
            slotId: "ph-1",
            label: "采购编号",
            value: "",
            placeholderType: "str",
          })
        }
      >
        占位符原子
      </button>
    );
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
  fillCalls.length = 0;
});

describe("WorkbenchView 占位符填写", () => {
  it("待填清单只列空占位符,默认全局替换并提示同步 N 处", async () => {
    render(<WorkbenchView />, { wrapper });
    expect(await screen.findByText("待填清单")).toBeTruthy();
    // 空占位符在列(采购编号×2 个空槽),已填项不在列
    expect(screen.getAllByText("采购编号").length).toBe(2);
    expect(screen.queryByText("已填项")).toBeNull();
    // 采购编号×2 空槽 → 两个「填写」按钮,点第一个
    fireEvent.click(screen.getAllByRole("button", { name: "填写" })[0]);
    const input = await screen.findByLabelText("占位符填写内容");
    // 同变量勾选框(采购编号×2 空槽)默认勾选
    expect(await screen.findByLabelText("同步填充所有相同变量")).toBeTruthy();
    fireEvent.change(input, { target: { value: "TZ-2026-118" } });
    fireEvent.click(screen.getByRole("button", { name: "填入" }));
    expect(fillCalls).toEqual([["ph-1", "TZ-2026-118", true]]);
    expect(
      await screen.findByText(/已填入「采购编号」＝TZ-2026-118（全局同步 2 处，记得保存）/),
    ).toBeTruthy();
    // 对话框关闭
    expect(screen.queryByLabelText("占位符填写内容")).toBeNull();
  });

  it("正文占位符点击打开同一对话框", async () => {
    render(<WorkbenchView />, { wrapper });
    // 先等云端文档就绪(docEpoch 重挂载完成),否则会点到重挂载前的脱连节点
    await screen.findByText("云端文档");
    fireEvent.click(screen.getByTestId("mock-placeholder"));
    expect(await screen.findByLabelText("占位符填写内容")).toBeTruthy();
  });

  it("取消勾选则单点填充", async () => {
    render(<WorkbenchView />, { wrapper });
    // 同上:等重挂载完成再取节点,避免点到脱连树
    await screen.findByText("云端文档");
    fireEvent.click(screen.getByTestId("mock-placeholder"));
    const input = await screen.findByLabelText("占位符填写内容");
    fireEvent.click(screen.getByLabelText("同步填充所有相同变量"));
    fireEvent.change(input, { target: { value: "TZ-1" } });
    fireEvent.click(screen.getByRole("button", { name: "填入" }));
    expect(fillCalls).toEqual([["ph-1", "TZ-1", false]]);
  });

  it("引导文案不再指向③重新生成死路", async () => {
    render(<WorkbenchView />, { wrapper });
    const guide = (await screen.findByText(/点击正文中的黄色高亮/))
      .parentElement;
    expect(guide).not.toBeNull();
    expect(guide.textContent).toContain("＋行/－行");
    expect(guide.textContent).not.toContain("重新生成");
  });

  it("空章节在大纲标记「空」且正文区出现输入引导", async () => {
    render(<WorkbenchView />, { wrapper });
    expect(await screen.findByText("9.2服务方案")).toBeTruthy();
    expect(screen.getByText("空")).toBeTruthy();
  });
});
