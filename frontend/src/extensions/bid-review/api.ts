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

/** POST /tasks —— 新建审查任务(landed 后端唯一文档入口=multipart Form:tender_files /
 * bid_files 重复字段 → FastAPI list[UploadFile];后端 _enqueue_docs 对零材料任务也无条件
 * 直推空跑,故 UI 必传文件——Task 12 修复轮决定 (b),M3 工作台上传=补充/重传文档)。
 * v1 后端将文件按 UTF-8 纯文本解码落 engine_meta.docs(.txt/.md 等文本格式最适配;
 * PDF/Word 结构化解析缺口见 routers.create_task 注释)。 */
export function createTask(
  mode: "quick" | "deep",
  files: { tender: File[]; bid: File[] },
): Promise<TaskOut> {
  const form = new FormData();
  form.set("mode", mode);
  for (const f of files.tender) form.append("tender_files", f);
  for (const f of files.bid) form.append("bid_files", f);
  return request<TaskOut>("/tasks", { method: "POST", body: form });
}
