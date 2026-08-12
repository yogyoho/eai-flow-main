/**
 * API client for the spare-parts-analysis management API.
 *
 * Endpoints live under `/api/extensions/spare-parts/*` (mounted in the
 * Gateway). `authFetch`'s default base is `/api/extensions`, so we pass the
 * `/spare-parts/...` suffix.
 */

import { authFetch, authFormFetch } from "@/extensions/api/client";

import type {
  CspCluster,
  CspClusterDetail,
  CspConfig,
  CspCustomer,
  CspCustomerCreate,
  CspCustomerResolveResult,
  CspCustomerUpdate,
  CspDashboard,
  CspDocument,
  CspItem,
  CspItemCustomer,
  CspRun,
  Page,
  PipelineRunResponse,
  PipelineStatus,
  UploadResponse,
} from "./types";

const API_BASE = "/spare-parts";
/** Full path for non-JSON GETs the browser issues directly (e.g. <img src>). */
const FULL_BASE = "/api/extensions/spare-parts";

/** Build a query string, skipping empty/null/undefined values. */
export function qs(
  params?: Record<string, string | number | boolean | null | undefined>
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const sparePartsApi = {
  // Functional area 6: dashboard
  dashboard: () => authFetch<CspDashboard>(`${API_BASE}/dashboard`),

  // Cross-contract goods analysis
  partsAnalysis: (params: { name?: string; cluster_id?: string; skip?: number; limit?: number }) =>
    authFetch<Record<string, unknown>>(`${API_BASE}/spare-parts-analysis${qs(params)}`),

  // Functional area 1: documents
  listDocuments: (params?: {
    keyword?: string;
    parse_status?: string;
    customer_id?: string;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CspDocument>>(`${API_BASE}/documents${qs(params)}`),

  deleteDocument: (id: string) =>
    authFetch<void>(`${API_BASE}/documents/${id}`, { method: "DELETE" }),

  reparseDocument: (id: string) =>
    authFetch<{ run_id: string; status: string; message?: string }>(`${API_BASE}/documents/${id}/reparse`, {
      method: "POST",
    }),

  updateDocument: (
    id: string,
    body: Partial<
      Pick<
        CspDocument,
        | "project_name"
        | "project_location"
        | "contract_no"
        | "supplier"
        | "customer_id"
        | "customer_name"
        | "sign_date"
      >
    >
  ) =>
    authFetch<CspDocument>(`${API_BASE}/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  confirmDocument: (id: string, confirm_status: "confirmed" | "skipped") =>
    authFetch<CspDocument>(`${API_BASE}/documents/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirm_status }),
    }),

  confirmAllDocuments: (confirm_status: "confirmed" | "skipped") =>
    authFetch<{ updated: number; confirm_status: string }>(`${API_BASE}/documents/confirm-all`, {
      method: "POST",
      body: JSON.stringify({ confirm_status }),
    }),

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

  // Functional area 2: clusters
  listClusters: (params?: {
    cluster_status?: string;
    category?: string;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CspCluster>>(`${API_BASE}/clusters${qs(params)}`),

  getCluster: (id: string) => authFetch<CspClusterDetail>(`${API_BASE}/clusters/${id}`),

  confirmCluster: (id: string, body?: { confirmed_by?: string; expected_version?: number }) =>
    authFetch<{ status: string; version: number }>(`${API_BASE}/clusters/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),

  rejectCluster: (id: string, body?: { expected_version?: number }) =>
    authFetch<{ status: string; version: number }>(`${API_BASE}/clusters/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),

  updateCluster: (id: string, body: { category?: string; representative_name?: string }) =>
    authFetch<CspCluster>(`${API_BASE}/clusters/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  mergeClusters: (cluster_ids: string[], representative_name: string, category?: string) =>
    authFetch<{ cluster_id: string; item_count: number }>(`${API_BASE}/clusters/merge`, {
      method: "POST",
      body: JSON.stringify({ cluster_ids, representative_name, category }),
    }),

  moveItem: (item_id: string, target_cluster_id: string) =>
    authFetch<{ item_id: string; cluster_id: string }>(`${API_BASE}/items/${item_id}/move`, {
      method: "POST",
      body: JSON.stringify({ target_cluster_id }),
    }),

  // Functional area 3: items
  listItemContracts: () =>
    authFetch<{ source_contract_no: string; count: number }[]>(`${API_BASE}/items/contracts`),

  /** 明细按客户聚合(D3 客户维度)。 */
  listItemCustomers: () => authFetch<CspItemCustomer[]>(`${API_BASE}/items/customers`),

  listItems: (params?: {
    part_name?: string;
    source_contract_no?: string;
    cluster_id?: string;
    run_id?: string;
    customer_id?: string;
    only_outliers?: boolean;
    validation_status?: string;
    skip?: number;
    limit?: number;
  }) => authFetch<Page<CspItem>>(`${API_BASE}/items${qs(params)}`),

  updateItem: (
    id: string,
    body: {
      unit_price?: number;
      tech_params?: Record<string, string>;
      part_name?: string;
      spec?: string;
      validation_status?: string;
      note?: string;
    }
  ) =>
    authFetch<CspItem>(`${API_BASE}/items/${id}`, {
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

  deleteItemsByRun: (runId: string) =>
    authFetch<{ deleted: number }>(`${API_BASE}/items/by-run/${runId}`, { method: "DELETE" }),

  // Functional area 4: runs
  listRuns: (params?: { run_status?: string; has_items?: boolean; skip?: number; limit?: number }) =>
    authFetch<Page<CspRun>>(`${API_BASE}/runs${qs(params)}`),

  deleteRun: (runId: string) =>
    authFetch<{ deleted: number }>(`${API_BASE}/runs/${runId}`, { method: "DELETE" }),

  // Functional area 5: config
  getConfig: () => authFetch<CspConfig>(`${API_BASE}/config`),

  updateConfig: (body: CspConfig) =>
    authFetch<CspConfig>(`${API_BASE}/config`, {
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

  // Functional area 7: 客户管理 (D3 master/alias 归并)
  listCustomers: (params?: { keyword?: string; status?: string; skip?: number; limit?: number }) =>
    authFetch<Page<CspCustomer>>(`${API_BASE}/customers${qs(params)}`),

  createCustomer: (body: CspCustomerCreate) =>
    authFetch<CspCustomer>(`${API_BASE}/customers`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateCustomer: (id: string, body: CspCustomerUpdate) =>
    authFetch<CspCustomer>(`${API_BASE}/customers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** 把一个 OCR 脏客户名认领到已有客户(追加为别名)。 */
  claimCustomer: (id: string, raw_name: string) =>
    authFetch<CspCustomer>(`${API_BASE}/customers/${id}/claim`, {
      method: "POST",
      body: JSON.stringify({ raw_name }),
    }),

  /** 多个客户合并到目标客户(文档+明细 customer_id 重指、别名合并)。 */
  mergeCustomers: (source_ids: string[], target_id: string) =>
    authFetch<CspCustomer>(`${API_BASE}/customers/merge`, {
      method: "POST",
      body: JSON.stringify({ source_ids, target_id }),
    }),

  /** 只读预览:一批脏客户名能匹配到哪些客户(未匹配 → customer_id=null)。 */
  resolveCustomers: (raw_names: string[]) =>
    authFetch<CspCustomerResolveResult[]>(`${API_BASE}/customers/resolve`, {
      method: "POST",
      body: JSON.stringify({ raw_names }),
    }),
};
