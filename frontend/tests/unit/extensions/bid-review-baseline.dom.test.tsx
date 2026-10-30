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

// EAI-CUSTOM 2026-10-30 分期建议一期(s3/s4,ui-gaps spec §二):
// ① 解析质量表 = engine_meta.docs 清单(pdf 真页码/assets;docx 无页边界「—」);
// ② 字段对照卡 = GET /tasks/{id}/baselines 行级快照 → 已抽取/缺失 pill +
//    「查看原文」→ content 端点定位弹层(与工作台证据 chip 同源);
// ③ 确认门 gating:仅 awaiting_confirm 可确认,按钮带未确认行数,POST /confirm。
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

import { BaselineView } from "@/extensions/bid-review/components/BaselineView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TASK = (status: string) => ({
  id: "t1",
  owner_id: "u1",
  status,
  mode: "deep",
  progress: { pct: status === "awaiting_confirm" ? 30 : 100 },
  error: null,
  engine_meta: {
    materials_hash: "abcdef1234567890",
    docs: [
      {
        doc_id: "招标文件.pdf",
        role: "tender",
        kind: "pdf",
        pages: 12,
        chars: 3400,
        assets: 1,
        status: "parsed",
      },
      {
        doc_id: "投标文件.docx",
        role: "bid",
        kind: "docx",
        pages: 0,
        chars: 2200,
        assets: 0,
        status: "parsed",
      },
    ],
  },
  prev_task_id: null,
  created_at: "2026-10-30T00:00:00Z",
});

const BASELINES = [
  {
    kind: "tender",
    doc_id: "招标文件.pdf",
    confirmed: false,
    created_at: "2026-10-30T00:00:00Z",
    fields: { "tender.max_price": 8000000, "tender.boq_items": null },
    provenance: {
      "tender.max_price": {
        doc_id: "招标文件.pdf",
        page: 3,
        quote: "最高限价捌佰万元整",
      },
    },
    materials_hash: "abcdef1234567890",
  },
  {
    kind: "bid",
    doc_id: "投标文件.docx",
    confirmed: false,
    created_at: "2026-10-30T00:00:00Z",
    fields: { "bid.total_price": 9000000 },
    provenance: {},
    materials_hash: "abcdef1234567890",
  },
];

const CONTENT = {
  doc: {
    doc_id: "招标文件.pdf",
    role: "tender",
    kind: "pdf",
    pages: 12,
    chars: 3400,
    assets: 1,
    status: "parsed",
  },
  page: 3,
  seq: 2,
  segments: [
    {
      seq: 2,
      page: 3,
      kind: "text",
      text: "投标最高限价:人民币捌佰万元整",
      asset_id: null,
    },
  ],
};

function renderBaseline() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<BaselineView taskId="t1" />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-review BaselineView 分期建议一期(EAI-CUSTOM 2026-10-30)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("解析质量表 + 字段卡对照渲染;查看原文 → content 定位弹层", async () => {
    responder = (path) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: BASELINES });
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("done"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    // 解析质量表:清单行 + OCR 兜底注记(pdf assets=1)
    expect(await screen.findByText("招标文件.pdf")).toBeTruthy();
    expect(screen.getByText("解析质量")).toBeTruthy();
    expect(screen.getByText(/份文档含扫描页/)).toBeTruthy();

    // 字段对照:族按钮 + 字段卡(已抽取/缺失 pill 与值)
    expect(screen.getByRole("button", { name: /招标基准/ })).toBeTruthy();
    expect(await screen.findByText("tender.max_price")).toBeTruthy();
    expect(screen.getByText("8,000,000")).toBeTruthy();
    expect(screen.getByText("tender.boq_items")).toBeTruthy();
    expect(screen.getAllByText("缺失").length).toBeGreaterThan(0);

    // 查看原文 → content?page=3(pdf 真页码直取)→ 定位弹层渲染命中段
    fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path.startsWith("/api/extensions/bid-review/tasks/t1/docs/") &&
            c.path.endsWith("/content?page=3"),
        ),
      ).toBe(true),
    );
    expect(
      await screen.findByRole("dialog", { name: "定位原文" }),
    ).toBeTruthy();
    expect(screen.getByText(/最高限价:人民币捌佰万元整/)).toBeTruthy();
  });

  it("确认门 gating:仅 awaiting_confirm 可确认,按钮带未确认行数并 POST /confirm", async () => {
    responder = (path, init) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: BASELINES });
      if (path.endsWith("/tasks/t1/confirm") && init?.method === "POST")
        return jsonRes(TASK("running"));
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    const btn = await screen.findByRole("button", {
      name: /确认基准包并开始审查/,
    });
    // 基线行到达后按钮才带未确认行数(行数随 baselines 查询异步填充)
    await waitFor(() => expect(btn.textContent).toContain("待确认 2 行"));
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path === "/api/extensions/bid-review/tasks/t1/confirm" &&
            c.init?.method === "POST",
        ),
      ).toBe(true),
    );
  });
});
