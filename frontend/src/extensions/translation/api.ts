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
  const d = await authFetch<{ items: TltFolder[]; total: number }>(`${API_BASE}/folders`);
  return d.items;
}

export async function createFolder(name: string, parentId: string | null): Promise<TltFolder> {
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
  await authFetch<{ ok: boolean }>(`${API_BASE}/folders/${id}`, { method: "DELETE" });
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

/** 通用状态流转（重跑/取消/复核裁决等，后端校验状态机边）。 */

/** 知识库下拉选项（复用 knowledge 模块列表接口，data-scope 已过滤可见范围）。 */
export async function listKbOptions(): Promise<{ id: string; name: string }[]> {
  const d = await authFetch<{ items: { id: string; name: string }[] }>("/knowledge-bases");
  return d.items.map((x) => ({ id: x.id, name: x.name }));
}

/** 资产库上传：多文件 + 目标文件夹；返回逐文件结果（reused=幂等复用）。 */
export async function uploadAssets(folderId: string | null, files: File[]): Promise<TltUploadResult[]> {
  const fd = new FormData();
  if (folderId) fd.set("folder_id", folderId);
  for (const f of files) fd.append("files", f, f.name);
  const d = await authFormFetch<{ items: TltUploadResult[]; count: number }>(
    `${API_BASE}/upload`,
    fd,
  );
  return d.items;
}

/** 通用状态流转（重跑/取消/复核裁决等，后端校验状态机边）。 */
export async function transitionTask(taskId: string, target: string): Promise<TltTask> {
  return authFetch<TltTask>(`${API_BASE}/tasks/${taskId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target }),
  });
}

/** 「翻译」动作：stored/failed → pending 入队。 */
export async function translateTask(taskId: string): Promise<TltTask> {
  return authFetch<TltTask>(`${API_BASE}/tasks/${taskId}/transition`, {
    method: "POST",
    body: JSON.stringify({ target: "pending" }),
  });
}

/** 库删除：→ archived（归档可救）。 */
export async function deleteTask(taskId: string): Promise<void> {
  await authFetch<{ ok: boolean }>(`${API_BASE}/tasks/${taskId}`, { method: "DELETE" });
}

/** 译本预览（Markdown 文本）。tlt 元数据头仅在文件内承载溯源，展示层剥离。 */
export async function fetchDeliverablePreview(taskId: string): Promise<string> {
  // Markdown 原文：走 credentials fetch 直取文本（authFetch 默认解析 JSON）
  const resp = await fetch(`${API_BASE_FULL}/tasks/${taskId}/deliverable/preview`, {
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`预览加载失败（${resp.status}）`);
  const text = await resp.text();
  // 剥离 tlt 元数据注释头（<!-- tlt:translated-document ... -->），仅展示正文
  return text.replace(/^<!--\s*tlt:translated-document[\s\S]*?-->\s*/, "");
}
