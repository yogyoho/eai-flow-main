// frontend/tests/unit/docmgr/task-hook.dom.test.tsx（.dom 后缀 → rstest 自动启用 happy-dom）
// EAI-CUSTOM (全文操作 M3顺手批, S-3): useDocAITask 卸载 abort——流运行中卸载组件须
// abort 在途请求（后端不再白烧 tokens）；与 useDocAIReview 的同名清理成对落地。
// mock 手法沿 review-area.dom.test.tsx 负面④（read 挂起、signal abort 时以真
// AbortError 拒绝）。
import { afterEach, describe, expect, rs, test } from "@rstest/core";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { RefObject } from "react";

import { useDocAITask } from "@/extensions/docmgr/DocAITaskArea";
import type { PersonalBlockNoteEditorRef } from "@/extensions/docmgr/PersonalBlockNoteEditor";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

function fakeOk(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
  } as unknown as Response;
}

// fetch mock 的 URL 提取——Request 对象不能 String()（no-base-to-string）。
const urlOf = (input: RequestInfo | URL): string =>
  typeof input === "string"
    ? input
    : input instanceof URL
      ? input.href
      : input.url;

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

describe("useDocAITask（S-3 卸载 abort）", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  test("unmount → 在途 transform 流 abort（mock 收到 abort；AbortError 不派 fail）", async () => {
    let abortSeen = false;
    globalThis.fetch = (async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = urlOf(input);
      if (url.includes("/ai/transform")) {
        const signal = init?.signal;
        return {
          ok: true,
          body: {
            getReader: () => ({
              read: () =>
                new Promise((_res, rej) => {
                  signal?.addEventListener("abort", () => {
                    abortSeen = true;
                    const e = new Error("The user aborted a request.");
                    e.name = "AbortError";
                    rej(e);
                  });
                }),
              cancel: () => undefined,
            }),
          },
        } as unknown as Response;
      }
      return fakeOk();
    }) as typeof fetch;
    const ed = makeEditor();
    const { result, unmount } = renderHook(() =>
      useDocAITask({
        editorRef: makeEditorRef(ed),
        threadId: "t1",
        docRelPath: "docs/a.md",
        modelName: null,
      }),
    );
    let running: Promise<void> | undefined;
    await act(async () => {
      running = result.current.startTask("polish");
    });
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 25));
    });
    // 流挂起在途：busy 为真、mock 尚未收到 abort
    expect(result.current.busy).toBe(true);
    expect(abortSeen).toBe(false);
    await act(async () => {
      unmount();
      await running;
    });
    expect(abortSeen).toBe(true);
  });
});
