import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// micro-A 2026-10-29 回归门:行级致命数与卡片的数据源=后端 GET /tasks 每任务聚合
// 字段(fatal_unhandled / need_human_count),口径由后端 pytest 锁定。
// 2026-10-31 Plan2 契约演进(spec §4.1 统计卡换血+§3.2 选中任务模型):
// ① 统计卡从「跨任务 Σ」换血为「选中任务体征」五格:致命未处理/待人工复核/
//    问题总数/误报已剔除/审查用时(B1 done_at 落地前恒 —);
// ② issues 请求契约从「零请求」演进为「仅选中任务一条」(O(1) 非 N+1——
//    逐任务批量请求仍然禁止,断言恰一条且只对选中任务);
// ③ 行点击=选中(router.replace ?task_id=),不再整行跳转;跳转走操作列;
// ④ 列变 任务号/模式/状态/可提交判定/致命·待人工(合并)/创建时间/操作(7 列;
//    B1 落地后 9 列全量对齐,fatal 格下标随之再调);
// ⑤ 可提交判定口径:done 且 fatal>0 → 不建议提交(err);done 且 =0 → 建议提交
//    (ok);未出结果/未统计 → —(未经测量不得判「建议提交」)。
// 伪零纪律本身不放松:半程快照与 null 计数一律「—」。
const calls: Array<{ path: string; init?: RequestInit }> = [];
const routerReplaces: string[] = [];
let responder: (
  path: string,
  init?: RequestInit,
) => Response | Promise<Response>;
let searchParams = new URLSearchParams();

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({}),
  usePathname: () => "/bid-review",
  useRouter: () => ({
    push: rs.fn(),
    replace: (href: string) => {
      routerReplaces.push(href);
    },
    refresh: rs.fn(),
  }),
  useSearchParams: () => searchParams,
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

/** 选中任务(s1 列表首位=最新)的 issues 响应体;条目只需 verdict 字段。 */
function issuesBody(verdicts: string[]): unknown {
  return {
    items: verdicts.map((v, i) => ({
      id: `i${i}`,
      severity: "fatal",
      verdict: v,
      need_human: false,
      confidence: 0.9,
    })),
  };
}

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** 卡片值段文本:.metric-strip 内按 label 定位 .metric-label,取相邻 .metric-value
 * (指标 label 与表头/状态 pill 同文,不能全局 getByText)。 */
function statValue(label: string): string {
  const strip = document.querySelector(".metric-strip");
  const labelEl = Array.from(
    strip?.querySelectorAll(".metric-label") ?? [],
  ).find((n) => n.textContent?.trim() === label);
  return labelEl?.nextElementSibling?.textContent?.trim() ?? "";
}

/** 致命/待人工合并格(任务行第 5 列:任务号/模式/状态/可提交判定/致命·待人工/创建时间/操作)。 */
function fatalCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[4] ?? null;
}

/** 可提交判定格(任务行第 4 列)。 */
function verdictCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[3] ?? null;
}

