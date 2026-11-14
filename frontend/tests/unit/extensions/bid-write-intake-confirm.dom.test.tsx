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

// 低置信阻断行的确认必须带人工依据：空备注不得发 PATCH，填写后只提交
// status=confirmed + note；行级 422 由调用方 toast 展示。
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
  usePathname: () => "/bid-write/intake",
  useSearchParams: () => new URLSearchParams("task_id=t1"),
}));

import { IntakeView } from "@/extensions/bid-write/components/IntakeView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TASK = {
  id: "t1",
  biz_no: "BW-0001",
  status: "matrix_ready",
  progress: { pct: 100 },
  error: null,
  project_name: "数据中心一期",
  lot_name: "标段一",
  tender_no: "T-2026-1",
  created_at: "2026-11-13T08:00:00Z",
  engine_meta: { matrix_counts: { total: 1, star: 0, blocked: 1 } },
};

const BLOCKED_ROW = {
  clause_id: "clause:2",
  kind: "clause",
  source_path: "tender.commitments",
  requirement: "投标有效期不少于 90 日历天",
  star: false,
  strategy: "positive",
  target_section: "二、商务响应",
  evidence_refs: [],
  status: "blocked",
  conf: 0.42,
  verified: false,
  note: "",
};

const MATRIX = {
  schema_version: "1.0.0",
  vocab: {
    strategies: ["pending", "full", "positive", "negative"],
    statuses: ["draft", "confirmed", "blocked"],
    kinds: ["attachment", "clause", "aggregate"],
  },
  items: [BLOCKED_ROW],
};

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<IntakeView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-write IntakeView 阻断行确认", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = (path, init) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/matrix") && init?.method === "PATCH") {
        return jsonRes({
          ...BLOCKED_ROW,
          status: "confirmed",
          note: "已对照招标文件 p.18 原文",
        });
      }
      if (path.endsWith("/matrix")) return jsonRes(MATRIX);
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
  });

  afterEach(() => {
    cleanup();
  });

  it("空备注不发 PATCH，填写依据后才确认", async () => {
    renderView();

    fireEvent.click(await screen.findByRole("button", { name: "确认" }));
    expect(screen.getByText("低置信行确认")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "确认并解阻" }));
    expect(calls.some((call) => call.init?.method === "PATCH")).toBe(false);

    fireEvent.change(screen.getByPlaceholderText(/已对照招标文件 p.18 原文/), {
      target: { value: "已对照招标文件 p.18 原文，确认投标有效期为 90 天" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认并解阻" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.init?.method === "PATCH" &&
            call.path ===
              "/api/extensions/bid-write/tasks/t1/matrix/clause%3A2",
        ),
      ).toBe(true),
    );
    const patch = calls.find((call) => call.init?.method === "PATCH");
    const body = patch?.init?.body;
    if (typeof body !== "string") throw new Error("PATCH body 不是字符串");
    expect(JSON.parse(body)).toEqual({
      status: "confirmed",
      note: "已对照招标文件 p.18 原文，确认投标有效期为 90 天",
    });
  });
});
