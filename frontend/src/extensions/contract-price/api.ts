/**
 * API client for the contract-price-analysis management API.
 *
 * Endpoints live under `/api/extensions/contract-price/*` (mounted in the
 * Gateway). `authFetch`'s default base is `/api/extensions`, so we pass the
 * `/contract-price/...` suffix.
 */

import { authFetch, authFormFetch } from "@/extensions/api/client";

import type {
  CpaCluster,
  CpaClusterDetail,
  CpaConfig,
  CpaDashboard,
  CpaDocument,
  CpaItem,
  CpaRun,
  EvolutionCandidate,
  Page,
  PipelineRunResponse,
  PipelineStatus,
  UploadResponse,
} from "./types";

const API_BASE = "/contract-price";
/** Full path for non-JSON GETs the browser issues directly (e.g. <img src>). */
const FULL_BASE = "/api/extensions/contract-price";

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

export const contractPriceApi = {
  // Functional area 6: dashboard
  dashboard: () => authFetch<CpaDashboard>(`${API_BASE}/dashboard`),

  // Cross-contract goods analysis
  goodsAnalysis: (params: {
    name?: string;
    cluster_id?: string;
    skip?: number;
    limit?: number;
  }) =>
    authFetch<Record<string, unknown>>(
      `${API_BASE}/contract-price-analysis${qs(params)}`,
    ),

  // Functional area 1: documents
  listDocuments: (params?: {
    keyword?: string;
    parse_status?: string;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CpaDocument>>(`${API_BASE}/documents${qs(params)}`),

  deleteDocument: (id: string) =>
    authFetch<void>(`${API_BASE}/documents/${id}`, { method: "DELETE" }),

  // reOcr=false 走 OCR 缓存(秒级);true 强制重 OCR。必须始终带值——
  // 空值 `?re_ocr=` 会被 FastAPI 拒以 422。
  reparseDocument: (id: string, reOcr = false) =>
    authFetch<{ run_id: string; status: string; message?: string }>(
      `${API_BASE}/documents/${id}/reparse?re_ocr=${reOcr}`,
      { method: "POST" },
    ),

  updateDocument: (
    id: string,
    body: Partial<
      Pick<
        CpaDocument,
        | "project_name"
        | "project_location"
        | "project_no"
        | "contract_no"
        | "supplier"
        | "sign_date"
      >
    >,
  ) =>
    authFetch<CpaDocument>(`${API_BASE}/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  confirmDocument: (id: string, confirm_status: "confirmed" | "skipped") =>
    authFetch<CpaDocument>(`${API_BASE}/documents/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirm_status }),
    }),

  confirmAllDocuments: (confirm_status: "confirmed" | "skipped") =>
    authFetch<{ updated: number; confirm_status: string }>(
      `${API_BASE}/documents/confirm-all`,
      {
        method: "POST",
        body: JSON.stringify({ confirm_status }),
      },
    ),

  runCluster: (mode = "table", trigger = "manual") =>
    authFetch<PipelineRunResponse>(`${API_BASE}/cluster/run`, {
      method: "POST",
      body: JSON.stringify({ mode, trigger }),
    }),

  uploadDocument: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return authFormFetch<UploadResponse>(`${API_BASE}/documents/upload`, fd);
  },

  /** URL for an <img> overlaying a bbox on the page preview PNG. */
  previewUrl: (docId: string, page: number) =>
    `${FULL_BASE}/documents/${docId}/preview/${page}`,

  /** URL for the original-file download (<a href>, same-origin cookie auth;
   * server streams the PDF/DOCX with Content-Disposition attachment). */
  fileUrl: (docId: string) => `${FULL_BASE}/documents/${docId}/file`,

  /** URL for inline browser rendering of the original file (?inline=1 →
   * Content-Disposition inline; used by the <iframe> native PDF viewer). */
  fileInlineUrl: (docId: string) =>
    `${FULL_BASE}/documents/${docId}/file?inline=1`,

  // Functional area 2: clusters
  listClusters: (params?: {
    cluster_status?: string;
    category?: string;
    keyword?: string;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CpaCluster>>(`${API_BASE}/clusters${qs(params)}`),

  getCluster: (id: string) =>
    authFetch<CpaClusterDetail>(`${API_BASE}/clusters/${id}`),

  confirmCluster: (
    id: string,
    body?: { confirmed_by?: string; expected_version?: number },
  ) =>
    authFetch<{ status: string; version: number }>(
      `${API_BASE}/clusters/${id}/confirm`,
      {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      },
    ),

  rejectCluster: (id: string, body?: { expected_version?: number }) =>
    authFetch<{ status: string; version: number }>(
      `${API_BASE}/clusters/${id}/reject`,
      {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      },
    ),

  updateCluster: (
    id: string,
    body: { category?: string; representative_name?: string },
  ) =>
    authFetch<CpaCluster>(`${API_BASE}/clusters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  mergeClusters: (
    cluster_ids: string[],
    representative_name: string,
    category?: string,
  ) =>
    authFetch<{ cluster_id: string; item_count: number }>(
      `${API_BASE}/clusters/merge`,
      {
        method: "POST",
        body: JSON.stringify({ cluster_ids, representative_name, category }),
      },
    ),

  moveItem: (item_id: string, target_cluster_id: string) =>
    authFetch<{ item_id: string; cluster_id: string }>(
      `${API_BASE}/items/${item_id}/move`,
      {
        method: "POST",
        body: JSON.stringify({ target_cluster_id }),
      },
    ),

  // Functional area 3: items
  listItemContracts: () =>
    authFetch<{ source_contract_no: string; count: number }[]>(
      `${API_BASE}/items/contracts`,
    ),

  listItems: (params?: {
    goods_name?: string;
    source_contract_no?: string;
    cluster_id?: string;
    run_id?: string;
    only_outliers?: boolean;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CpaItem>>(`${API_BASE}/items${qs(params)}`),

  updateItem: (
    id: string,
    body: {
      unit_price?: number;
      tech_params?: Record<string, string>;
      goods_name?: string;
      spec_model?: string;
      validation_status?: string;
      note?: string;
    },
  ) =>
    authFetch<CpaItem>(`${API_BASE}/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteItem: (id: string) =>
    authFetch<void>(`${API_BASE}/items/${id}`, { method: "DELETE" }),

  batchDeleteItems: (itemIds: string[]) =>
    authFetch<{ deleted: number }>(`${API_BASE}/items/batch-delete`, {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds }),
    }),

  batchValidateItems: (itemIds: string[]) =>
    authFetch<{ updated: number }>(`${API_BASE}/items/batch-validate`, {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds }),
    }),

  // Functional area 7: evolution（自进化候选 ⑥ 落地工作流）
  evolutionCandidates: () =>
    authFetch<{ items: EvolutionCandidate[] }>(
      `${API_BASE}/evolution/candidates`,
    ),
  adoptEvolutionCandidate: (learningId: string) =>
    authFetch<{ status: string }>(
      `${API_BASE}/evolution/candidates/${learningId}/adopt`,
      { method: "POST" },
    ),
  dismissEvolutionCandidate: (learningId: string) =>
    authFetch<{ status: string }>(
      `${API_BASE}/evolution/candidates/${learningId}/dismiss`,
      { method: "POST" },
    ),

  deleteItemsByRun: (runId: string) =>
    authFetch<{ deleted: number }>(`${API_BASE}/items/by-run/${runId}`, {
      method: "DELETE",
    }),

  // Functional area 4: runs
  listRuns: (params?: {
    run_status?: string;
    has_items?: boolean;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CpaRun>>(`${API_BASE}/runs${qs(params)}`),

  deleteRun: (runId: string) =>
    authFetch<{ deleted: number }>(`${API_BASE}/runs/${runId}`, {
      method: "DELETE",
    }),

  // Functional area 5: config
  getConfig: () => authFetch<CpaConfig>(`${API_BASE}/config`),

  updateConfig: (body: CpaConfig) =>
    authFetch<CpaConfig>(`${API_BASE}/config`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // Pipeline trigger
  runPipeline: (mode = "table", trigger = "manual") =>
    authFetch<PipelineRunResponse>(`${API_BASE}/pipeline/run`, {
      method: "POST",
      body: JSON.stringify({ mode, trigger }),
    }),

  pipelineStatus: (run_id: string) =>
    authFetch<PipelineStatus>(`${API_BASE}/pipeline/runs/${run_id}/status`),
};
