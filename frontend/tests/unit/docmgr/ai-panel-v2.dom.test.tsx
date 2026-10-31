import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { RefObject } from "react";

import DocAIAgentPanel from "@/extensions/docmgr/DocAIAgentPanel";
import type { PersonalBlockNoteEditorRef } from "@/extensions/docmgr/PersonalBlockNoteEditor";

// ─── 面板 v2 dom 测试：空态宫格 launcher / 回复操作条 / 发送⇄停止 ─────────
// useStream、docmgrApi、useDocAITask 全部 mock（面板层测试不碰真实流与任务通道）。

const m = rs.hoisted(() => ({
  submit: rs.fn(),
  stop: rs.fn(),
  startTask: rs.fn(),
  startReview: rs.fn(),
  writeText: rs.fn(() => Promise.resolve()),
  streamState: { isLoading: false, messages: [] as unknown[] },
  // 复审 I-1: busy 互跨禁用断言——两通道 busy 可控 + 挂载 props 捕获
  docTaskBusy: false,
  reviewBusy: false,
  docTaskState: { sections: [] } as Record<string, unknown>,
  reviewState: { reviewType: "consistency" } as Record<string, unknown>,
  capturedTask: null as Record<string, unknown> | null,
  capturedReview: null as Record<string, unknown> | null,
}));

rs.mock("@langchain/langgraph-sdk/react", () => ({
  useStream: () => ({
    isLoading: m.streamState.isLoading,
    messages: m.streamState.messages,
    stop: m.stop,
    submit: m.submit,
    values: {},
  }),
}));

rs.mock("@/core/models/hooks", () => ({
  useModels: () => ({ models: [] }),
}));

rs.mock("@/core/api", () => ({ getAPIClient: () => ({}) }));

rs.mock("@/core/streamdown/components", () => ({
  SafeStreamdown: () => null,
}));

rs.mock("@/extensions/api", () => ({
  docmgrApi: {
    createPersonalVersion: rs.fn(() => Promise.resolve({})),
    aiTransformStream: rs.fn(() => Promise.resolve()),
  },
}));

// DocAITaskArea 整体替换：PRESETS 按 Chunk 1 冻结版复刻（面板宫格消费它），
// useDocAITask 返回受控 spy——launcher「开始执行」断言 startTask 收到的 sections。
rs.mock("@/extensions/docmgr/DocAITaskArea", () => ({
  PRESETS: [
    { id: "polish", label: "全文润色" },
    { id: "proofread", label: "全文校对" },
    { id: "terminology", label: "术语统一" },
    { id: "format", label: "格式规范" },
    { id: "toc", label: "生成目录" },
    { id: "summary", label: "全文摘要" },
  ],
  DocAITaskArea: (props: Record<string, unknown>) => {
    m.capturedTask = props;
    return null;
  },
  useDocAITask: () => ({
    state: m.docTaskState,
    busy: m.docTaskBusy,
    undoBlocked: false,
    markUserEdited: rs.fn(),
    startTask: m.startTask,
    cancel: rs.fn(),
    applySection: rs.fn(),
    rejectSection: rs.fn(),
    restoreSection: rs.fn(),
    applyAll: rs.fn(),
    undoAll: rs.fn(),
    dismiss: rs.fn(),
    retrySection: rs.fn(),
    insertSummary: rs.fn(),
  }),
}));

// EAI-CUSTOM (全文操作 M2 Chunk 2): 审查任务区整体替换（面板层不碰真实审查流）——
// REVIEW_PRESETS 按 Chunk 2 冻结版复刻（宫格第二组消费它），startReview 走受控 spy。
rs.mock("@/extensions/docmgr/DocAIReviewArea", () => ({
  REVIEW_PRESETS: [
    { id: "consistency", label: "术语一致性审查" },
    { id: "numbering", label: "编号连续性审查" },
    { id: "units", label: "公式单位审查" },
  ],
  DocAIReviewArea: (props: Record<string, unknown>) => {
    m.capturedReview = props;
    return null;
  },
  useDocAIReview: () => ({
    state: m.reviewState,
    busy: m.reviewBusy,
    undoBlocked: false,
    hasSnapshot: false,
    markUserEdited: rs.fn(),
    startReview: m.startReview,
    cancel: rs.fn(),
    applyFix: rs.fn(),
    applyAllFixes: rs.fn(),
    undoAllFixes: rs.fn(),
    dismissFinding: rs.fn(),
    restoreFinding: rs.fn(),
    reset: rs.fn(),
  }),
}));

