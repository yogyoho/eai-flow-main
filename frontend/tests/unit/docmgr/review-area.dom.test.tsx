// frontend/tests/unit/docmgr/review-area.dom.test.tsx（.dom 后缀 → rstest 自动启用 happy-dom）
// EAI-CUSTOM (全文操作 M2 Chunk 2): DocAIReviewArea 审查任务区 —— FindingsCard 分组 /
// 定位 / 修复 / 忽略 / 整批修复撤销 + useDocAIReview 全链路（NDJSON 流 → 修复 → 撤销）。
import { afterEach, describe, expect, rs, test } from "@rstest/core";
import { act, cleanup, renderHook } from "@testing-library/react";
import React, { useReducer } from "react";
import type { RefObject } from "react";
import { createRoot } from "react-dom/client";

import { type DocAIFinding } from "@/extensions/api";
import {
  DocAIReviewArea,
  type DocAIReviewAction,
  type DocAIReviewState,
  initialReviewState,
  reviewReducer,
  useDocAIReview,
} from "@/extensions/docmgr/DocAIReviewArea";
import type {
  DocOperation,
  PersonalBlockNoteEditorRef,
} from "@/extensions/docmgr/PersonalBlockNoteEditor";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

async function render(ui: React.ReactElement): Promise<HTMLElement> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(ui);
  });
  return host;
}

async function click(el: HTMLElement): Promise<void> {
  await act(async () => {
    el.click();
  });
}

const buttonByText = (host: HTMLElement, text: string): HTMLButtonElement =>
  Array.from(host.querySelectorAll("button")).find(
    (b) => b.textContent === text,
  )!;

const buttonsByText = (host: HTMLElement, text: string): HTMLButtonElement[] =>
  Array.from(host.querySelectorAll("button")).filter(
    (b) => b.textContent === text,
  );

// ── fixture ──────────────────────────────────────────────────────────

const errFinding: DocAIFinding = {
  id: "e1",
  severity: "error",
  anchor: "概述",
  excerpt: "蒸发损失系数取 0.0012",
  problem: "数值与下文计算不一致",
  suggestion: "复核后统一为 0.001461",
  fix_op: { op: "replace_section", anchor: "概述", content: "修正后全节" },
};

const warnFinding: DocAIFinding = {
  id: "w1",
  severity: "warn",
  anchor: "设计参数",
  excerpt: "循环水场",
  problem: "同词异形：循环水场/循环水场区",
  suggestion: "统一为「循环水场」",
};

const infoFinding: DocAIFinding = {
  id: "i1",
  severity: "info",
  anchor: "水力计算",
  excerpt: "表 3.3.3",
  problem: "编号格式不统一",
  suggestion: "改为「表 3-3」",
};

const doneState = (): DocAIReviewState => ({
  ...initialReviewState("consistency"),
  running: false,
  total: 3,
  audited: [0, 1, 2],
  entries: [
    { finding: errFinding, sectionIndex: 0, fixed: false },
    { finding: warnFinding, sectionIndex: 1, fixed: false },
    { finding: infoFinding, sectionIndex: 2, fixed: false },
  ],
  failed: [],
  skipped: [],
  dismissedIds: [],
  summary: { error: 1, warn: 1, info: 1 },
});

// ── Harness：reducer 驱动的壳（同 task-area.dom.test 手法） ────────────

const harnessReducer = (
  s: DocAIReviewState,
  a: DocAIReviewAction,
): DocAIReviewState => reviewReducer(s, a) ?? s;

function Harness({
  initial,
  busy = false,
  undoBlocked = false,
  hasSnapshot = false,
  locate,
  spies,
}: {
  initial: DocAIReviewState;
  busy?: boolean;
  undoBlocked?: boolean;
  hasSnapshot?: boolean;
  locate?: (anchor: string) => boolean;
  spies?: {
    onCancel?: () => void;
    onApplyAllFixes?: () => void;
    onUndoAllFixes?: () => void;
  };
}) {
  const [st, dispatch] = useReducer(harnessReducer, initial);
  return (
    <DocAIReviewArea
      state={st}
      busy={busy}
      undoBlocked={undoBlocked}
      hasSnapshot={hasSnapshot}
      onLocate={locate ?? (() => true)}
      onApplyFix={(f) => dispatch({ type: "fix_applied", id: f.id })}
      onApplyAllFixes={() => {
        spies?.onApplyAllFixes?.();
        for (const e of st.entries) {
          if (
            e.fixed ||
            !e.finding.fix_op ||
            st.dismissedIds.includes(e.finding.id)
          )
            continue;
          dispatch({ type: "fix_applied", id: e.finding.id });
        }
      }}
      onUndoAllFixes={() => {
        spies?.onUndoAllFixes?.();
        dispatch({ type: "fixes_reverted" });
      }}
      onDismissFinding={(id) => dispatch({ type: "dismiss", id })}
      onRestoreFinding={(id) => dispatch({ type: "restore", id })}
      onCancel={() => spies?.onCancel?.()}
      onReset={() => undefined}
    />
  );
}

