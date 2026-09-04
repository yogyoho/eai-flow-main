/**
 * API client for the geo-sample-bank management API.
 *
 * Endpoints live under `/api/extensions/geo-samples/*` (mounted in the
 * Gateway). `authFetch`'s default base is `/api/extensions`, so we pass the
 * `/geo-samples/...` suffix.
 */

// EAI-CUSTOM: forked from extensions/contract-price/api.ts (geo-sample-bank Phase 1, spec 2026-09-01).
import { authFetch, authFormFetch } from "@/extensions/api/client";

import type {
  GsbDocument,
  GsbOrePackApproveResult,
  GsbOrePackDraft,
  GsbRedaction,
  GsbRun,
} from "./types";

const API_BASE = "/geo-samples";

/** Build a query string, skipping empty/null/undefined values. */
export function qs(
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const geoSamplesApi = {
  // Functional area 1: documents
  listDocuments: (params?: {
    stage?: string;
    mineral?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }) =>
    authFetch<{
      items: GsbDocument[];
      skip: number;
      limit: number;
      total: number;
    }>(`${API_BASE}/documents${qs(params)}`),

  getDocument: (id: string) =>
    authFetch<GsbDocument>(`${API_BASE}/documents/${id}`),

  uploadDocument: (form: FormData) =>
    // run_id 可选（batch-cli P4 T1）：服务端 defer_parse=true 时响应省略 run_id 键
    authFormFetch<{ document: GsbDocument; run_id?: string }>(
      `${API_BASE}/documents/upload`,
      form,
    ),

  deleteDocument: (id: string) =>
    authFetch<{ deleted: boolean; report_id: string }>(
      `${API_BASE}/documents/${id}`,
      { method: "DELETE" },
    ),

  // 题名 → 结构化 report_id 建议（batch-cli T7, spec 2026-09-03）。后端为 POST
  // ?title=Query(...)，authFetch 不带 method 默认走 GET → 必须显式 POST（且 CSRF 头仅对
  // 显式 state-changing method 附加）。
  suggestId: (title: string) =>
    authFetch<{
      report_id: string;
      stage: string | null;
      mineral: string | null;
      region: string | null;
      confidence: "auto" | "needs-review";
    }>(`${API_BASE}/documents/suggest-id?title=${encodeURIComponent(title)}`, {
      method: "POST",
    }),

  // Functional area 2: parse / redact pipeline
  parse: (id: string) =>
    authFetch<{ run_id: string }>(`${API_BASE}/documents/${id}/parse`, {
      method: "POST",
    }),

  redact: (id: string) =>
    authFetch<{ run_id: string }>(`${API_BASE}/documents/${id}/redact`, {
      method: "POST",
    }),

  // Functional area 3: review
  review: (
    id: string,
    body: { decision: "approve" | "reject"; note: string | null },
  ) =>
    authFetch<GsbDocument>(`${API_BASE}/documents/${id}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRedactions: (id: string) =>
    authFetch<{ items: GsbRedaction[] }>(
      `${API_BASE}/documents/${id}/redactions`,
    ),

  // Functional area 4: tasks
  listRuns: () => authFetch<{ items: GsbRun[] }>(`${API_BASE}/runs`),

  // 模块级编译（Phase 2）：reviewed 清单（可带 stage/mineral 过滤）→ 子进程 bank_compile
  // 切片落 references + RAGFlow 分发（后台 run，进度见 /runs）。POST 缺省会走 GET 405，必须显式。
  compile: (params?: { stage?: string; mineral?: string }) =>
    authFetch<{ run_id: string }>(`${API_BASE}/pipeline/compile${qs(params)}`, {
      method: "POST",
    }),

  // Functional area 6: ore_pack incubation（P5 T5 端点）。approve/reject 为 POST + JSON body
  // （note 可空）；approve 响应附加 written 落盘路径 + standards_index 扩容义务清单。
  listDrafts: (params?: { mineral?: string; review_status?: string }) =>
    authFetch<{ items: GsbOrePackDraft[] }>(
      `${API_BASE}/ore-packs/drafts${qs(params)}`,
    ),

  extractOrePack: (body: { mineral: string; slice_paths: string[] }) =>
    authFetch<{ queued: boolean; mineral: string; slices_hash: string }>(
      `${API_BASE}/ore-packs/extract`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  approveDraft: (id: string, note: string | null) =>
    authFetch<GsbOrePackApproveResult>(
      `${API_BASE}/ore-packs/drafts/${id}/approve`,
      { method: "POST", body: JSON.stringify({ note }) },
    ),

  rejectDraft: (id: string, note: string | null) =>
    authFetch<GsbOrePackDraft>(`${API_BASE}/ore-packs/drafts/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
};
