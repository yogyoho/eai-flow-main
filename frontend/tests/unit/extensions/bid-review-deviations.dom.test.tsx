import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { createElement, type ReactNode } from "react";

// B9 响应偏离表(spec 2026-11-01 §1.3,原型 s7):计数五格 / pill 五色映射 /
// 默认滤 match + toggle 全量 / 零投影空态 / 证据 chip 开 DocLocateModal。
// mock fetcher 同 tasks-view 测试惯例:按 path 分发,TanStack Query 真实跑。

const mocks = rs.hoisted(() => ({
  search: new URLSearchParams("task_id=t1"),
}));

let responder: (path: string) => Response;
rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string) => responder(path),
}));

rs.mock("next/navigation", () => ({
  usePathname: () => "/bid-review/deviations",
  useSearchParams: () => mocks.search,
  useRouter: () => ({ push: () => {} }),
}));

import { DeviationsView } from "@/extensions/bid-review/components/DeviationsView";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

const TASK = {
  id: "t1",
  owner_id: "o",
  status: "done",
  mode: "quick",
  progress: {},
  error: null,
  biz_no: "TBR-20261101-0001",
  engine_meta: {
    docs: [
      { doc_id: "招标文件.docx", role: "tender", kind: "docx", status: "parsed" },
      { doc_id: "投标文件.docx", role: "bid", kind: "docx", status: "parsed" },
    ],
  },
  prev_task_id: null,
  created_at: "2026-11-01T00:00:00Z",
  fatal_unhandled: null,
  need_human_count: 0,
};

const ITEMS = [
  { item: "投标保证金", tender_req: "10万元", bid_response: null, kind: "missing", severity: "fatal", evidence: { role: "tender", quote: "保证金10万元", page: 5 } },
  { item: "付款节点", tender_req: "30日", bid_response: "60日", kind: "negative", severity: "major", evidence: { role: "bid", quote: "验收后60日", page: 2 } },
  { item: "培训次数", tender_req: "≥3次", bid_response: "2次", kind: "negative", severity: "minor", evidence: null },
  { item: "免费培训", tender_req: null, bid_response: "自行增报", kind: "extra", severity: "major", evidence: { role: "bid", quote: "免费培训", page: 52 } },
  { item: "质保期", tender_req: "24个月", bid_response: "36个月", kind: "positive", severity: null, evidence: { role: "bid", quote: "36个月", page: 45 } },
  { item: "交货期", tender_req: "90天", bid_response: "90天", kind: "match", severity: null, evidence: null },
];

const COUNTS = { tender_items: 5, bid_items: 5, negative: 2, missing: 1, extra: 1 };

function setupRoutes(opts?: { zero?: boolean }) {
  responder = (path: string) => {
    if (path.startsWith("/api/extensions/bid-review/tasks/t1/deviations")) {
      return jsonResponse(opts?.zero ? { counts: { tender_items: 0, bid_items: 0, negative: 0, missing: 0, extra: 0 }, items: [] } : { counts: COUNTS, items: ITEMS });
    }
    if (path === "/api/extensions/bid-review/tasks") {
      return jsonResponse({ items: [TASK] });
    }
    return new Response("not found", { status: 404 });
  };
}

function renderView(): ReturnType<typeof render> {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren): ReactNode =>
    createElement(QueryClientProvider, { client: qc }, children);
  return render(createElement(DeviationsView), { wrapper });
}

beforeEach(() => {
  mocks.search = new URLSearchParams("task_id=t1");
});
afterEach(cleanup);

describe("DeviationsView(原型 s7)", () => {
  it("计数五格渲染服务端 counts", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("未响应（漏项）")).toBeTruthy());
    expect(screen.getByText("招标清单条目")).toBeTruthy();
    expect(screen.getByText("投标响应条目")).toBeTruthy();
    expect(screen.getByText("负偏离")).toBeTruthy();
    expect(screen.getByText("擅自增项")).toBeTruthy();
  });

  it("页头致命 stage-chip:missing>0 显示 N 项致命偏离", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("1 项致命偏离（漏项）")).toBeTruthy());
  });

  it("pill 五色映射:漏项err/负偏离主要orange/次要warn/增项orange/正偏离ok", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("漏项 · 致命")).toBeTruthy());
    expect((screen.getByText("漏项 · 致命").closest("span") as HTMLElement).className).toContain("pill-err");
    expect(screen.getByText("负偏离 · 主要").className).toContain("pill-orange");
    expect(screen.getByText("负偏离 · 次要").className).toContain("pill-warn");
    expect(screen.getByText("擅自增项 · 主要").className).toContain("pill-orange");
    expect(screen.getByText("正偏离 · 优").className).toContain("pill-ok");
  });

  it("默认隐藏一致项,toggle 显示全量(含 match 行)", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("投标保证金")).toBeTruthy());
    expect(screen.queryByText("交货期")).toBeNull(); // match 默认滤掉
    fireEvent.click(screen.getByRole("button", { name: "显示一致项" }));
    expect(screen.getByText("交货期")).toBeTruthy();
    expect(screen.getByText("一致").className).toContain("pill-ok");
  });

  it("零投影空态:引导「未包含偏离维度」而非空表", async () => {
    setupRoutes({ zero: true });
    renderView();
    await waitFor(() => expect(screen.getByText(/未包含偏离维度/)).toBeTruthy());
  });

  it("证据 chip 点击开 DocLocateModal(role 解析为任务 docs 的 doc_id)", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByText("招标文件.docx p.5")).toBeTruthy());
    fireEvent.click(screen.getByText("招标文件.docx p.5"));
    await waitFor(() => expect(screen.getByRole("dialog", { name: "定位原文" })).toBeTruthy());
  });

  it("「导出偏离表」按钮在场", async () => {
    setupRoutes();
    renderView();
    await waitFor(() => expect(screen.getByRole("button", { name: "导出偏离表" })).toBeTruthy());
  });
});
