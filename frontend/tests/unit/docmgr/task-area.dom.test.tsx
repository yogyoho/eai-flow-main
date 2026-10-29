// frontend/tests/unit/docmgr/task-area.dom.test.tsx（.dom 后缀 → rstest 自动启用 happy-dom）
import { describe, expect, test } from "@rstest/core";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import { PresetChips, SectionCard } from "@/extensions/docmgr/DocAITaskArea";

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

describe("PresetChips", () => {
  test("渲染 6 个预设并可点击", async () => {
    const picked: string[] = [];
    const host = await render(
      <PresetChips disabled={false} onPick={(op) => picked.push(op)} />,
    );
    const buttons = Array.from(host.querySelectorAll("button"));
    expect(buttons.map((b) => b.textContent)).toEqual([
      "全文润色",
      "全文校对",
      "术语统一",
      "格式规范",
      "生成目录",
      "全文摘要",
    ]);
    buttons[0]!.click();
    await Promise.resolve();
    expect(picked).toEqual(["polish"]);
  });

  test("disabled 时点击无效", async () => {
    const picked: string[] = [];
    const host = await render(
      <PresetChips disabled onPick={(op) => picked.push(op)} />,
    );
    const btn = host.querySelector<HTMLButtonElement>("button")!;
    expect(btn.disabled).toBe(true);
  });
});

describe("SectionCard", () => {
  const base = {
    index: 0,
    title: "第一节",
  };

  test("streaming → 生成中", async () => {
    const host = await render(
      <SectionCard
        section={{ ...base, status: "streaming" }}
        onApply={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(host.textContent).toContain("生成中");
  });

  test("skipped → 明示跳过原因", async () => {
    const host = await render(
      <SectionCard
        section={{ ...base, status: "skipped" }}
        onApply={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(host.textContent).toContain("已跳过");
  });

  test("unchanged → 无变更", async () => {
    const host = await render(
      <SectionCard
        section={{ ...base, status: "unchanged" }}
        onApply={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(host.textContent).toContain("无变更");
  });

  test("ready → 预览+应用+跳过", async () => {
    const applied: number[] = [];
    const host = await render(
      <SectionCard
        section={{
          ...base,
          status: "ready",
          ops: [{ op: "replace_section", anchor: "第一节", content: "新内容" }],
        }}
        onApply={(i) => applied.push(i)}
        onRetry={() => undefined}
      />,
    );
    const buttons = Array.from(host.querySelectorAll("button"));
    const applyBtn = buttons.find((b) => b.textContent === "应用")!;
    applyBtn.click();
    await Promise.resolve();
    expect(applied).toEqual([0]);
  });

  test("failed → 错误信息+重试本节", async () => {
    const retried: number[] = [];
    const host = await render(
      <SectionCard
        section={{ ...base, status: "failed", error: "超时" }}
        onApply={() => undefined}
        onRetry={(i) => retried.push(i)}
      />,
    );
    expect(host.textContent).toContain("超时");
    const retry = Array.from(host.querySelectorAll("button")).find(
      (b) => b.textContent === "重试本节",
    )!;
    retry.click();
    await Promise.resolve();
    expect(retried).toEqual([0]);
  });

  test("applied → 已应用标记", async () => {
    const host = await render(
      <SectionCard
        section={{ ...base, status: "applied" }}
        onApply={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(host.textContent).toContain("已应用");
  });
});
