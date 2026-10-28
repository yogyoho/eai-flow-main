/**
 * API client for the bid-review extension.
 *
 * Endpoints live under `/api/extensions/bid-review/*`(Gateway;routers.py
 * Task 10:POST /tasks / GET /tasks / GET /tasks/{id} / POST /tasks/{id}/confirm /
 * GET /tasks/{id}/issues / GET /issues/{id} / POST /issues/{id}/feedback / GET /rulepacks)。
 * Fetch 走共享 `@/core/api/fetcher` 的 `fetch`(导出名是 fetch,非 authFetch):
 * 自动 credentials: "include" + 状态变更方法注入 X-CSRF-Token + 401 跳登录。
 */

import { fetch } from "@/core/api/fetcher";

import type { TaskOut } from "./types";

const API_BASE = "/api/extensions/bid-review";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let message = `请求失败(${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // 非 JSON 错误体,保留默认 message
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

/** GET /tasks —— 任务列表(owner 过滤由后端完成;响应 {items: TaskOut[]},拆包返回)。 */
export function listTasks(): Promise<TaskOut[]> {
  return request<{ items: TaskOut[] }>("/tasks").then((r) => r.items);
}

/** POST /tasks —— 新建审查任务(landed 后端契约=multipart Form;UI 文件上传 M3 补,
 * 无文件版先建任务,文档经对话/MCP 编排补传)。 */
export function createTask(mode: "quick" | "deep"): Promise<TaskOut> {
  const form = new FormData();
  form.set("mode", mode);
  return request<TaskOut>("/tasks", { method: "POST", body: form });
}
