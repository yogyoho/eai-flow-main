// 批三十:编辑器真执行器 API——路径/方法/body + 非 2xx 抛 ApiError(工作台据此
// 显示「校验未完成」,不回退假绿)。
import { describe, expect, it, rs } from "@rstest/core";

import { ApiError, assertTaskDocument } from "@/extensions/bid-write/api";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

const calls: Array<{ path: string; init?: RequestInit }> = [];

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    if (path.includes("/tasks/tbad/assert")) {
      return new Response(JSON.stringify({ detail: "ast 根节点 type 必须为 \"doc\"" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({
        states: { "price:R-1": { state: "D0", err_code: "SK-PS-008", message: "行金额失配" } },
        skipped: [{ code: "SK-PS-006", count: 1, reason: "限价未确认" }],
        run_at: "2026-11-14T00:00:00Z",
        results: [],
        summary: { d0: 1, d1: 0, d2: 0, skipped: [] },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  },
}));

const AST = { type: "doc", content: [] } as unknown as AstJsonNode;

describe("assertTaskDocument", () => {
  it("POST 到 /tasks/{id}/assert 并透传 states/skipped", async () => {
    const payload = await assertTaskDocument("t1", { ast: AST });
    const call = calls[calls.length - 1]!;
    expect(call.path).toBe("/api/extensions/bid-write/tasks/t1/assert");
    expect(call.init?.method).toBe("POST");
    const body = call.init?.body;
    expect(typeof body === "string" ? JSON.parse(body) : null).toEqual({ ast: AST });
    expect(payload.states["price:R-1"]?.err_code).toBe("SK-PS-008");
    expect(payload.skipped[0]?.code).toBe("SK-PS-006");
  });

  it("非 2xx 抛 ApiError(保留后端 detail)", async () => {
    await expect(assertTaskDocument("tbad", { ast: AST })).rejects.toBeInstanceOf(ApiError);
    await expect(assertTaskDocument("tbad", { ast: AST })).rejects.toThrow(/ast 根节点/);
  });
});
