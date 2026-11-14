import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

const calls: Array<{ path: string; init?: RequestInit }> = [];
let taskStatus = "extracting";

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    if (path.endsWith("/tasks")) {
      return jsonRes({ items: [{ ...TASK, status: taskStatus }] });
    }
    if (path.endsWith("/matrix")) {
      return jsonRes(taskStatus === "matrix_ready" ? MATRIX : EMPTY_MATRIX);
    }
    return jsonRes({ detail: "not found" }, 404);
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
  status: "extracting",
  progress: { stage: "extracting", pct: 50, msg: "extracting" },
  error: null,
  project_name: "Demo",
  lot_name: "Lot",
  tender_no: "T-2026-1",
  created_at: "2026-11-13T08:00:00Z",
  engine_meta: { matrix_counts: { total: 1, star: 0, blocked: 0 } },
};

const ROW = {
  clause_id: "clause:2",
  kind: "clause",
  source_path: "tender.commitments",
  requirement: "Requirement A",
  star: false,
  strategy: "positive",
  target_section: "",
  evidence_refs: [],
  status: "draft",
  conf: 0.9,
  verified: true,
  note: "",
};

const MATRIX = {
  schema_version: "1.0.0",
  vocab: {
    strategies: ["pending", "full", "positive", "negative"],
    statuses: ["draft", "confirmed", "blocked"],
    kinds: ["attachment", "clause", "aggregate"],
  },
  items: [ROW],
};

const EMPTY_MATRIX = { ...MATRIX, items: [] };

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

describe("bid-write IntakeView matrix refresh", () => {
  beforeEach(() => {
    calls.length = 0;
    taskStatus = "extracting";
  });

  afterEach(() => {
    cleanup();
  });

  it("refetches matrix after the task turns matrix_ready", async () => {
    renderView();

    await waitFor(() =>
      expect(calls.some((call) => call.path.endsWith("/matrix"))).toBe(true),
    );
    expect(screen.queryByText("clause:2")).toBeNull();

    taskStatus = "matrix_ready";

    await waitFor(
      () => expect(screen.getAllByText("clause:2").length).toBeGreaterThan(0),
      { timeout: 8000 },
    );
  }, 15000);
});
