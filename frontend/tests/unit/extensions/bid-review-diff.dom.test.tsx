import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { createElement, type ReactNode } from "react";

// B10 版本差异整屏(spec 2026-11-01 §2,原型 s8):页头 prev→cur + 变更影响
// N 项问题中的 M 项(M=added+removed,N=added+unchanged=新版问题总数) /
// 关键内容差异 dif-box(−prev +cur) / 规则影响 4 列表(两侧 present/severity
// pill) / 无 prev 空态 / 旧网关缺 fields+rules 键诚实兜底。

const mocks = rs.hoisted(() => ({
  search: new URLSearchParams("task_id=t2&prev=t1"),
}));

let responder: (path: string) => Response;
rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string) => responder(path),
}));

rs.mock("next/navigation", () => ({
  usePathname: () => "/bid-review/diff",
  useSearchParams: () => mocks.search,
  useRouter: () => ({ push: () => {} }),
}));

import { DiffView } from "@/extensions/bid-review/components/DiffView";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

const TASKS = [
  {
    id: "t2",
    owner_id: "o",
    status: "done",
    mode: "quick",
    progress: {},
    error: null,
    biz_no: "TBR-CUR-0002",
    engine_meta: {},
    prev_task_id: "t1",
    created_at: "2026-11-01T00:00:00Z",
    fatal_unhandled: null,
    need_human_count: 0,
  },
  {
    id: "t1",
    owner_id: "o",
    status: "done",
    mode: "quick",
    progress: {},
    error: null,
    biz_no: "TBR-PREV-0001",
    engine_meta: {},
    prev_task_id: null,
    created_at: "2026-10-31T00:00:00Z",
    fatal_unhandled: null,
    need_human_count: 0,
  },
];

const DIFF = {
  added: [
    {
      id: "i1",
      rule_id: "L1-009",
      layer: "L1",
      severity: "fatal",
      message: "调价后仍超限价 2,300 元",
      need_human: false,
    },
  ],
  removed: [{ rule_id: "L1-010", severity: "fatal", message: "总价栏未对齐明细" }],
  unchanged_count: 3,
  fields: [
    { path: "project.total_price", label: "投标总价", prev: "1,000,000.00", cur: "1,002,300.00" },
    { path: "project.warranty", label: "质保期", prev: "24个月", cur: "36个月" },
  ],
  rules: [
    { rule_id: "L1-010", prev: { present: true, severity: "fatal" }, cur: { present: false, severity: null } },
    { rule_id: "L1-009", prev: { present: true, severity: "fatal" }, cur: { present: true, severity: "fatal" } },
    { rule_id: "L3-005", prev: { present: false, severity: null }, cur: { present: true, severity: "major" } },
  ],
};

function setupRoutes(opts?: { legacy?: boolean }) {
  responder = (path: string) => {
    if (path.startsWith("/api/extensions/bid-review/tasks/t2/diff")) {
      if (opts?.legacy) {
        // 旧网关:仅 B7 三键,无 fields/rules
        const { fields: _f, rules: _r, ...legacy } = DIFF;
        return jsonResponse(legacy);
      }
      return jsonResponse(DIFF);
    }
    if (path === "/api/extensions/bid-review/tasks") {
      return jsonResponse({ items: TASKS });
    }
    return new Response("not found", { status: 404 });
  };
}

function renderView(): ReturnType<typeof render> {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren): ReactNode =>
    createElement(QueryClientProvider, { client: qc }, children);
  return render(createElement(DiffView), { wrapper });
}

beforeEach(() => {
  mocks.search = new URLSearchParams("task_id=t2&prev=t1");
});
afterEach(cleanup);

describe("DiffView(原型 s8)", () => {
  it("页头 prev→cur biz 与变更影响 N 项问题中的 M 项", async () => {
    setupRoutes();
    renderView();
    // M = added(1) + removed(1) = 2;N = added(1) + unchanged(3) = 4(新版问题总数)
    await waitFor(() => expect(screen.getByText(/变更影响 4 项问题中的 2 项/)).toBeTruthy());
    expect(screen.getByText(/TBR-PREV-0001/)).toBeTruthy();
    expect(screen.getByText(/TBR-CUR-0002/)).toBeTruthy();
  });

  it("关键内容差异:dif-box −prev +cur 逐路径", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("投标总价")).toBeTruthy());
    expect(screen.getByText(/− 1,000,000\.00/)).toBeTruthy();
    expect(screen.getByText(/\+ 1,002,300\.00/)).toBeTruthy();
    expect(screen.getByText("质保期")).toBeTruthy();
    expect(screen.getByText(/− 24个月/)).toBeTruthy();
    expect(screen.getByText(/\+ 36个月/)).toBeTruthy();
  });

  it("规则影响 4 列表:两侧 present/severity → pill 映射", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("L1-010")).toBeTruthy());
    // L1-010:prev fatal(pill-err) → cur 无问题(pill-ok)
    const row1010 = screen.getByText("L1-010").closest("tr") as HTMLElement;
    expect(row1010.textContent).toContain("无问题");
    expect(row1010.querySelectorAll(".pill-ok").length).toBeGreaterThan(0);
    // L1-009:两侧 fatal(pill-err),变化行排序在前
    const row1009 = screen.getByText("L1-009").closest("tr") as HTMLElement;
    expect(row1009.querySelectorAll(".pill-err").length).toBe(2);
    // L3-005:prev 无 → cur major(pill-orange,新增问题)
    const row3005 = screen.getByText("L3-005").closest("tr") as HTMLElement;
    expect(row3005.querySelectorAll(".pill-orange").length).toBeGreaterThan(0);
  });

  it("无 prev 参数:空态引导而非裸 404", async () => {
    setupRoutes();
    mocks.search = new URLSearchParams("task_id=t2");
    renderView();
    expect(screen.getByText(/未指定基准任务/)).toBeTruthy();
  });

  it("旧网关缺 fields/rules 键:诚实兜底不崩", async () => {
    setupRoutes({ legacy: true });
    renderView();
    await waitFor(() => expect(screen.getByText(/变更影响 4 项问题中的 2 项/)).toBeTruthy());
    expect(screen.getByText(/无字段级差异可比/)).toBeTruthy();
  });
});
