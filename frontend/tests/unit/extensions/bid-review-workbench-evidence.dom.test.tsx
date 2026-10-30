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

// EAI-CUSTOM 2026-10-30 证据管线(spec 2026-10-30-bid-review-evidence-pipeline-design):
// ① 真证据 chip 可点 → GET /tasks/{id}/docs/{doc}/content?page=(pdf 真页码直取页),
//    弹层渲染片段窗口 + 命中高亮;
// ② content 404 → 「未定位到原文」如实呈现(不造假原文);
// ③ 「待人工」按钮 → POST /issues/{id}/feedback {action:"need_human"}(spec D9)。
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
  evidence: [
    {
      doc_id: "bid.pdf",
      page: 3,
      section_path: "bid.total_price",
      text: "投标总价:¥9,000,000",
    },
  ],
  dedup_key: "L1-009|-|k",
  need_human: false,
  confidence: 1.0,
  created_at: "2026-10-29T00:00:00Z",
};

const CONTENT = {
  doc: {
    doc_id: "bid.pdf",
    role: "bid",
    kind: "pdf",
    pages: 12,
    chars: 5000,
    assets: 0,
    status: "parsed",
  },
  page: 3,
  seq: 2,
  segments: [
    { seq: 2, page: 3, kind: "text", text: "投标总价:¥9,000,000", asset_id: null },
    { seq: 3, page: 3, kind: "table", text: "| 项目 | 金额 |", asset_id: null },
  ],
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
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

describe("bid-review WorkbenchView 证据管线(EAI-CUSTOM 2026-10-30)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("证据 chip 点击 → content?page= 定位弹层渲染命中窗口", async () => {
    responder = (path) => {
      if (path.includes("/docs/bid.pdf/content"))
        return jsonRes(CONTENT);
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: /bid\.pdf/ }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path ===
            "/api/extensions/bid-review/tasks/t1/docs/bid.pdf/content?page=3",
        ),
      ).toBe(true),
    );
    expect(await screen.findByRole("dialog", { name: "定位原文" })).toBeTruthy();
    expect(screen.getAllByText("投标总价:¥9,000,000").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/第\s*3\s*页/)).toBeTruthy();
  });

  it("content 404 → 未定位到原文如实呈现", async () => {
    responder = (path) => {
      if (path.includes("/docs/bid.pdf/content")) return jsonRes({ detail: "未定位到原文" }, 404);
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: /bid\.pdf/ }));
    expect(await screen.findByText(/未定位到原文/)).toBeTruthy();
  });

  it("待人工按钮 → POST feedback action=need_human", async () => {
    responder = (path) => {
      if (path.endsWith("/feedback")) return jsonRes({ ...ISSUE, verdict: "need_human", need_human: true });
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: "待人工" }));
    await waitFor(() => {
      const fb = calls.find((c) => c.path.endsWith("/issues/i1/feedback"));
      expect(fb).toBeTruthy();
      const body = fb?.init?.body;
      if (typeof body !== "string") throw new Error("feedback body missing");
      expect(JSON.parse(body)).toEqual({
        action: "need_human",
        note: "",
      });
    });
  });
});