describe("DocAIReviewArea（审查任务区组件）", () => {
  test("severity 分组渲染 + 组头计数 pill（error 红/warn 琥珀/info 灰）", async () => {
    const host = await render(<Harness initial={doneState()} />);
    const errGroup = host.querySelector('[data-severity="error"]');
    const warnGroup = host.querySelector('[data-severity="warn"]');
    const infoGroup = host.querySelector('[data-severity="info"]');
    expect(errGroup).not.toBeNull();
    expect(warnGroup).not.toBeNull();
    expect(infoGroup).not.toBeNull();
    expect(errGroup!.textContent).toContain("错误");
    expect(errGroup!.textContent).toContain("1");
    expect(warnGroup!.textContent).toContain("警告");
    expect(warnGroup!.textContent).toContain("1");
    expect(infoGroup!.textContent).toContain("提示");
    // 条目内容：excerpt（等宽）+ problem + suggestion
    expect(host.textContent).toContain("蒸发损失系数取 0.0012");
    expect(host.textContent).toContain("数值与下文计算不一致");
    expect(host.textContent).toContain("复核后统一为 0.001461");
  });

  test("定位：onLocate 收到 anchor；返回 false → 按钮转禁用态", async () => {
    const located: string[] = [];
    const host = await render(
      <Harness
        initial={doneState()}
        locate={(a) => {
          located.push(a);
          return false;
        }}
      />,
    );
    await click(buttonByText(host, "定位"));
    expect(located).toEqual(["概述"]);
    expect(buttonByText(host, "定位").disabled).toBe(true);
  });

  test("修复：仅 fix_op 存在才出现；点击 → onApplyFix → 翻「已修复」", async () => {
    const host = await render(<Harness initial={doneState()} />);
    expect(buttonsByText(host, "修复").length).toBe(1);
    await click(buttonByText(host, "修复"));
    expect(host.textContent).toContain("已修复");
    expect(buttonsByText(host, "修复").length).toBe(0);
  });

  test("忽略：条目移出展示列表；恢复忽略（n）入口一键还原", async () => {
    const host = await render(<Harness initial={doneState()} />);
    await click(buttonByText(host, "忽略"));
    expect(host.querySelector('[data-severity="error"]')).toBeNull();
    expect(host.textContent).toContain("恢复忽略（1）");
    await click(buttonByText(host, "恢复忽略（1）"));
    expect(host.querySelector('[data-severity="error"]')).not.toBeNull();
    expect(host.textContent).not.toContain("恢复忽略（1）");
  });

  test("全部修复（n）：n=带 fix_op 未修复未忽略条数；0 时禁用；撤销整批随快照出现", async () => {
    const host = await render(
      <Harness initial={doneState()} hasSnapshot={true} />,
    );
    const bar = () =>
      Array.from(host.querySelectorAll("button")).find((b) =>
        b.textContent?.startsWith("全部修复"),
      )!;
    expect(bar().textContent).toBe("全部修复（1）");
    expect(bar().disabled).toBe(false);
    expect(buttonByText(host, "撤销整批")).toBeTruthy();
    // 忽略唯一可修复条 → 计数归零禁用（忽略钮在组内第一条卡上）
    await click(buttonsByText(host, "忽略")[0]!);
    expect(bar().textContent).toBe("全部修复（0）");
    expect(bar().disabled).toBe(true);
  });

  test("无快照（未整批修复过）不显示撤销整批", async () => {
    const host = await render(<Harness initial={doneState()} />);
    expect(buttonByText(host, "撤销整批")).toBeUndefined();
  });

  test("undoBlocked → 脏检查提示（batch bar 既有模式文案）", async () => {
    const host = await render(
      <Harness initial={doneState()} hasSnapshot={true} undoBlocked={true} />,
    );
    expect(host.textContent).toContain("整批撤销已禁用");
  });

  test("running：执行中 pill + 三行计划（已审/正在审/待查看 findings）+ 停止钮", async () => {
    const cancelled: boolean[] = [];
    const runningState: DocAIReviewState = {
      ...initialReviewState("consistency"),
      running: true,
      total: 4,
      audited: [0, 1],
      current: { index: 1, title: "设计参数" },
      entries: [{ finding: warnFinding, sectionIndex: 0, fixed: false }],
      failed: [],
      skipped: [],
      dismissedIds: [],
    };
    const host = await render(
      <Harness
        initial={runningState}
        busy={true}
        spies={{ onCancel: () => cancelled.push(true) }}
      />,
    );
    expect(host.textContent).toContain("执行中");
    expect(host.textContent).not.toContain("已完成");
    expect(host.textContent).toContain("已审 2 节");
    expect(host.textContent).toContain("正在审 §2 设计参数");
    expect(host.textContent).toContain("待查看 findings 1 条");
    await click(host.querySelector('button[aria-label="停止审查"]')!);
    expect(cancelled).toEqual([true]);
  });

  test("任务名=审查类型中文；failed 节计数提示", async () => {
    const st: DocAIReviewState = {
      ...doneState(),
      failed: [2],
    };
    const host = await render(<Harness initial={st} />);
    expect(host.textContent).toContain("术语一致性审查");
    expect(host.textContent).toContain("1 节审查失败");
  });

  test("空表短路：已完成 pill + message 展示 + 零 findings 不炸", async () => {
    const st: DocAIReviewState = {
      ...initialReviewState("numbering"),
      running: false,
      total: 2,
      audited: [0, 1],
      failed: [],
      skipped: [],
      dismissedIds: [],
      summary: { error: 0, warn: 0, info: 0 },
      message: "未提取到编号清单",
    };
    const host = await render(<Harness initial={st} />);
    expect(host.textContent).toContain("已完成");
    expect(host.textContent).toContain("未提取到编号清单");
    expect(host.textContent).toContain("编号连续性审查");
  });
});

