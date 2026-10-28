import { describe, expect, it, rs } from "@rstest/core";

import { listTasks } from "@/extensions/bid-review/api";

// 共享 fetcher 的真实导出名是 `fetch`(非计划底稿里的 `fetcher`)——
// @/core/api/fetcher 只导出 fetch/readCsrfCookie/getCsrfHeaders 等,契约返回 Response。
// GET /tasks 的 landed 后端契约(Task 10)= {items: TaskOut[]},listTasks 拆包。
rs.mock("@/core/api/fetcher", () => ({
  fetch: async () =>
    new Response(
      JSON.stringify({
        items: [{ id: "t1", status: "created", mode: "quick" }],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
}));

describe("bid-review api", () => {
  it("lists tasks via shared fetcher", async () => {
    const rows = await listTasks();
    expect(rows).toHaveLength(1);
    expect(rows[0]?.id).toBe("t1");
    expect(rows[0]?.mode).toBe("quick");
  });
});
