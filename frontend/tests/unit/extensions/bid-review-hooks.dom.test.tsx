import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// 计划 Task 17 Step 4:hooks.ts 单测 + mutation payload 断言。
// hooks 行为(useMutation 失效广播/渲染期状态)只在真实 React 下存在——按仓库惯例
// (frontend/AGENTS.md)落 .dom.test 环境 + renderHook + QueryClientProvider 包装,
// 非 node 环境手 mock react(计划底稿写 node,落地从仓库规约,与 Task 12 的
// fetcher→fetch 勘误同性质)。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (path: string, init?: RequestInit) => Response;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

import { ApiError } from "@/extensions/bid-review/api";
import {
  useBidConfirmTask,
  useBidFeedback,
  useBidIssues,
  useBidRulepacks,
  useBidTask,
} from "@/extensions/bid-review/hooks";

const ISSUE = {
  id: "i1",
  task_id: "t1",
  rule_id: "L1-009",
  layer: "L1",
  severity: "fatal",
  verdict: "violation",
  clause_id: null,
  message: "投标总价超出招标控制价",
  fix: "下调总价至控制价以内",
  evidence: [{ doc_id: "bid.md", page: 3, text: "投标总价:¥9,000,000" }],
  dedup_key: "L1-009|-|k",
  need_human: false,
  confidence: 1.0,
  created_at: "2026-10-29T00:00:00Z",
};

const TASK = {
  id: "t1",
  owner_id: "u1",
  status: "done",
  mode: "quick",
  progress: { pct: 100 },
  error: null,
  engine_meta: {},
  prev_task_id: null,
  created_at: "2026-10-29T00:00:00Z",
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function QueryWrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("bid-review hooks", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("useBidTask fetches task detail by id", async () => {
    responder = (path) =>
      path.endsWith("/tasks/t1") ? jsonRes(TASK) : jsonRes({}, 404);
    const { result } = renderHook(() => useBidTask("t1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe("t1");
    expect(result.current.data?.status).toBe("done");
    const last = calls[calls.length - 1];
    expect(last?.path).toBe("/api/extensions/bid-review/tasks/t1");
  });

  it("useBidTask is disabled without a task id", () => {
    const { result } = renderHook(() => useBidTask(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(calls).toHaveLength(0);
  });

  it("useBidIssues fetches task issues and unwraps {items}", async () => {
    responder = () => jsonRes({ items: [ISSUE] });
    const { result } = renderHook(() => useBidIssues("t1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.rule_id).toBe("L1-009");
    const last = calls[calls.length - 1];
    expect(last?.path).toBe("/api/extensions/bid-review/tasks/t1/issues");
  });

  it("useBidFeedback posts the JSON payload to /issues/{id}/feedback", async () => {
    responder = () => jsonRes(ISSUE);
    const { result } = renderHook(() => useBidFeedback(), {
      wrapper: createWrapper(),
    });
    act(() =>
      result.current.mutate({
        issueId: "i1",
        taskId: "t1",
        action: "severity_change",
        new_severity: "major",
        note: "人工复核降级",
      }),
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const last = calls[calls.length - 1];
    expect(last?.path).toBe("/api/extensions/bid-review/issues/i1/feedback");
    expect(last?.init?.method).toBe("POST");
    const body = last?.init?.body;
    expect(typeof body).toBe("string");
    expect(JSON.parse(body as string)).toEqual({
      action: "severity_change",
      new_severity: "major",
      note: "人工复核降级",
    });
  });

  it("useBidFeedback invalidates the issues query on success", async () => {
    let issueGetCount = 0;
    responder = (path, init) => {
      const method = init?.method ?? "GET";
      if (path.endsWith("/tasks/t1/issues") && method === "GET") {
        issueGetCount += 1;
        return jsonRes({ items: [ISSUE] });
      }
      if (path.endsWith("/issues/i1/feedback")) return jsonRes(ISSUE);
      return jsonRes({}, 404);
    };
    const { result } = renderHook(
      () => ({ issues: useBidIssues("t1"), feedback: useBidFeedback() }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.issues.isSuccess).toBe(true));
    const before = issueGetCount;
    act(() =>
      result.current.feedback.mutate({
        issueId: "i1",
        taskId: "t1",
        action: "confirm",
        note: "",
      }),
    );
    await waitFor(() => expect(result.current.feedback.isSuccess).toBe(true));
    // onSuccess 失效 issues 前缀 → issues 查询 refetch(至少再拉一次)
    await waitFor(() => expect(issueGetCount).toBeGreaterThan(before));
  });

  it("useBidConfirmTask posts POST /tasks/{id}/confirm and invalidates the task query", async () => {
    let taskGetCount = 0;
    responder = (path, init) => {
      const method = init?.method ?? "GET";
      if (path.endsWith("/tasks/t9") && method === "GET") {
        taskGetCount += 1;
        return jsonRes({ ...TASK, id: "t9", status: "awaiting_confirm" });
      }
      if (path.endsWith("/tasks/t9/confirm")) {
        return jsonRes({ ...TASK, id: "t9", status: "running" });
      }
      return jsonRes({}, 404);
    };
    const { result } = renderHook(
      () => ({ task: useBidTask("t9"), confirm: useBidConfirmTask() }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.task.isSuccess).toBe(true));
    const before = taskGetCount;
    act(() => result.current.confirm.mutate("t9"));
    await waitFor(() => expect(result.current.confirm.isSuccess).toBe(true));
    const confirmCall = calls.find((c) =>
      c.path?.endsWith("/tasks/t9/confirm"),
    );
    expect(confirmCall?.init?.method).toBe("POST");
    // onSuccess 失效 task + tasks 列表 → task 详情查询 refetch
    await waitFor(() => expect(taskGetCount).toBeGreaterThan(before));
  });

  it("surfaces a 409 confirm-gate rejection as ApiError with status", async () => {
    responder = (path, init) => {
      if ((init?.method ?? "GET") === "POST") {
        return jsonRes({ detail: "存在未复核致命项" }, 409);
      }
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      return jsonRes({}, 404);
    };
    const { result } = renderHook(
      () => ({ issues: useBidIssues("t1"), feedback: useBidFeedback() }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.issues.isSuccess).toBe(true));
    act(() =>
      result.current.feedback.mutate({
        issueId: "i1",
        taskId: "t1",
        action: "confirm",
        note: "",
      }),
    );
    await waitFor(() => expect(result.current.feedback.isError).toBe(true));
    const err = result.current.feedback.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toBe("存在未复核致命项");
  });

  it("useBidRulepacks fetches /rulepacks and unwraps {items}", async () => {
    responder = () =>
      jsonRes({
        items: [
          {
            name: "bid-review-core",
            version: "1.0.0",
            rule_count: 2,
            rules: [
              {
                id: "L1-009",
                name: "总价不超限价",
                layer: "L1",
                severity: "fatal",
                type: "deterministic",
              },
              {
                id: "L3-004",
                name: "工期一致",
                layer: "L3",
                severity: "major",
                type: "hybrid",
              },
            ],
            stats: { "L1-009": { hit: 3, fp: 1, adopted: 2 } },
            enabled: true,
          },
        ],
      });
    const { result } = renderHook(() => useBidRulepacks(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const pack = result.current.data?.[0];
    expect(pack?.name).toBe("bid-review-core");
    expect(pack?.rules).toHaveLength(2);
    expect(pack?.stats["L1-009"]?.hit).toBe(3);
    const last = calls[calls.length - 1];
    expect(last?.path).toBe("/api/extensions/bid-review/rulepacks");
  });
});