function rowOf(taskId: string): HTMLTableRowElement | null {
  return screen.getByTitle(taskId).closest("tr");
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

describe("bid-review TasksView 选中任务体征契约门(Plan2 2026-10-31)", () => {
  beforeEach(() => {
    calls.length = 0;
    routerReplaces.length = 0;
    searchParams = new URLSearchParams();
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("done 任务:行级合并格填实(1 / 1 带 v-hot),卡片=选中任务体征五格", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            TASK,
            { ...TASK, id: "t2", fatal_unhandled: 0, need_human_count: 0 },
          ],
        });
      }
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes(
          issuesBody(["unresolved", "unresolved", "false_positive"]),
        );
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() => {
      expect(fatalCell("t1")?.textContent?.trim()).toBe("1 / 1");
      expect(fatalCell("t2")?.textContent?.trim()).toBe("0 / 0");
    });
    expect(fatalCell("t1")?.querySelector(".v-hot")).not.toBeNull();
    expect(fatalCell("t2")?.querySelector(".v-hot")).toBeNull();
    // 可提交判定:done+fatal>0 不建议提交;done+fatal=0 建议提交
    expect(verdictCell("t1")?.textContent?.trim()).toBe("不建议提交");
    expect(verdictCell("t2")?.textContent?.trim()).toBe("建议提交");
    // 选中任务(fallback 最新=t1)体征五格
    expect(statValue("致命未处理")).toBe("1");
    expect(statValue("待人工复核")).toBe("1");
    expect(statValue("问题总数")).toBe("3");
    expect(statValue("误报已剔除")).toBe("1");
    expect(statValue("审查用时")).toBe("—");
  });

  it("半程任务行级「—」;issues 请求恰一条且只对选中任务(非 N+1)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [TASK, { ...TASK, id: "t2", status: "running" }],
        });
      }
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes(issuesBody(["unresolved", "false_positive"]));
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() =>
      expect(statValue("问题总数")).toBe("2"),
    );
    // 处理中任务:行级 —(半程快照不得冒充统计),判定也不产生
    expect(fatalCell("t2")?.textContent?.trim()).toBe("—");
    expect(verdictCell("t2")?.textContent?.trim()).toBe("—");
    // 契约演进:仅选中任务(t1=最新)一条 issues 请求;逐任务批量仍然禁止
    const issueCalls = calls.filter((c) => c.path.includes("/issues"));
    expect(issueCalls).toHaveLength(1);
    expect(issueCalls[0]?.path.endsWith("/tasks/t1/issues")).toBe(true);
    expect(calls.some((c) => c.path.includes("/tasks/t2/issues"))).toBe(false);
    // 选中任务已出结果 → 体征照常填实(不再是「有未定型任务全卡 —」)
    expect(statValue("致命未处理")).toBe("1");
    expect(statValue("待人工复核")).toBe("1");
  });

  it("计数缺失(null=未统计)行级「— / —」;问题总数按 issues 真值", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [{ ...TASK, fatal_unhandled: null, need_human_count: null }],
        });
      }
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes(issuesBody(["unresolved", "false_positive"]));
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    await waitFor(() => expect(statValue("问题总数")).toBe("2"));
    expect(fatalCell("t1")?.textContent?.trim()).toBe("— / —");
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工复核")).toBe("—");
    expect(statValue("误报已剔除")).toBe("1");
  });

  it("任务列表加载失败:选中为空、卡片全「—」、零 issues 请求", async () => {
    responder = () => jsonRes({ detail: "db error" }, 500);
    renderTasks();
    await screen.findByText(/^任务列表加载失败/);
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工复核")).toBe("—");
    expect(statValue("问题总数")).toBe("—");
    expect(statValue("误报已剔除")).toBe("—");
    expect(calls.some((c) => c.path.includes("/issues"))).toBe(false);
  });

  it("操作列分派:待确认→去基准确认 / done→查看结果 / 在途→查看进度 / failed 不渲染", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            TASK,
            { ...TASK, id: "t2", status: "awaiting_confirm" },
            { ...TASK, id: "t3", status: "parsing" },
            { ...TASK, id: "t4", status: "failed" },
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t4");
    const linkOf = (id: string) =>
      rowOf(id)?.querySelector("td:last-child a") ?? null;
    expect(linkOf("t2")?.textContent?.trim()).toBe("去基准确认");
    expect(linkOf("t2")?.getAttribute("href")).toBe(
      "/bid-review/baseline?task_id=t2",
    );
    expect(linkOf("t1")?.textContent?.trim()).toBe("查看结果");
    expect(linkOf("t1")?.getAttribute("href")).toBe(
      "/bid-review/workbench?task_id=t1",
    );
    expect(linkOf("t3")?.textContent?.trim()).toBe("查看进度");
    expect(linkOf("t4")).toBeNull();
    expect(rowOf("t4")?.querySelector("td:last-child")?.textContent).toContain(
      "—",
    );
  });

  it("行点击=选中(router.replace ?task_id),选中行高亮 tr.on", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [TASK, { ...TASK, id: "t2", status: "running" }],
        });
      }
      return jsonRes({}, 404);
    };
    const { rerender } = renderTasks();
    await screen.findByTitle("t2");
    fireEvent.click(rowOf("t2")!);
    expect(routerReplaces).toContain("/bid-review?task_id=t2");
    // URL 变更后(此处直接驱动 mock)重渲染:t2 行 on、t1 行非 on
    searchParams = new URLSearchParams("task_id=t2");
    rerender(<TasksView />);
    await screen.findByTitle("t2");
    expect(rowOf("t2")?.className).toContain("on");
    expect(rowOf("t1")?.className).not.toContain("on");
  });
});