// 复审#1 fixture：index（块下标）与 section（后端 split_sections 桶下标）刻意
// 错开——有前导节（preamble=1）时首标题 section=1，证明面板投递/展示用 section 空间。
const HEADINGS = [
  { index: 2, level: 1, text: "概述", section: 1 },
  { index: 5, level: 1, text: "设计参数", section: 2 },
  { index: 9, level: 1, text: "水力计算", section: 3 },
];

function makeEditorRef(headings = HEADINGS) {
  const ed = {
    getHeadings: () => headings.map((h) => ({ ...h })),
    getSectionText: rs.fn(() => ""),
    matchAnchor: rs.fn((): null => null),
    getMarkdown: () => Promise.resolve("# 文档"),
    getBlockAnchors: rs.fn((): never[] => []),
    snapshotBlocks: rs.fn((): never[] => []),
    restoreBlocks: rs.fn(),
    applyOperations: rs.fn(),
    scrollToAnchor: rs.fn(),
    onDocumentChange: rs.fn(() => rs.fn()),
  };
  return {
    current: ed,
  } as unknown as RefObject<PersonalBlockNoteEditorRef | null>;
}

const baseProps = (editorRef: ReturnType<typeof makeEditorRef>, id = "t1") => ({
  docTitle: "测试文档",
  docRelPath: "docs/a.md",
  threadId: id,
  editorRef,
  onClose: rs.fn(),
  subThreadId: id,
  ensureThread: () => Promise.resolve(id),
  isCreating: false,
  resetThread: () => Promise.resolve(),
  onClearHistory: rs.fn(),
});

function seedUserMessages(threadId: string, msgs: string[]) {
  localStorage.setItem(
    `docmgr-ai-usermessages:${threadId}`,
    JSON.stringify(msgs),
  );
}

const originalFetch = globalThis.fetch;

describe("DocAIAgentPanel v2 空态（方案三）", () => {
  beforeEach(() => {
    m.streamState.isLoading = false;
    m.streamState.messages = [];
    m.startTask.mockClear();
    m.startReview.mockClear();
    m.docTaskBusy = false;
    m.reviewBusy = false;
    m.capturedTask = null;
    m.capturedReview = null;
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: m.writeText },
      configurable: true,
    });
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    globalThis.fetch = originalFetch;
  });

  it("空态渲染六宫格，未选中时不出现 launcher", async () => {
    render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    for (const label of [
      "全文润色",
      "全文校对",
      "术语统一",
      "格式规范",
      "生成目录",
      "全文摘要",
    ]) {
      expect(screen.getByText(label)).not.toBeNull();
    }
    expect(screen.queryByText(/执行预览/)).toBeNull();
    expect(screen.queryByText("全部章节")).toBeNull();
  });

  it("选节 → 开始执行：startTask 收到正确 sections（split_sections 桶下标数组）", async () => {
    render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    fireEvent.click(screen.getByText("全文校对"));

    // launcher 出现：预览标题 + 目标 pills（全部章节默认 on + 3 个节 pill）
    expect(await screen.findByText(/执行预览/)).not.toBeNull();
    const allPill = screen.getByText("全部章节");
    // 节 pills 来自编辑器标题快照（进入空态后轮询捕获，异步到达）；
    // 展示用 section 空间：设计参数 section=2 → §3（块下标是 5）
    const sectionPill = await screen.findByText("§3 设计参数");
    expect(allPill.getAttribute("aria-pressed")).toBe("true");

    // 互斥：点节 pill → 节 on、全部 off
    fireEvent.click(sectionPill);
    expect(sectionPill.getAttribute("aria-pressed")).toBe("true");
    expect(allPill.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(screen.getByText("开始执行"));
    await waitFor(() => expect(m.startTask).toHaveBeenCalled());
    expect(m.startTask).toHaveBeenCalledWith("proofread", [2]);
  });

  it("保持全部章节 → 开始执行：startTask sections 为 undefined", async () => {
    render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    fireEvent.click(screen.getByText("全文润色"));
    fireEvent.click(await screen.findByText("开始执行"));
    await waitFor(() => expect(m.startTask).toHaveBeenCalled());
    expect(m.startTask).toHaveBeenCalledWith("polish", undefined);
  });

  it("0 标题文档：launcher 仅「全部章节」+ 提示，不崩溃", async () => {
    render(<DocAIAgentPanel {...baseProps(makeEditorRef([]))} />);
    fireEvent.click(screen.getByText("全文摘要"));
    expect(await screen.findByText(/仅支持全文执行/)).not.toBeNull();
    expect(screen.getByText("全部章节")).not.toBeNull();
    expect(screen.queryByText(/^§/)).toBeNull();
  });

  // EAI-CUSTOM (全文操作 M2 Chunk 2): 宫格第二组「深度审查」——审查卡选中断言 +
  // 「开始执行」走 startReview（审查固定全文档，sections 不传）。
  it("深度审查卡：选中出 launcher（全文档审查提示），开始执行走 startReview", async () => {
    render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    expect(screen.getByText("深度审查")).not.toBeNull();
    fireEvent.click(screen.getByText("术语一致性审查"));
    expect(await screen.findByText(/全文档审查/)).not.toBeNull();
    fireEvent.click(screen.getByText("开始执行"));
    await waitFor(() => expect(m.startReview).toHaveBeenCalled());
    expect(m.startReview).toHaveBeenCalledWith("consistency");

    // 跨组互斥：改写卡与审查卡共享同一选中态（卡按钮经 label span closest("button") 取）
    fireEvent.click(screen.getByText("全文润色"));
    expect(
      screen
        .getByText("术语一致性审查")
        .closest("button")!
        .getAttribute("aria-pressed"),
    ).toBe("false");
    // 改写卡文案在 launcher 标题重复出现，用 desc 文案唯一定位卡片按钮
    expect(
      screen
        .getByText("逐节提升表达，保留结构")
        .closest("button")!
        .getAttribute("aria-pressed"),
    ).toBe("true");
  });

  // EAI-CUSTOM (全文操作 M2 复审 I-1): busy 互跨禁用——审查运行中改写任务卡收到
  // busy=true（批量栏 !busy 门控即冻结）；改写运行中审查区收到 actionsDisabled=true。
  it("busy 互跨禁用：审查运行中冻结任务卡；改写运行中冻结审查区", async () => {
    m.reviewBusy = true;
    let r = render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    expect(m.capturedTask?.busy).toBe(true);
    expect(m.capturedReview?.busy).toBe(true);
    expect(m.capturedReview?.actionsDisabled).toBe(false);
    r.unmount();

    m.docTaskBusy = true;
    m.reviewBusy = false;
    r = render(<DocAIAgentPanel {...baseProps(makeEditorRef())} />);
    expect(m.capturedReview?.actionsDisabled).toBe(true);
    expect(m.capturedTask?.busy).toBe(true);
    r.unmount();
  });
});

