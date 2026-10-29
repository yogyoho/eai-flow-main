import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// 修复轮 2026-10-29 回归门:TasksView 原硬编码 fatalCount=0 / needHumanCount=0(评审
// Important——合规门禁列表首屏用未经测量的数据伪造『零致命』信号,行级致命数恒『—』)。
// 锁定三类行为:
// ① 未测量(问题清单请求中/失败/处理中任务)→ 卡片与行级致命数显示 —,严禁显示 0;
// ② done/awaiting_confirm/failed 任务逐任务接 issues 实测(useBidIssues 同 queryKey/
//    queryFn 缓存空间)填实卡片聚合与行级致命数;
// ③ false_positive(Task 16 verdict 落库,已处置)不计入『致命未处理』。
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
import type { IssueOut } from "@/extensions/bid-review/types";

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

function makeIssue(partial: Partial<IssueOut>): IssueOut {
  return {
    id: "i1",
    task_id: "t1",
    rule_id: "L1-009",
    layer: "L1",
    severity: "fatal",
    verdict: "violation",
    clause_id: null,
    message: "投标总价超过最高限价",
    fix: "复核报价汇总与含税口径",
    evidence: [],
    dedup_key: "L1-009|-|k",
    need_human: false,
    confidence: 1.0,
    created_at: "2026-10-29T00:00:00Z",
    ...partial,
  };
}

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

/** 行级致命数格文本(任务行第 5 列:任务名/模式/状态/进度/致命数/更新时间/操作)。 */
function rowFatalCell(taskId: string): string {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[4]?.textContent?.trim() ?? "";
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

describe("bid-review TasksView 伪零回归门(修复轮 2026-10-29)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("问题清单未取到时卡片与行级致命数显示 —,不显示 0(伪零门)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/tasks/t1/issues")) {
        // 请求已发出但永不返回:未测量状态必须保持「未知」呈现而非 0
        return new Promise<Response>(() => undefined) as unknown as Response;
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    // issues 请求确实挂出(是网络未归,而非跳过统计)
    expect(calls.some((c) => c.path.endsWith("/tasks/t1/issues"))).toBe(true);
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
    expect(rowFatalCell("t1")).toBe("—");
  });

  it("done 任务逐行实测填实:卡片聚合与行级致命数", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({ items: [TASK, { ...TASK, id: "t2" }] });
      }
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes({
          items: [
            makeIssue({ id: "i1", severity: "fatal" }),
            makeIssue({ id: "i2", rule_id: "L1-011", severity: "minor" }),
            makeIssue({
              id: "i3",
              rule_id: "L1-013",
              severity: "major",
              need_human: true,
            }),
          ],
        });
      }
      if (path.endsWith("/tasks/t2/issues")) return jsonRes({ items: [] });
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() => expect(rowFatalCell("t1")).toBe("1"));
    await waitFor(() => expect(rowFatalCell("t2")).toBe("0"));
    expect(statValue("致命未处理")).toBe("1");
    expect(statValue("待人工")).toBe("1");
    expect(statValue("总任务")).toBe("2个");
  });

  it("false_positive 已处置致命不计入『致命未处理』(Task 16 verdict 落库契约)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes({
          items: [
            makeIssue({
              id: "i1",
              verdict: "false_positive",
              need_human: false,
            }),
            makeIssue({ id: "i2" }),
            makeIssue({
              id: "i3",
              rule_id: "L1-013",
              severity: "major",
              need_human: true,
            }),
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await waitFor(() => expect(rowFatalCell("t1")).toBe("1"));
    expect(statValue("致命未处理")).toBe("1");
    expect(statValue("待人工")).toBe("1");
  });

  it("处理中任务不入统计:整体未测完卡片显示 —,done 行照常实测", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [TASK, { ...TASK, id: "t2", status: "running" }],
        });
      }
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes({ items: [makeIssue({ id: "i1" })] });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    await waitFor(() => expect(rowFatalCell("t1")).toBe("1"));
    // 处理中任务:不发 issues 请求,行级显示 —(半程快照不得冒充统计)
    expect(rowFatalCell("t2")).toBe("—");
    expect(calls.some((c) => c.path.endsWith("/tasks/t2/issues"))).toBe(false);
    // 组合口径:存在未定型任务 → 卡片不给数字(部分和同样可能是伪低值)
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
  });

  it("问题清单拉取失败显示 —(错误态),不显示 0", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/tasks/t1/issues")) {
        return jsonRes({ detail: "db error" }, 500);
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    await waitFor(() =>
      expect(
        document.querySelector('td [title^="问题清单加载失败"]'),
      ).toBeTruthy(),
    );
    expect(statValue("致命未处理")).toBe("—");
    expect(statValue("待人工")).toBe("—");
    expect(rowFatalCell("t1")).toBe("—");
  });
});
