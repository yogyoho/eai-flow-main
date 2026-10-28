/**
 * API client for the translation workbench.
 *
 * Endpoints live under `/api/extensions/translation/*`. `authFetch`'s default
 * base is `/api/extensions`, so we pass the `/translation/...` suffix.
 */

import { authFetch, authFormFetch } from "@/extensions/api/client";

import type { TltFolder, TltTask, TltTaskPage, TltUploadResult } from "./types";

const API_BASE = "/translation";
const API_BASE_FULL = "/api/extensions/translation";

export async function listFolders(): Promise<TltFolder[]> {
  const d = await authFetch<{ items: TltFolder[]; total: number }>(
    `${API_BASE}/folders`,
  );
  return d.items;
}

export async function createFolder(
  name: string,
  parentId: string | null,
): Promise<TltFolder> {
  return authFetch<TltFolder>(`${API_BASE}/folders`, {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId }),
  });
}

export async function patchFolder(
  id: string,
  patch: { name?: string; parent_id?: string | null },
): Promise<TltFolder> {
  return authFetch<TltFolder>(`${API_BASE}/folders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteFolder(id: string): Promise<void> {
  await authFetch<{ ok: boolean }>(`${API_BASE}/folders/${id}`, {
    method: "DELETE",
  });
}

export async function listTasks(opts: {
  page?: number;
  page_size?: number;
  folder_id?: string | null; // null=全部；"root"=根
  state?: string;
  kb_id?: string;
  source_lang?: string;
  quality_tier?: string;
  q?: string;
}): Promise<TltTaskPage> {
  const p = new URLSearchParams();
  if (opts.page) p.set("page", String(opts.page));
  if (opts.page_size) p.set("page_size", String(opts.page_size));
  if (opts.folder_id) p.set("folder_id", opts.folder_id);
  if (opts.state) p.set("state", opts.state);
  if (opts.kb_id) p.set("kb_id", opts.kb_id);
  if (opts.source_lang) p.set("source_lang", opts.source_lang);
  if (opts.quality_tier) p.set("quality_tier", opts.quality_tier);
  if (opts.q) p.set("q", opts.q);
  return authFetch<TltTaskPage>(`${API_BASE}/tasks?${p.toString()}`);
}

/** 复核工作台队列：exceeded 任务列表。 */
export async function listReviewQueue(): Promise<TltTask[]> {
  const d = await listTasks({ state: "exceeded", page_size: 200 });
  return d.items;
}

/** 通用状态流转（重跑/取消/复核裁决等，后端校验状态机边）。 */

/** 知识库下拉选项（复用 knowledge 模块列表接口，data-scope 已过滤可见范围）。 */
export async function listKbOptions(): Promise<{ id: string; name: string }[]> {
  // 响应键是 knowledge_bases（KnowledgeBaseListResponse），非 items
  const d = await authFetch<{
    knowledge_bases?: { id: string; name: string }[];
  }>("/knowledge-bases");
  return (d.knowledge_bases ?? []).map((x) => ({ id: x.id, name: x.name }));
}

/** 资产库上传：多文件 + 目标文件夹 + 目标 RAG 库；返回逐文件结果（reused=幂等复用）。 */
export async function uploadAssets(
  folderId: string | null,
  files: File[],
  kbId?: string | null,
): Promise<TltUploadResult[]> {
  const fd = new FormData();
  if (folderId) fd.set("folder_id", folderId);
  if (kbId) fd.set("kb_id", kbId);
  for (const f of files) fd.append("files", f, f.name);
  const d = await authFormFetch<{ items: TltUploadResult[]; count: number }>(
    `${API_BASE}/upload`,
    fd,
  );
  return d.items;
}

/** 通用状态流转（重跑/取消/复核裁决等，后端校验状态机边）。 */
export async function transitionTask(
  taskId: string,
  target: string,
  note?: string,
): Promise<TltTask> {
  return authFetch<TltTask>(`${API_BASE}/tasks/${taskId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target, ...(note ? { note } : {}) }),
  });
}

export interface TaskDraftBlock {
  id: string;
  type: string;
  text: string;
}

