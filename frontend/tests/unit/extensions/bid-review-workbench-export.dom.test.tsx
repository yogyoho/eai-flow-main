import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

// Task 21:工作台「导出报告」按钮——点击 → GET /tasks/{id}/report?format=md →
// Blob 经 URL.createObjectURL 触发 <a download>(Blob 下载惯例,照 docmgr 导出先例;
// 后端 md 报告内容契约由 pytest test_bid_review_routers.py 锁定)。此处锁定前端接线:
// ① done 任务点击发 report 请求且 Blob 交给 createObjectURL、revokeObjectURL 回收;
// ② 非 done 任务按钮禁用且不发 report 请求(半程审查不得导出冒充完整报告)。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (
  path: string,
  init?: RequestInit,
) => Response | Promise<Response>;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({}),
  usePathname: () => "/bid-review",
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
}));

import { WorkbenchView } from "@/extensions/bid-review/components/WorkbenchView";

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

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mdRes(): Response {
  return new Response("# 投标审查报告 t1abcd12\n", {
    status: 200,
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
  });
}

function renderWorkbench() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<WorkbenchView taskId="t1" />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

const originalCreate = URL.createObjectURL.bind(URL);
const originalRevoke = URL.revokeObjectURL.bind(URL);

describe("bid-review WorkbenchView 导出报告(Task 21)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    cleanup();
  });

  it("done 任务点击导出:请求 ?format=md,Blob 交给 createObjectURL 并回收", async () => {
    responder = (path) => {
      if (path.includes("/report")) return mdRes();
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    const created: Blob[] = [];
    const revoked: string[] = [];
    (
      URL as unknown as { createObjectURL: (b: Blob) => string }
    ).createObjectURL = (b: Blob) => {
      created.push(b);
      return "blob:mock-report";
    };
    (
      URL as unknown as { revokeObjectURL: (u: string) => void }
    ).revokeObjectURL = (u: string) => {
      revoked.push(u);
    };
    renderWorkbench();
    const button = await screen.findByRole("button", { name: "导出报告" });
    // 任务详情查询未落定时按钮处于禁用态(happy-dom 抑制禁用元素点击)——先等启用再点
    await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
    fireEvent.click(button);
    await waitFor(() =>
      expect(calls.some((c) => c.path.includes("/report"))).toBe(true),
    );
    await waitFor(() => expect(created).toHaveLength(1));
    expect(created[0]).toBeInstanceOf(Blob);
    expect(await created[0]!.text()).toContain("# 投标审查报告");
    expect(revoked).toEqual(["blob:mock-report"]);
    expect(
      calls.some(
        (c) =>
          c.path === "/api/extensions/bid-review/tasks/t1/report?format=md",
      ),
    ).toBe(true);
  });

  it("非 done 任务导出按钮禁用且不发 report 请求", async () => {
    responder = (path) => {
      if (path.includes("/report")) return mdRes();
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1"))
        return jsonRes({ ...TASK, status: "running" });
      return jsonRes({}, 404);
    };
    renderWorkbench();
    const button = await screen.findByRole("button", { name: "导出报告" });
    // 等 issues 数据落定(证明查询已跑)后仍禁用——非 done 门生效,而非加载中瞬态
    await screen.findByText("投标总价超出招标控制价");
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(calls.some((c) => c.path.includes("/report"))).toBe(false);
  });
});
