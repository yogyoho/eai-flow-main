import { describe, expect, it, rs } from "@rstest/core";

import {
  ApiError,
  createTask,
  exportReport,
  listTasks,
} from "@/extensions/bid-review/api";

// 共享 fetcher 的真实导出名是 `fetch`(非计划底稿里的 `fetcher`)——
// @/core/api/fetcher 只导出 fetch/readCsrfCookie/getCsrfHeaders 等,契约返回 Response。
// landed 后端契约(Task 10):GET /tasks = {items: TaskOut[]},listTasks 拆包;
// POST /tasks = multipart(mode + tender_files/bid_files 重复字段 → FastAPI
// list[UploadFile])。Task 12 修复轮起 createTask 必传文件——后端 _enqueue_docs
// 对零材料任务也无条件直推空跑,无文件路径只剩 MCP bid_review_start。
// Task 21:GET /tasks/{id}/report?format=md 返回 text/markdown(非 JSON)→
// exportReport 走 Blob;非 2xx 仍抛 ApiError(带 status + 后端 detail)。
const calls: Array<{ path: string; init?: RequestInit }> = [];

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    if (path.includes("/report")) {
      if (path.includes("/tasks/tbad/")) {
        return new Response(
          JSON.stringify({ detail: "format 仅支持 md(html 导出属 M4)" }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("# 投标审查报告\n", {
        status: 200,
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
      });
    }
    const body =
      init?.method === "POST"
        ? { id: "t2", status: "created", mode: "quick" }
        : {
            items: [
              {
                id: "t1",
                status: "created",
                mode: "quick",
                fatal_unhandled: 2,
                need_human_count: 1,
              },
            ],
          };
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

  it("listTasks keeps per-task issue count fields (micro-A 拆包+字段契约门)", async () => {
    // GET /tasks 每任务聚合字段(micro-A 2026-10-29)经拆包原样透传,TasksView 直接消费
    const rows = await listTasks();
    expect(rows[0]?.fatal_unhandled).toBe(2);
    expect(rows[0]?.need_human_count).toBe(1);
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

  it("exportReport fetches ?format=md and returns the markdown Blob", async () => {
    const blob = await exportReport("t1");
    expect(blob).toBeInstanceOf(Blob);
    expect(await blob.text()).toContain("# 投标审查报告");
    const last = calls[calls.length - 1];
    expect(last?.path).toBe(
      "/api/extensions/bid-review/tasks/t1/report?format=md",
    );
  });

  it("exportReport surfaces backend detail as ApiError on non-2xx", async () => {
    let err: unknown;
    try {
      await exportReport("tbad");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.message).toBe("format 仅支持 md(html 导出属 M4)");
  });
});
