import { describe, expect, it, rs } from "@rstest/core";

import { createTask, listTasks } from "@/extensions/bid-review/api";

// 共享 fetcher 的真实导出名是 `fetch`(非计划底稿里的 `fetcher`)——
// @/core/api/fetcher 只导出 fetch/readCsrfCookie/getCsrfHeaders 等,契约返回 Response。
// landed 后端契约(Task 10):GET /tasks = {items: TaskOut[]},listTasks 拆包;
// POST /tasks = multipart(mode + tender_files/bid_files 重复字段 → FastAPI
// list[UploadFile])。Task 12 修复轮起 createTask 必传文件——后端 _enqueue_docs
// 对零材料任务也无条件直推空跑,无文件路径只剩 MCP bid_review_start。
const calls: Array<{ path: string; init?: RequestInit }> = [];

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    const body =
      init?.method === "POST"
        ? { id: "t2", status: "created", mode: "quick" }
        : { items: [{ id: "t1", status: "created", mode: "quick" }] };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
}));

describe("bid-review api", () => {
  it("lists tasks via shared fetcher and unwraps {items}", async () => {
    const rows = await listTasks();
    expect(rows).toHaveLength(1);
    expect(rows[0]?.id).toBe("t1");
    expect(rows[0]?.mode).toBe("quick");
    expect(calls[calls.length - 1]?.path).toBe(
      "/api/extensions/bid-review/tasks",
    );
  });

  it("createTask posts multipart with mode + tender_files/bid_files", async () => {
    const tender = new File(["tender text"], "tender.txt", {
      type: "text/plain",
    });
    const bid = new File(["bid text"], "bid.txt", { type: "text/plain" });
    const task = await createTask("quick", { tender: [tender], bid: [bid] });
    expect(task.id).toBe("t2");
    const last = calls[calls.length - 1];
    expect(last?.path).toBe("/api/extensions/bid-review/tasks");
    expect(last?.init?.method).toBe("POST");
    const form = last?.init?.body;
    expect(form).toBeInstanceOf(FormData);
    const fd = form as FormData;
    expect(fd.get("mode")).toBe("quick");
    expect(fd.getAll("tender_files")).toEqual([tender]);
    expect(fd.getAll("bid_files")).toEqual([bid]);
  });
});
