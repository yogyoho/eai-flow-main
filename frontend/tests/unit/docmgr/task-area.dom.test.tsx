// frontend/tests/unit/docmgr/task-area.dom.test.tsx（.dom 后缀 → rstest 自动启用 happy-dom）
// EAI-CUSTOM (全文操作 v2): SectionCard → DiffCard（工单 diff 卡）+ DocAITaskArea 工单化联动。
import { describe, expect, test } from "@rstest/core";
import React, { act, useReducer } from "react";
import { createRoot } from "react-dom/client";

import {
  DiffCard,
  DocAITaskArea,
  type DocAITaskAction,
  type DocAITaskState,
  type TaskSection,
  initialTaskState,
  taskReducer,
} from "@/extensions/docmgr/DocAITaskArea";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

// React 19 createRoot().render() 是异步提交 —— 用 act 包裹保证 DOM 同步 flush。
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

// EAI-CUSTOM (面板 v2 复审#3): PresetChips 组件已删（空态宫格取代），其 2 个 dom 测试随之移除。

// ── DiffCard（逐节 diff 卡） ─────────────────────────────────────────

const readySection: TaskSection = {
  index: 0,
  title: "第一节",
  status: "ready",
  ops: [{ op: "replace_section", anchor: "第一节", content: "新内容" }],
};

