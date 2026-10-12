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
  q?: string;
}): Promise<TltTaskPage> {
  const p = new URLSearchParams();
  if (opts.page) p.set("page", String(opts.page));
  if (opts.page_size) p.set("page_size", String(opts.page_size));
  if (opts.folder_id) p.set("folder_id", opts.folder_id);
  if (opts.state) p.set("state", opts.state);
  if (opts.q) p.set("q", opts.q);
  return authFetch<TltTaskPage>(`${API_BASE}/tasks?${p.toString()}`);
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

/** 译本预览（Markdown 文本）。 */
export async function fetchDeliverablePreview(taskId: string): Promise<string> {
  // Markdown 原文：走 credentials fetch 直取文本（authFetch 默认解析 JSON）
  const resp = await fetch(`${API_BASE_FULL}/tasks/${taskId}/deliverable/preview`, {
    credentials: "include",
  });
  if (!resp.ok) throw new Error(`预览加载失败（${resp.status}）`);
  return resp.text();
}
