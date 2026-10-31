import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// UX 重构 Plan 2 T1(spec §3.2 选中任务模型):effectiveTaskId =
// URL ?task_id → 最新任务(useBidTasks[0])→ null。
// isFallback=true 表示走了最新任务 fallback(非用户显式选择);task 为 undefined
// 的两种情形:param 深链不在列表缓存 / 任务列表未加载——调用方按「无详情」处理。
const mocks = rs.hoisted(() => ({
  search: new URLSearchParams(),
  tasks: [] as unknown[],
}));

// hooks.ts → ./api → @/core/api/fetcher(同 tasks-view 测试的既有 mock 惯例),
// mock fetcher 后 useBidTasks 真实跑 TanStack Query,listTasks 数据由 responder 供给。
let responder: (path: string) => Response;
rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string) => {
    return responder(path);
  },
}));

rs.mock("next/navigation", () => ({
  useSearchParams: () => mocks.search,
}));

import { useSelectedTask } from "@/extensions/bid-review/hooks";

function task(partial: Record<string, unknown>) {
  return {
    id: "t0",
    owner_id: "o",
    status: "created",
    mode: "deep",
    progress: {},
    error: null,
    engine_meta: {},
    prev_task_id: null,
    created_at: "2026-10-31T00:00:00Z",
    fatal_unhandled: null,
    need_human_count: null,
    ...partial,
  };
}

function renderSel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderHook(() => useSelectedTask(), {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  });
}

/** happy-dom 下等 TanStack Query 落定的最简轮询。 */
async function settle(result: { current: { task?: unknown } }, hit = true) {
  for (let i = 0; i < 20; i++) {
    if (!hit || result.current.task !== undefined) return;
    await new Promise((r) => setTimeout(r, 10));
  }
}

describe("useSelectedTask fallback 链(spec §3.2)", () => {
  beforeEach(() => {
    mocks.search = new URLSearchParams();
    responder = () =>
      new Response(JSON.stringify({ items: mocks.tasks }), {
        headers: { "Content-Type": "application/json" },
      });
  });
  afterEach(cleanup);

  it("URL param 优先,task 对象从列表缓存取,isFallback=false", async () => {
    mocks.search = new URLSearchParams("task_id=t2");
    mocks.tasks = [task({ id: "t1" }), task({ id: "t2", status: "done" })];
    const { result } = renderSel();
    await settle(result);
    expect(result.current.taskId).toBe("t2");
    expect(result.current.task?.id).toBe("t2");
    expect(result.current.isFallback).toBe(false);
  });

  it("无 param 回退最新任务(列表首位),isFallback=true", async () => {
    mocks.tasks = [task({ id: "newest", status: "running" })];
    const { result } = renderSel();
    await settle(result);
    expect(result.current.taskId).toBe("newest");
    expect(result.current.isFallback).toBe(true);
  });

  it("空任务列表:taskId=null、task=undefined(页面据此渲染空态)", async () => {
    const { result } = renderSel();
    await settle(result, false);
    expect(result.current.taskId).toBeNull();
    expect(result.current.task).toBeUndefined();
  });

  it("param 指向不在列表的任务(深链):taskId 保留,task=undefined", async () => {
    mocks.search = new URLSearchParams("task_id=ghost");
    mocks.tasks = [task({ id: "t1" })];
    const { result } = renderSel();
    await settle(result, false);
    expect(result.current.taskId).toBe("ghost");
    expect(result.current.task).toBeUndefined();
  });
});