describe("DocAIAgentPanel v2 消息流（方案一）", () => {
  beforeEach(() => {
    m.streamState.isLoading = false;
    m.streamState.messages = [];
    m.writeText.mockClear();
    m.submit.mockClear();
    m.stop.mockClear();
    m.docTaskBusy = false;
    m.reviewBusy = false;
    m.capturedTask = null;
    m.capturedReview = null;
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: m.writeText },
      configurable: true,
    });
    globalThis.fetch = rs.fn(() => Promise.resolve({ ok: true })) as never;
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    globalThis.fetch = originalFetch;
  });

  it("复制：写入剪贴板并显示「已复制」反馈", async () => {
    seedUserMessages("t2", ["帮我校对"]);
    m.streamState.messages = [{ id: "a1", type: "ai", content: "回复内容" }];
    render(<DocAIAgentPanel {...baseProps(makeEditorRef(), "t2")} />);

    fireEvent.click(await screen.findByTitle("复制"));
    await waitFor(() => expect(m.writeText).toHaveBeenCalledWith("回复内容"));
    expect(screen.getByText("已复制")).not.toBeNull();
  });

  it("重新生成：仅最后一条回复有入口，点击重发最后一条用户消息", async () => {
    seedUserMessages("t3", ["第一条", "最后指令"]);
    m.streamState.messages = [
      { id: "a1", type: "ai", content: "回复一" },
      { id: "a2", type: "ai", content: "回复二" },
    ];
    render(<DocAIAgentPanel {...baseProps(makeEditorRef(), "t3")} />);

    // 只有最后一条回复挂操作条 → 全局仅一个「重新生成」入口
    const retryBtns = await screen.findAllByTitle("重新生成");
    expect(retryBtns.length).toBe(1);

    fireEvent.click(retryBtns[0]!);
    await waitFor(() => expect(m.submit).toHaveBeenCalled());
    const arg = m.submit.mock.calls[0]?.[0] as {
      messages: Array<{ content: string }>;
    };
    expect(String(arg.messages[0]?.content)).toContain("最后指令");
  });

  it("流式中发送键变停止：点击调用 stream.stop", () => {
    seedUserMessages("t4", ["问题"]);
    m.streamState.isLoading = true;
    render(<DocAIAgentPanel {...baseProps(makeEditorRef(), "t4")} />);

    const stopBtn = screen.getByTitle("停止");
    fireEvent.click(stopBtn);
    expect(m.stop).toHaveBeenCalled();
  });
});