// ── useDocAIReview 全链路（fetch 假响应：PUT 同步 / 版本 / NDJSON 流） ──

function fakeOk(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
  } as unknown as Response;
}

function fakeNdjson(lines: unknown[]): Response {
  const encoder = new TextEncoder();
  const payload = encoder.encode(
    lines.map((l) => JSON.stringify(l) + "\n").join(""),
  );
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(payload);
      controller.close();
    },
  });
  return {
    ok: true,
    status: 200,
    body,
    text: async () => "",
  } as unknown as Response;
}

const REVIEW_STREAM: unknown[] = [
  { type: "section_start", index: 0, total: 2, title: "概述" },
  {
    type: "finding",
    index: 0,
    finding: errFinding,
  },
  {
    type: "finding",
    index: 0,
    finding: warnFinding,
  },
  { type: "section_start", index: 1, total: 2, title: "水力计算" },
  { type: "section_error", index: 1, message: "本节审查失败，可稍后重试" },
  {
    type: "done",
    total: 2,
    failed: [1],
    skipped: [],
    summary: { error: 1, warn: 1, info: 0 },
  },
];

function makeEditor() {
  return {
    getMarkdown: () => Promise.resolve("# 文档\n\n## 概述\n\n内容。"),
    applyOperations: rs.fn(),
    snapshotBlocks: rs.fn(() => [{ id: "b1", type: "heading" }]),
    restoreBlocks: rs.fn(),
    onDocumentChange: rs.fn(() => rs.fn()),
  };
}

function makeEditorRef(ed: ReturnType<typeof makeEditor>) {
  return {
    current: ed,
  } as unknown as RefObject<PersonalBlockNoteEditorRef | null>;
}

const useReview = (ref: RefObject<PersonalBlockNoteEditorRef | null>) =>
  useDocAIReview({
    editorRef: ref,
    threadId: "t1",
    docRelPath: "docs/a.md",
    modelName: null,
  });

// fetch mock 的 URL 提取——Request 对象不能 String()（no-base-to-string）。
const urlOf = (input: RequestInfo | URL): string =>
  typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input.url;