describe("DiffCard", () => {
  test("ready + oldText → 行级 diff 渲染（del/ins 色档 + 前缀）", async () => {
    const host = await render(
      <DiffCard
        section={readySection}
        oldText="旧内容"
        onApply={() => undefined}
        onReject={() => undefined}
        onRetry={() => undefined}
      />,
    );
    // ready 默认展开
    expect(host.querySelector('button[aria-expanded="true"]')).not.toBeNull();
    expect(host.innerHTML).toContain("bg-destructive/10");
    expect(host.innerHTML).toContain("bg-emerald-500/10");
    expect(host.textContent).toContain("+新内容");
    expect(host.textContent).toContain("旧内容");
    expect(host.querySelector(".line-through")).not.toBeNull();
  });

  test("streaming 挂载→ready 迁移自动展开；手动收起不被覆盖（复审#1）", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const streaming: TaskSection = {
      index: 0,
      title: "第一节",
      status: "streaming",
    };
    const ready: TaskSection = {
      ...streaming,
      status: "ready",
      ops: [{ op: "replace_section", anchor: "第一节", content: "新内容" }],
    };
    const props = {
      onApply: () => undefined,
      onReject: () => undefined,
      onRetry: () => undefined,
    };
    // 生产路径：卡片以 streaming 挂载（key=index 不重挂）
    let root: ReturnType<typeof createRoot> | null = null;
    await act(async () => {
      root = createRoot(host);
      root.render(<DiffCard section={streaming} {...props} />);
    });
    expect(host.querySelector('button[aria-expanded="false"]')).not.toBeNull();
    // streaming→ready 迁移 → 自动展开
    await act(async () => {
      root!.render(<DiffCard section={ready} oldText="旧内容" {...props} />);
    });
    expect(host.querySelector('button[aria-expanded="true"]')).not.toBeNull();
    expect(host.querySelector(".line-through")).not.toBeNull();
    // 用户手动收起后，ready 重渲染不重新展开
    await click(
      host.querySelector<HTMLButtonElement>('button[aria-expanded="true"]')!,
    );
    expect(host.querySelector('button[aria-expanded="false"]')).not.toBeNull();
    await act(async () => {
      root!.render(<DiffCard section={ready} oldText="旧内容" {...props} />);
    });
    expect(host.querySelector('button[aria-expanded="false"]')).not.toBeNull();
  });

  test("oldText 缺省 → 退化为新内容预览（无 diff 色档）", async () => {
    const host = await render(
      <DiffCard
        section={readySection}
        onApply={() => undefined}
        onReject={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(host.textContent).toContain("新内容");
    expect(host.querySelector(".line-through")).toBeNull();
  });

  test("点头部开合：ready 默认展开 → 收起 → 再展开", async () => {
    const host = await render(
      <DiffCard
        section={readySection}
        oldText="旧内容"
        onApply={() => undefined}
        onReject={() => undefined}
        onRetry={() => undefined}
      />,
    );
    const header = host.querySelector<HTMLButtonElement>(
      'button[aria-expanded="true"]',
    )!;
    await click(header);
    expect(host.querySelector('button[aria-expanded="false"]')).not.toBeNull();
    expect(host.querySelector(".line-through")).toBeNull();
    await click(
      host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!,
    );
    expect(host.querySelector(".line-through")).not.toBeNull();
  });

  test("点击 接受 → onApply(index)；点击 拒绝 → onReject(index)", async () => {
    const applied: number[] = [];
    const rejected: number[] = [];
    const host = await render(
      <DiffCard
        section={readySection}
        onApply={(i) => applied.push(i)}
        onReject={(i) => rejected.push(i)}
        onRetry={() => undefined}
      />,
    );
    await click(buttonByText(host, "接受"));
    await click(buttonByText(host, "拒绝"));
    expect(applied).toEqual([0]);
    expect(rejected).toEqual([0]);
  });

  test("rejected → 已拒绝 pill + 恢复建议 → onRestore；不展示 diff", async () => {
    const restored: number[] = [];
    const host = await render(
      <DiffCard
        section={{ ...readySection, status: "rejected" }}
        oldText="旧内容"
        onApply={() => undefined}
        onReject={() => undefined}
        onRetry={() => undefined}
        onRestore={(i) => restored.push(i)}
      />,
    );
    expect(host.textContent).toContain("已拒绝");
    // rejected 默认收起：恢复建议在展开体内
    const header = host.querySelector<HTMLButtonElement>("button")!;
    await click(header);
    expect(host.querySelector(".line-through")).toBeNull();
    await click(buttonByText(host, "恢复建议"));
    expect(restored).toEqual([0]);
  });

  test("failed → 错误信息 + 重试本节", async () => {
    const retried: number[] = [];
    const host = await render(
      <DiffCard
        section={{ ...readySection, status: "failed", error: "超时" }}
        onApply={() => undefined}
        onReject={() => undefined}
        onRetry={(i) => retried.push(i)}
      />,
    );
    await click(host.querySelector<HTMLButtonElement>("button")!); // 展开
    expect(host.textContent).toContain("超时");
    await click(buttonByText(host, "重试本节"));
    expect(retried).toEqual([0]);
  });

  test("applied → 已接受 pill；skipped/unchanged → 灰档 pill", async () => {
    for (const [status, label] of [
      ["applied", "已接受"],
      ["skipped", "已跳过"],
      ["unchanged", "无变更"],
    ] as const) {
      const host = await render(
        <DiffCard
          section={{ ...readySection, status, ops: undefined }}
          onApply={() => undefined}
          onReject={() => undefined}
          onRetry={() => undefined}
        />,
      );
      expect(host.textContent).toContain(label);
    }
  });
});

// ── DocAITaskArea（工单容器） ─────────────────────────────────────────

/** reducer 驱动的壳：点击 拒绝/接受 走真实 taskReducer 流转。 */
// taskReducer 形参收 null（dismiss 路径）→ useReducer 会把 State 推宽为 | null；
// harness 恒非空，包一层收窄。
const harnessReducer = (
  s: DocAITaskState,
  a: DocAITaskAction,
): DocAITaskState => taskReducer(s, a) ?? s;

function Harness({
  initial,
  busy = false,
  spies,
  getSectionText,
}: {
  initial: DocAITaskState;
  busy?: boolean;
  spies?: {
    onApplySection?: (i: number) => void;
    onRejectSection?: (i: number) => void;
    onRestoreSection?: (i: number) => void;
    onCancel?: () => void;
  };
  getSectionText?: (anchor: string) => string;
}) {
  const [task, dispatch] = useReducer(harnessReducer, initial);
  return (
    <DocAITaskArea
      task={task}
      busy={busy}
      undoBlocked={false}
      onApplySection={(i) => {
        spies?.onApplySection?.(i);
        dispatch({ type: "apply_section", index: i });
      }}
      onApplyAll={() => {
        for (const s of task.sections) {
          if (s.status === "ready")
            dispatch({ type: "apply_section", index: s.index });
        }
      }}
      onUndoAll={() => dispatch({ type: "reverted" })}
      onRetrySection={() => undefined}
      onRejectSection={(i) => {
        spies?.onRejectSection?.(i);
        dispatch({ type: "reject_section", index: i });
      }}
      onRestoreSection={(i) => {
        spies?.onRestoreSection?.(i);
        dispatch({ type: "restore_section", index: i });
      }}
      onInsertSummary={() => undefined}
      onCancel={() => {
        spies?.onCancel?.();
      }}
      onDismiss={() => undefined}
      getSectionText={getSectionText}
    />
  );
}

const twoSectionState = (): DocAITaskState => ({
  ...initialTaskState("polish"),
  running: false,
  total: 2,
  sections: [readySection, { index: 1, title: "第二节", status: "applied" }],
});

describe("DocAITaskArea（工单）", () => {
  test("ready 节 + getSectionText → diff 渲染；批量条计数正确", async () => {
    const host = await render(
      <Harness
        initial={twoSectionState()}
        getSectionText={(anchor) =>
          anchor === "第一节" ? "旧内容" : "旧内容2"
        }
      />,
    );
    expect(host.innerHTML).toContain("bg-destructive/10");
    expect(host.innerHTML).toContain("bg-emerald-500/10");
    expect(host.textContent).toContain("接受全部（1）");
    expect(host.textContent).toContain("每次批量应用前自动建版本快照");
    // 计划行：终态 1 + 待确认 1
    expect(host.textContent).toContain("已完成处理 1 节");
    expect(host.textContent).toContain("待确认 1 节");
    expect(host.textContent).toContain("已完成");
  });

  test("拒绝 → pill 已拒绝 + 恢复建议；恢复 → 回待确认可再接受", async () => {
    const rejected: number[] = [];
    const restored: number[] = [];
    const host = await render(
      <Harness
        initial={twoSectionState()}
        spies={{
          onRejectSection: (i) => rejected.push(i),
          onRestoreSection: (i) => restored.push(i),
        }}
      />,
    );
    await click(buttonByText(host, "拒绝"));
    expect(rejected).toEqual([0]);
    expect(host.textContent).toContain("已拒绝");
    // 卡挂载于 ready（默认展开）→ 拒绝后恢复建议直接可见
    await click(buttonByText(host, "恢复建议"));
    expect(restored).toEqual([0]);
    expect(host.textContent).toContain("待确认");
    expect(buttonByText(host, "接受")).toBeTruthy();
  });

  test("接受 → onApply 调用 + 批量计数更新（接受全部归零禁用）", async () => {
    const applied: number[] = [];
    const host = await render(
      <Harness
        initial={twoSectionState()}
        spies={{ onApplySection: (i) => applied.push(i) }}
      />,
    );
    await click(buttonByText(host, "接受"));
    expect(applied).toEqual([0]);
    expect(host.textContent).toContain("接受全部（0）");
    const applyAll = Array.from(host.querySelectorAll("button")).find((b) =>
      b.textContent?.startsWith("接受全部"),
    )!;
    expect(applyAll.disabled).toBe(true);
    // 撤销整批可用（appliedCount=2）
    const undoBtn = buttonByText(host, "撤销整批");
    expect(undoBtn.disabled).toBe(false);
  });

  test("busy → 执行中 pill + 停止按钮（onCancel 接通）+ 批量条隐藏", async () => {
    const cancelled: boolean[] = [];
    const host = await render(
      <Harness
        initial={twoSectionState()}
        busy={true}
        spies={{ onCancel: () => cancelled.push(true) }}
      />,
    );
    expect(host.textContent).toContain("执行中");
    expect(host.textContent).not.toContain("接受全部");
    await click(host.querySelector('button[aria-label="停止任务"]')!);
    expect(cancelled).toEqual([true]);
  });

  test("streaming 节 → 正在处理 计划行", async () => {
    const host = await render(
      <Harness
        initial={{
          ...initialTaskState("polish"),
          sections: [{ index: 0, title: "第二节", status: "streaming" }],
        }}
        busy={true}
      />,
    );
    expect(host.textContent).toContain("正在处理 第二节");
  });

  test("无标题节 → 第 n 节兜底", async () => {
    const host = await render(
      <Harness
        initial={{
          ...initialTaskState("polish"),
          running: false,
          sections: [{ index: 2, title: "", status: "unchanged" }],
        }}
      />,
    );
    expect(host.textContent).toContain("第 3 节");
  });
});