export interface TaskDraft {
  state: string;
  source: TaskDraftBlock[];
  translated: TaskDraftBlock[];
  gate_failures: Record<string, string[]> | null;
  uncertainty: { block: string; spans?: string[] }[];
  edited_at: string | null;
  edited_by: string | null;
}

/** 复核对照数据：源文块 + 译文草稿（exceeded 任务）。 */
export async function getTaskDraft(taskId: string): Promise<TaskDraft> {
  return authFetch<TaskDraft>(`${API_BASE}/tasks/${taskId}/draft`);
}

export interface DraftUpdateResult {
  translated: TaskDraftBlock[];
  gate_failures: Record<string, string[]>;
  edited_at: string | null;
}

/** MTPE：保存人工编辑后的译文块（首次编辑保留机器原件）。 */
export async function saveTaskDraft(
  taskId: string,
  blocks: { id: string; text: string }[],
): Promise<DraftUpdateResult> {
  return authFetch<DraftUpdateResult>(`${API_BASE}/tasks/${taskId}/draft`, {
    method: "PUT",
    body: JSON.stringify({ blocks }),
  });
}

export interface BackfillJob {
  id: string;
  total: number;
  chunk_size: number;
  state: string;
}

/** P2 超大回填：创建后台分批入队任务。 */
export async function createBackfillJob(body: {
  task_ids?: string[];
  kb_id?: string;
  folder_id?: string;
  states?: string[];
  chunk_size?: number;
}): Promise<BackfillJob> {
  return authFetch<BackfillJob>(`${API_BASE}/backfill-jobs`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface TaskStats {
  total: number;
  by_state: Record<string, number>;
  delivered: number;
  running: number;
  pending: number;
  exceeded: number;
  skipped: number;
}

export async function getTaskStats(kbId?: string): Promise<TaskStats> {
  const qs = kbId ? `?kb_id=${encodeURIComponent(kbId)}` : "";
  return authFetch<TaskStats>(`${API_BASE}/task-stats${qs}`);
}

/** 资产库拖拽移动（folderId=null 表示根）。 */
export async function moveTaskToFolder(
  taskId: string,
  folderId: string | null,
): Promise<TltTask> {
  return authFetch<TltTask>(`${API_BASE}/tasks/${taskId}/folder`, {
    method: "PATCH",
    body: JSON.stringify({ folder_id: folderId }),
  });
}

/** 「翻译」动作：stored/failed → pending 入队。 */
export async function translateTask(taskId: string): Promise<TltTask> {
  return authFetch<TltTask>(`${API_BASE}/tasks/${taskId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target: "pending" }),
  });
}

/** P1-10: 批量入队（stored/failed → pending，单次 ≤500）。 */
export async function batchTranslateTasks(
  taskIds: string[],
): Promise<{
  queued: number;
  task_ids: string[];
  skipped: { task_id: string; reason: string }[];
}> {
  return authFetch(`${API_BASE}/tasks/batch-translate`, {
    method: "POST",
    body: JSON.stringify({ task_ids: taskIds }),
  });
}

/** 库删除：→ archived（归档可救）。 */
export async function deleteTask(taskId: string): Promise<void> {
  await authFetch<{ ok: boolean }>(`${API_BASE}/tasks/${taskId}`, {
    method: "DELETE",
  });
}

/** 译本预览（Markdown 文本）。tlt 元数据头仅在文件内承载溯源，展示层剥离。 */
export async function fetchDeliverablePreview(taskId: string): Promise<string> {
  // Markdown 原文：走 credentials fetch 直取文本（authFetch 默认解析 JSON）
  const resp = await fetch(
    `${API_BASE_FULL}/tasks/${taskId}/deliverable/preview`,
    {
      credentials: "include",
    },
  );
  if (!resp.ok) throw new Error(`预览加载失败（${resp.status}）`);
  const text = await resp.text();
  // 剥离 tlt 元数据注释头（<!-- tlt:translated-document ... -->），仅展示正文
  return text.replace(/^<!--\s*tlt:translated-document[\s\S]*?-->\s*/, "");
}

/** RAG 知识库配置（多库）：配置真源在 RAGFlow，PG 只存映射摘要。 */
export interface RagKb {
  id: string;
  name: string;
  description: string | null;
  language: string | null;
  permission: string | null;
  chunk_method: string | null;
  embedding_model: string | null;
  parser_config: Record<string, unknown> | null;
  pagerank: number | null;
  ragflow_linked: boolean;
  ragflow_dataset_id: string | null;
  doc_count: number;
  pending_count: number;
}

export async function listRagKbs(): Promise<RagKb[]> {
  const d = await authFetch<{ items: RagKb[]; total: number }>(
    `${API_BASE}/rag-kbs`,
  );
  return d.items ?? [];
}

/** 翻译模型选择（与对话模型独立；全局设置）。 */
export interface TranslationModelOption {
  name: string;
  display_name: string;
}

export interface TranslationModelSettings {
  items: TranslationModelOption[];
  setting: string | null;
  effective: string | null;
}

export async function getTranslationModelSettings(): Promise<TranslationModelSettings> {
  return authFetch<TranslationModelSettings>(`${API_BASE}/models`);
}

export async function updateTranslationModel(
  translationModel: string | null,
): Promise<{ setting: string | null; effective: string | null }> {
  return authFetch(`${API_BASE}/models`, {
    method: "PUT",
    body: JSON.stringify({ translation_model: translationModel }),
  });
}

export async function listEmbeddingModels(): Promise<string[]> {
  const d = await authFetch<{ items: string[] }>(
    `${API_BASE}/rag-kbs/embedding-models`,
  );
  return d.items ?? [];
}

export interface RagKbPayload {
  name?: string;
  description?: string | null;
  language?: string | null;
  permission?: string | null;
  embedding_model?: string | null;
  chunk_method?: string | null;
  parser_config?: Record<string, unknown> | null;
  pagerank?: number | null;
}

export async function createRagKb(body: RagKbPayload): Promise<{ id: string }> {
  return authFetch<{ id: string }>(`${API_BASE}/rag-kbs`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateRagKb(
  kbId: string,
  body: RagKbPayload,
): Promise<{ ok: boolean }> {
  return authFetch<{ ok: boolean }>(`${API_BASE}/rag-kbs/${kbId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function setRagKbEnabled(
  kbId: string,
  enabled: boolean,
): Promise<{ ok: boolean }> {
  return authFetch<{ ok: boolean }>(`${API_BASE}/rag-kbs/${kbId}/enabled`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

// ── 术语库（语言维度 + Excel 导入，EAI-CUSTOM 2026-10-18）──────────────

export type GlossaryLang = "en" | "fr" | "any";
export type GlossaryAction = "force" | "forbid" | "keep";

export interface GlossaryEntry {
  source: string;
  lang: GlossaryLang;
  action: GlossaryAction;
  target: string | null;
  domains: string[];
  notes: string | null;
}

export interface GlossaryResponse {
  entries: GlossaryEntry[];
  count: number;
  version: string;
}

export type GlossaryImportStatus = "add" | "update" | "unchanged" | "invalid";

export interface GlossaryImportRow {
  row: number;
  source: string;
  lang: string;
  action: string;
  target: string | null;
  domains: string[];
  notes: string | null;
  status: GlossaryImportStatus;
  errors: string[];
}

export interface GlossaryImportPreview {
  version: string;
  rows: GlossaryImportRow[];
  summary: Record<string, number>;
  merged_entries: GlossaryEntry[];
}

export async function getGlossary(): Promise<GlossaryResponse> {
  return authFetch<GlossaryResponse>(`${API_BASE}/glossary`);
}

/** 全表保存；baseVersion 不匹配时后端返回 409。 */
export async function putGlossary(
  entries: GlossaryEntry[],
  baseVersion?: string,
): Promise<GlossaryResponse> {
  return authFetch<GlossaryResponse>(`${API_BASE}/glossary`, {
    method: "PUT",
    body: JSON.stringify({ entries, base_version: baseVersion }),
  });
}

/** 上传 Excel/CSV 解析为预览（不落盘）；确认后走 putGlossary。 */
export async function importGlossary(
  file: File,
): Promise<GlossaryImportPreview> {
  const form = new FormData();
  form.append("file", file);
  return authFormFetch<GlossaryImportPreview>(
    `${API_BASE}/glossary/import`,
    form,
  );
}
