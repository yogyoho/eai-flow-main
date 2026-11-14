import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// 项目列表只消费真实 GET /tasks：矩阵阻断/星级来自 engine_meta.matrix_counts，
// 缺失时不补零、不写演示指标；下一个动作统一下发到解析确认并保留 task_id。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (path: string, init?: RequestInit) => Response;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write",
  useSearchParams: () => new URLSearchParams(),
}));

import { ProjectsView } from "@/extensions/bid-write/components/ProjectsView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const READY_TASK = {
  id: "t-ready",
  biz_no: "BW-0001",
  status: "matrix_ready",
  progress: { pct: 100 },
  error: null,
  project_name: "数据中心一期",
  lot_name: "标段一",
  tender_no: "T-2026-1",
  created_at: "2026-11-13T08:00:00Z",
  engine_meta: { matrix_counts: { total: 12, star: 3, blocked: 2 } },
};

const FAILED_TASK = {
  ...READY_TASK,
  id: "t-failed",
  biz_no: "BW-0002",
  status: "failed",
  project_name: "园区网络改造",
  lot_name: null,
  tender_no: null,
  engine_meta: {},
};

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<ProjectsView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-write ProjectsView", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({ items: [READY_TASK, FAILED_TASK] });
  });

  afterEach(() => {
    cleanup();
  });

  it("渲染真实任务、矩阵计数与失败原因入口", async () => {
    renderView();

    expect(await screen.findByText("数据中心一期")).toBeTruthy();
    expect(screen.getByText("园区网络改造")).toBeTruthy();
    expect(screen.getByText("待确认 2 项")).toBeTruthy();
    expect(screen.getByText("3 / 2")).toBeTruthy();
    expect(screen.getAllByText("解析失败").length).toBeGreaterThan(0);

    const enter = screen.getByRole("link", { name: /进入解析确认/ });
    expect(enter.getAttribute("href")).toBe(
      "/bid-write/intake?task_id=t-ready",
    );
    const failed = screen.getByRole("link", { name: /查看失败原因/ });
    expect(failed.getAttribute("href")).toBe(
      "/bid-write/intake?task_id=t-failed",
    );
  });

  it("只请求任务列表，不在列表页伪造矩阵/缺口数据", async () => {
    renderView();
    await screen.findByText("数据中心一期");
    expect(calls.map((call) => call.path)).toEqual([
      "/api/extensions/bid-write/tasks",
    ]);
  });
});
