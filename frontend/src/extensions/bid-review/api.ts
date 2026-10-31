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
export type FeedbackAction =
  | "confirm"
  | "false_positive"
  | "severity_change"
  | "need_human";

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
  /** 判定输入字段路径(routers 2026-10-30 起回传);det 规则 issue 无 doc/page 证据时前端回退展示。 */
  inputs?: string[];
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
 * PDF/Word 结构化解析缺口见 routers.create_task 注释)。
 * identity(裁定12+14,Plan5):可选身份覆盖位;空白不 append,留空=引擎抽取回填位。 */
export function createTask(
  mode: "quick" | "deep",
  files: { tender: File[]; bid: File[] },
  identity?: { project_name?: string | null; lot_name?: string | null; tender_no?: string | null },
): Promise<TaskOut> {
  const form = new FormData();
  form.set("mode", mode);
  if (identity?.project_name?.trim()) form.set("project_name", identity.project_name.trim());
  if (identity?.lot_name?.trim()) form.set("lot_name", identity.lot_name.trim());
  if (identity?.tender_no?.trim()) form.set("tender_no", identity.tender_no.trim());
  for (const f of files.tender) form.append("tender_files", f);
  for (const f of files.bid) form.append("bid_files", f);
  return request<TaskOut>("/tasks", { method: "POST", body: form });
}

/** GET /tasks/{id} —— 任务详情(含 progress / engine_meta)。 */
export function getTask(taskId: string): Promise<TaskOut> {
  return request<TaskOut>(`/tasks/${taskId}`);
}

/** GET /tasks/{id}/confirm —— 确认门(仅 UI):基线全量翻转 confirmed;
 * awaiting_confirm 状态后台续跑。确认前存在未复核致命项时后端收紧(计划 Task 15)
 * 将回 409,调用方按 ApiError.status 分流 toast(spec §3.2)。 */
export function confirmTask(taskId: string): Promise<TaskOut> {
  return request<TaskOut>(`/tasks/${taskId}/confirm`, { method: "POST" });
}

// ── 基线读端点(EAI-CUSTOM 2026-10-30 分期建议一期 s3/s4)─────────────

/** GET /tasks/{id}/baselines 行:_write_baselines 落库形——每行同全量 fields
 * 快照 + 本行 doc_id;provenance 逐字段出处 {doc_id,page,quote}(模型没给的
 * 路径缺省不造假)。EAI-CUSTOM 2026-10-31 二期(spec §1.3):candidates 多候选 /
 * fields_conf 置信 / conflicts 冲突路径 / effective_fields(裁定覆盖后)。 */
export interface BidCandidate {
  value: unknown;
  doc_id: string;
  page: number | null;
  quote: string;
}

export interface BidFieldConf {
  conf: number | null;
  verified: boolean;
}

export interface BidBaselineRow {
  kind: string;
  doc_id: string | null;
  confirmed: boolean;
  created_at: string | null;
  fields: Record<string, unknown>;
  provenance: Record<
    string,
    { doc_id: string; page: number | null; quote: string }
  >;
  candidates: Record<string, BidCandidate[]>;
  fields_conf: Record<string, BidFieldConf>;
  conflicts: string[];
  effective_fields: Record<string, unknown>;
  materials_hash: string;
}

/** GET /tasks/{id}/baselines 响应:行数组 + 顶层 labels(中文名映射)+
 * adjudications(engine_meta 裁定 {path: {value, at, note?}})。 */
export interface BidBaselinesOut {
  items: BidBaselineRow[];
  labels: Record<string, string>;
  adjudications: Record<string, { value: unknown; at: string; note?: string }>;
}

/** GET /tasks/{id}/baselines —— 基线行级读端点(行 + labels + 裁定)。 */
export function fetchBaselines(taskId: string): Promise<BidBaselinesOut> {
  return request<BidBaselinesOut>(`/tasks/${taskId}/baselines`);
}

/** POST /tasks/{id}/baselines/adjudicate —— 冲突裁定(EAI-CUSTOM 2026-10-31
 * 二期 spec §1.3):仅 awaiting_confirm 可裁定(过门 409);返回更新投影。 */
export function adjudicateBaseline(
  taskId: string,
  body: { path: string; value: unknown; note?: string },
): Promise<BidBaselinesOut> {
  return request<BidBaselinesOut>(`/tasks/${taskId}/baselines/adjudicate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
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

// ── 文档溯源取数(EAI-CUSTOM 2026-10-30,spec D6/D8)──────────────────

/** 定位原文弹层目标(WorkbenchView 证据 chip → DocLocateModal)。 */
export interface LocateTarget {
  docId: string;
  /** pdf 真页码;docx 无页码 null → 后端走 quote 片段窗口(D8 诚实降级)。 */
  page: number | null;
  quote: string;
}

/** GET /tasks/{id}/docs/{doc_id}/content 响应段(只回命中页/±10段窗口,整本不回传)。 */
export interface BidDocSegment {
  seq: number;
  page: number | null;
  kind: "text" | "table" | "ocr";
  text: string;
  asset_id: string | null;
}

export interface BidDocContent {
  doc: {
    doc_id: string;
    role: string;
    kind: string;
    pages: number;
    chars: number;
    assets: number;
    status: string;
  };
  page: number | null;
  seq: number | null;
  segments: BidDocSegment[];
}

/** GET /tasks/{id}/docs/{doc_id}/content?quote=|page= —— 溯源定位窗口(docx 走 quote
 * 片段命中 ±10 段;pdf 优先 page 整页)。404 = 未定位到原文(调用方如实呈现)。 */
export function fetchDocContent(
  taskId: string,
  docId: string,
  params: { quote?: string; page?: number },
): Promise<BidDocContent> {
  const q = new URLSearchParams();
  if (params.quote) q.set("quote", params.quote);
  if (params.page != null) q.set("page", String(params.page));
  const qs = q.toString();
  return request<BidDocContent>(
    `/tasks/${taskId}/docs/${encodeURIComponent(docId)}/content${qs ? `?${qs}` : ""}`,
  );
}

/** GET /tasks/{id}/docs/{doc_id}/assets/{asset_id} —— 原图 URL(直接喂 <img src>;
 * cookie 鉴权走同源 fetch 不适用于 <img>,资产端点本身在 owner 过滤下放行)。 */
export function docAssetUrl(
  taskId: string,
  docId: string,
  assetId: string,
): string {
  return `${API_BASE}/tasks/${taskId}/docs/${encodeURIComponent(docId)}/assets/${encodeURIComponent(assetId)}`;
}
