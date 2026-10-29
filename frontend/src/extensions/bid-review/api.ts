/**
 * API client for the bid-review extension.
 *
 * Endpoints live under `/api/extensions/bid-review/*`(Gateway;routers.py
 * Task 10:POST /tasks / GET /tasks / GET /tasks/{id} / POST /tasks/{id}/confirm /
 * GET /tasks/{id}/issues / GET /issues/{id} / POST /issues/{id}/feedback / GET /rulepacks;
 * Task 21:GET /tasks/{id}/report?format=md Blob 导出)。
 * Fetch 走共享 `@/core/api/fetcher` 的 `fetch`(导出名是 fetch,非 authFetch):
 * 自动 credentials: "include" + 状态变更方法注入 X-CSRF-Token + 401 跳登录。
 * Task 17:补 issues/feedback/confirm/rulepacks 调用;非 2xx 抛 {@link ApiError}
 * (携带 status,确认门 409 → toast 分流用,spec §3.2)。
 */

import { fetch } from "@/core/api/fetcher";

import type { IssueOut, TaskOut } from "./types";

const API_BASE = "/api/extensions/bid-review";

/** 非 2xx 响应:message 取后端 detail;status 供调用方分流(409 确认门等)。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestRaw(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let message = `请求失败(${res.status})`;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // 非 JSON 错误体,保留默认 message
    }
    throw new ApiError(message, res.status);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestRaw(path, init).then((r) => r.json())) as T;
}

// ── 类型(landed 后端契约;types.ts 不在本任务允许清单,规则库契约类型落此)──

/** POST /issues/{id}/feedback 请求体(backend FeedbackIn)。 */
export type FeedbackAction = "confirm" | "false_positive" | "severity_change";

export interface FeedbackBody {
  action: FeedbackAction;
  /** action=severity_change 时必填(fatal|major|minor|info,routers 422 校验)。 */
  new_severity?: string;
  note?: string;
}

/** GET /rulepacks 行(rules 数组元素)。 */
export interface RulePackRule {
  id: string;
  name: string;
  layer: string;
  severity: string;
  type: string;
}

/** GET /rulepacks 条目:生产规则包 + DB stats 覆盖(routers.list_rulepacks)。 */
export interface RulePackOut {
  name: string;
  version: string;
  rule_count: number;
  rules: RulePackRule[];
  /** rule_id → {hit, fp, adopted} 计数(crud.add_rulepack_stats 回流)。 */
  stats: Record<string, { hit?: number; fp?: number; adopted?: number }>;
  enabled: boolean;
}

// ── 任务端点 ──────────────────────────────────────────────────────────

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

/** GET /tasks/{id} —— 任务详情(含 progress / engine_meta)。 */
export function getTask(taskId: string): Promise<TaskOut> {
  return request<TaskOut>(`/tasks/${taskId}`);
}

/** POST /tasks/{id}/confirm —— 确认门(仅 UI):基线全量翻转 confirmed;
 * awaiting_confirm 状态后台续跑。确认前存在未复核致命项时后端收紧(计划 Task 15)
 * 将回 409,调用方按 ApiError.status 分流 toast(spec §3.2)。 */
export function confirmTask(taskId: string): Promise<TaskOut> {
  return request<TaskOut>(`/tasks/${taskId}/confirm`, { method: "POST" });
}

// ── 问题端点 ──────────────────────────────────────────────────────────

/** GET /tasks/{id}/issues —— 任务问题列表({items: IssueOut[]},拆包返回)。 */
export function listTaskIssues(taskId: string): Promise<IssueOut[]> {
  return request<{ items: IssueOut[] }>(`/tasks/${taskId}/issues`).then(
    (r) => r.items,
  );
}

/** POST /issues/{id}/feedback —— 复核三连(confirm/false_positive/severity_change;
 * 返回复核后的 IssueOut)。误报/认可回流 RulePackMeta.stats(后端 routers.feedback_issue)。 */
export function feedbackIssue(
  issueId: string,
  body: FeedbackBody,
): Promise<IssueOut> {
  return request<IssueOut>(`/issues/${issueId}/feedback`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── 规则包端点 ────────────────────────────────────────────────────────

/** GET /rulepacks —— 规则包清单({items: RulePackOut[]},拆包返回)。 */
export function listRulepacks(): Promise<RulePackOut[]> {
  return request<{ items: RulePackOut[] }>("/rulepacks").then((r) => r.items);
}

// ── 报告导出(Task 21)────────────────────────────────────────────────

/** GET /tasks/{id}/report?format=md —— 审查报告导出,返回 Blob(text/markdown;
 * 首行免责声明+可提交判定提示行+severity 分节,内容契约由后端渲染)。html 导出属
 * M4,后端 422 → 走 {@link ApiError} 分支。调用方经 URL.createObjectURL + <a
 * download> 触发浏览器保存(WorkbenchView 导出按钮)。 */
export function exportReport(taskId: string): Promise<Blob> {
  return requestRaw(`/tasks/${taskId}/report?format=md`).then((r) => r.blob());
}
