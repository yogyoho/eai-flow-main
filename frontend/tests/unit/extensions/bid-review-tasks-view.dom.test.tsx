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
  // B1 批(Plan4 2026-10-31):业务号/项目/标段/更新时间/完成时刻/主要未处理/创建人
  biz_no: "TBR-20261029-0001",
  project_name: "XX数据中心一期采购项目",
  lot_name: "标段一(机电设备)",
  tender_no: null,
  updated_at: "2026-10-30T16:20:00Z",
  done_at: "2026-10-29T00:11:32Z",
  main_unhandled: 4,
  created_by_name: "张工",
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

/** 致命/主要合并格(九列:任务号/项目·标段/模式/状态/可提交判定/致命·主要/创建人/更新时间/操作)。 */
function fatalCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[5] ?? null;
}

/** 可提交判定格(九列下标 4:任务号/项目·标段/模式/状态/判定)。 */
function verdictCell(taskId: string): Element | null {
  const row = screen.getByTitle(taskId).closest("tr");
  return row?.querySelectorAll("td")[4] ?? null;
}

/** 任意列取格(Plan4 九列:0=任务号 1=项目·标段 4=判定 5=致命·主要 6=创建人 7=更新时间)。 */
function cellAt(taskId: string, i: number): Element | null {
  return (
    screen.getByTitle(taskId).closest("tr")?.querySelectorAll("td")[i] ?? null
  );
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
            {
              ...TASK,
              id: "t2",
              fatal_unhandled: 0,
              need_human_count: 0,
              main_unhandled: 0,
            },
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
      expect(fatalCell("t1")?.textContent?.trim()).toBe("1 / 4");
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
    // Plan4 T3:审查用时=done_at−created_at 客户端算(2026-10-29T00:00Z→00:11:32Z)
    expect(statValue("审查用时")).toBe("11m 32s");
    // Plan4 T2:九列——任务号=biz_no / 项目·标段 / 致命·主要 / 创建人 / 更新时间
    expect(cellAt("t1", 0)?.textContent?.trim()).toBe("TBR-20261029-0001");
    expect(cellAt("t1", 1)?.textContent?.trim()).toBe(
      "XX数据中心一期采购项目 · 标段一(机电设备)",
    );
    expect(cellAt("t1", 5)?.textContent?.trim()).toBe("1 / 4");
    expect(cellAt("t1", 5)?.querySelector(".v-hot")).not.toBeNull();
    expect(cellAt("t1", 6)?.textContent?.trim()).toBe("张工");
    // 更新时间=formatDate 本地时区渲染(TZ 无关断言,CI=UTC/本机=UTC+8 都过)
    expect(cellAt("t1", 7)?.textContent?.trim()).toMatch(
      /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
    );
    // 2026-10-31 用户定案:选中任务号随页头标题展示;Plan4 换 TBR 业务号
    expect(document.querySelector(".page-head h2")?.textContent).toContain(
      "TBR-20261029-0001",
    );
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
    // 处理中任务:行级 —(半程快照不得冒充统计),判定也不产生;项目列与结果无关照常真值
    expect(fatalCell("t2")?.textContent?.trim()).toBe("—");
    expect(verdictCell("t2")?.textContent?.trim()).toBe("—");
    expect(cellAt("t2", 1)?.textContent?.trim()).toBe(
      "XX数据中心一期采购项目 · 标段一(机电设备)",
    );
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
          items: [
            {
              ...TASK,
              fatal_unhandled: null,
              need_human_count: null,
              main_unhandled: null,
            },
          ],
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
    // Plan6 (spec §4.3):在途查看进度改指 /parsing 归拢专屏(原 workbench)
    expect(linkOf("t3")?.getAttribute("href")).toBe(
      "/bid-review/parsing?task_id=t3",
    );
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

  it("存量降级:B1 字段 null → 任务号回退 id8,项目/创建人/更新时间/用时 —", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            {
              ...TASK,
              biz_no: null,
              project_name: null,
              lot_name: null,
              updated_at: null,
              done_at: null,
              main_unhandled: null,
              created_by_name: null,
            },
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    expect(cellAt("t1", 0)?.textContent?.trim()).toBe("t1");
    expect(cellAt("t1", 1)?.textContent?.trim()).toBe("—");
    expect(cellAt("t1", 6)?.textContent?.trim()).toBe("—");
    expect(cellAt("t1", 7)?.textContent?.trim()).toBe("—");
    expect(statValue("审查用时")).toBe("—");
    expect(document.querySelector(".page-head h2")?.textContent).toContain("t1");
  });

  it("搜索命中业务号与项目名(客户端过滤,foot 计数跟随)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            TASK,
            {
              ...TASK,
              id: "t2",
              biz_no: "TBR-20261029-0002",
              project_name: "智慧园区消防改造项目",
              lot_name: null,
            },
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    const inp = screen.getByLabelText("搜索任务号 / 项目名");
    // 项目名命中:仅 t2
    fireEvent.change(inp, { target: { value: "智慧园区" } });
    expect(screen.queryByTitle("t1")).toBeNull();
    expect(screen.getByTitle("t2")).toBeTruthy();
    // 业务号尾段命中:仅 t1
    fireEvent.change(inp, { target: { value: "0001" } });
    expect(screen.getByTitle("t1")).toBeTruthy();
    expect(screen.queryByTitle("t2")).toBeNull();
    expect(document.querySelector(".tbl-foot")?.textContent).toContain(
      "共 1 / 2",
    );
  });

  it("对话框:身份字段随 FormData 提交,留空不发(裁定12+14)", async () => {
    responder = (path, init) => {
      if (init?.method === "POST") {
        return jsonRes({
          ...TASK,
          id: "t-new",
          biz_no: "TBR-20261031-0001",
        });
      }
      if (path.endsWith("/tasks")) {
        return jsonRes({ items: [TASK] });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    fireEvent.click(screen.getByRole("button", { name: "新建审查任务" }));
    fireEvent.change(screen.getByLabelText("项目 / 标段名称"), {
      target: { value: "XX数据中心二期" },
    });
    fireEvent.change(screen.getByLabelText("招标编号"), {
      target: { value: "TZ-2026-009" },
    });
    fireEvent.change(screen.getByLabelText("选择招标文件"), {
      target: { files: [new File(["T"], "t.txt", { type: "text/plain" })] },
    });
    fireEvent.change(screen.getByLabelText("选择投标文件"), {
      target: { files: [new File(["B"], "b.txt", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() => {
      const post = calls.find((c) => c.init?.method === "POST");
      expect(post).toBeTruthy();
      const form = post?.init?.body as FormData;
      expect(form.get("mode")).toBe("quick");
      expect(form.get("project_name")).toBe("XX数据中心二期");
      expect(form.get("tender_no")).toBe("TZ-2026-009");
      // 留空不 append(=引擎抽取回填位)
      expect(form.get("lot_name")).toBeNull();
      expect(form.getAll("tender_files")).toHaveLength(1);
      expect(form.getAll("bid_files")).toHaveLength(1);
    });
  });

  it("对话框:单文件 >200MB 拒收(errbar 提示,文件不入列)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    fireEvent.click(screen.getByRole("button", { name: "新建审查任务" }));
    const big = new File(["x"], "huge.bin");
    Object.defineProperty(big, "size", { value: 201 * 1024 * 1024 });
    fireEvent.change(screen.getByLabelText("选择招标文件"), {
      target: { files: [big] },
    });
    expect(screen.getByRole("alert").textContent).toContain(
      "超过 200MB 上限",
    );
    expect(screen.queryByTitle("huge.bin")).toBeNull();
    // 招标侧被拒收=空 → 创建门保持关闭
    expect(screen.getByRole("button", { name: "创建任务" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});
