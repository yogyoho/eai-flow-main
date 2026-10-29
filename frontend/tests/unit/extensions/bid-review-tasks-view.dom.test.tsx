import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// micro-A 2026-10-29 回归门:行级致命数与致命未处理/待人工两卡的数据源改为后端
// GET /tasks 每任务聚合字段(fatal_unhandled / need_human_count,ui-spec §3.1「数据=
// GET /tasks 聚合」),TasksView 不再逐任务拉 issues(N+1 移除)。锁定四类行为:
// ① done 任务行级致命数/卡片由计数字段填实(>0 error 深档,=0 普通档);
// ② 处理中任务(半程快照)行级与卡片显示 —,且零 issues 请求;
// ③ 计数缺失(null=未统计)显示 —,严禁显示 0(伪零纪律沿修复轮 2026-10-29);
// ④ 任务列表加载失败卡片显示 —。口径(误报剔除/need_human 计入)由后端 pytest 锁定
// (test_bid_review_routers.py::test_list_tasks_per_task_issue_counts)。
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

import { TasksView } from "@/extensions/bid-review/components/TasksView";

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
  fatal_unhandled: 1,
  need_human_count: 1,
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** StatCard 值段文本(label span 的相邻 value span)。 */
function statValue(label: string): string {
  return screen.getByText(label).nextElementSibling?.textContent?.trim() ?? "";
}

/** 行级致命数格(任务行第 5 列:任务名/模式/状态/进度/致命数/更新时间/操作)。 */
function fatalCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[4] ?? null;
}

function renderTasks() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<TasksView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-review TasksView 计数契约门(micro-A 2026-10-29)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("done 任务由 GET /tasks 计数填实:行级致命数与卡片聚合,>0 error 深档", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            TASK,
            { ...TASK, id: "t2", fatal_unhandled: 0, need_human_count: 0 },
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() => {
      expect(fatalCell("t1")?.textContent?.trim()).toBe("1");
      expect(fatalCell("t2")?.textContent?.trim()).toBe("0");
    });
    expect(statValue("致命未处理")).toBe("1");
    expect(statValue("待人工")).toBe("1");
    expect(statValue("总任务")).toBe("2个");
    expect(fatalCell("t1")?.querySelector("span")?.className).toContain(
      "text-[var(--error-700)]",
    );
    expect(fatalCell("t2")?.querySelector("span")?.className).not.toContain(
      "text-[var(--error-700)]",
    );
  });

  it("处理中任务不入统计:行级「—」、卡片「—」,且零 issues 请求(N+1 移除)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [TASK, { ...TASK, id: "t2", status: "running" }],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() => expect(fatalCell("t1")?.textContent?.trim()).toBe("1"));
    // 处理中任务:行级显示 —(半程快照不得冒充统计)
    expect(fatalCell("t2")?.textContent?.trim()).toBe("—");
    // 新契约:列表页不再发任何逐任务 issues 请求
    expect(calls.some((c) => c.path.includes("/issues"))).toBe(false);
    // 组合口径:存在未定型任务 → 卡片不给数字(部分和同样可能是伪低值)
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
  });

  it("计数缺失(null=未统计)显示「—」不显示 0(伪零门)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [{ ...TASK, fatal_unhandled: null, need_human_count: null }],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    await waitFor(() => expect(fatalCell("t1")?.textContent?.trim()).toBe("—"));
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
  });

  it("任务列表加载失败:卡片显示「—」,不显示 0", async () => {
    responder = () => jsonRes({ detail: "db error" }, 500);
    renderTasks();
    await screen.findByText(/^任务列表加载失败/);
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
    expect(calls.some((c) => c.path.includes("/issues"))).toBe(false);
  });
});