describe("useDocAIReview（审查任务通道）", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  test("startReview 全链路：NDJSON 事件入状态；PUT 同步与版本快照先行", async () => {
    const calls: string[] = [];
    globalThis.fetch = (async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = urlOf(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.includes("/ai/review")) return fakeNdjson(REVIEW_STREAM);
      return fakeOk();
    }) as typeof fetch;
    const ed = makeEditor();
    const { result } = renderHook(() => useReview(makeEditorRef(ed)));

    await act(async () => {
      await result.current.startReview("consistency");
    });

    // PUT 文档同步 → 版本快照 → /ai/review
    expect(
      calls.some((c) => c.startsWith("PUT") && c.includes("/content")),
    ).toBe(true);
    expect(
      calls.some((c) => c.startsWith("POST") && c.includes("/versions")),
    ).toBe(true);
    expect(calls.some((c) => c.includes("/ai/review"))).toBe(true);

    const st = result.current.state!;
    expect(st.running).toBe(false);
    expect(st.reviewType).toBe("consistency");
    expect(st.entries.map((e) => e.finding.id)).toEqual(["e1", "w1"]);
    expect(st.failed).toEqual([1]);
    expect(st.audited).toEqual([0, 1]);
    expect(st.total).toBe(2);
    expect(st.summary).toEqual({ error: 1, warn: 1, info: 0 });
    expect(result.current.busy).toBe(false);

    // 单条修复走 applyOperations（fix_op 原样回灌）
    await act(async () => {
      result.current.applyFix(errFinding);
    });
    expect(ed.applyOperations).toHaveBeenCalledTimes(1);
    const appliedOp = ed.applyOperations.mock.calls[0]?.[0] as DocOperation[];
    expect(appliedOp[0]).toEqual(errFinding.fix_op);
    expect(
      result.current.state!.entries.find((e) => e.finding.id === "e1")!.fixed,
    ).toBe(true);
  });

  test("全部修复：先 snapshotBlocks 再顺序 apply；撤销整批 restoreBlocks + 状态回退", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/ai/review")) return fakeNdjson(REVIEW_STREAM);
      return fakeOk();
    }) as typeof fetch;
    const ed = makeEditor();
    const { result } = renderHook(() => useReview(makeEditorRef(ed)));
    await act(async () => {
      await result.current.startReview("consistency");
    });

    await act(async () => {
      result.current.applyAllFixes();
    });
    // 快照先于修复（整批撤销的回滚点）；仅带 fix_op 的条目被 apply
    expect(ed.snapshotBlocks).toHaveBeenCalledTimes(1);
    expect(ed.applyOperations).toHaveBeenCalledTimes(1);
    expect(result.current.hasSnapshot).toBe(true);
    expect(
      result.current.state!.entries.find((e) => e.finding.id === "e1")!.fixed,
    ).toBe(true);

    await act(async () => {
      result.current.undoAllFixes();
    });
    expect(ed.restoreBlocks).toHaveBeenCalledTimes(1);
    expect(result.current.hasSnapshot).toBe(false);
    expect(result.current.state!.entries.every((e) => !e.fixed)).toBe(true);
  });

  test("脏检查：整批修复后用户手改 → 撤销整批被禁（undoBlocked）", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/ai/review")) return fakeNdjson(REVIEW_STREAM);
      return fakeOk();
    }) as typeof fetch;
    const ed = makeEditor();
    const { result } = renderHook(() => useReview(makeEditorRef(ed)));
    await act(async () => {
      await result.current.startReview("consistency");
    });
    await act(async () => {
      result.current.applyAllFixes();
    });
    // 模拟整批修复后用户手改（面板 onDocumentChange → markUserEdited）
    await act(async () => {
      result.current.markUserEdited();
    });
    await act(async () => {
      result.current.undoAllFixes();
    });
    expect(ed.restoreBlocks).not.toHaveBeenCalled();
    expect(result.current.undoBlocked).toBe(true);
    // 已修复状态保持（未回滚）
    expect(
      result.current.state!.entries.find((e) => e.finding.id === "e1")!.fixed,
    ).toBe(true);
  });

  test("忽略/恢复 + reset：dismiss 后不计入全部修复；reset 卸载任务区", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/ai/review")) return fakeNdjson(REVIEW_STREAM);
      return fakeOk();
    }) as typeof fetch;
    const ed = makeEditor();
    const { result } = renderHook(() => useReview(makeEditorRef(ed)));
    await act(async () => {
      await result.current.startReview("consistency");
    });

    await act(async () => {
      result.current.dismissFinding("e1");
    });
    expect(result.current.state!.dismissedIds).toEqual(["e1"]);
    await act(async () => {
      result.current.restoreFinding("e1");
    });
    expect(result.current.state!.dismissedIds).toEqual([]);

    await act(async () => {
      result.current.reset();
    });
    expect(result.current.state).toBeNull();
  });
});
