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
  CpaLibraryAnalyze,
  CpaLibraryFile,
  CpaLibraryFolder,
  CpaLibraryUploadItem,
  CpaRun,
  CpaNameSplit,
  CpaTerm,
  EvolutionCandidate,
  Page,
  PipelineRunResponse,
  PipelineStatus,
  RagflowInitResponse,
  RagflowStatusResponse,
  RagflowSyncItemsResponse,
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

// EAI-CUSTOM: cpa v3 合同文件库（spec 2026-10-14 §1.2/§1.3）
export const libraryApi = {
  listFolders: () =>
    authFetch<{ items: CpaLibraryFolder[] }>(`${API_BASE}/library/folders`),

  createFolder: (name: string, parentId: string | null) =>
    authFetch<CpaLibraryFolder>(`${API_BASE}/library/folders`, {
      method: "POST",
      body: JSON.stringify({ name, parent_id: parentId }),
    }),

  updateFolder: (
    id: string,
    patch: { name?: string; parent_id?: string | null },
  ) =>
    authFetch<CpaLibraryFolder>(`${API_BASE}/library/folders/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteFolder: (id: string) =>
    authFetch<{ ok: boolean }>(`${API_BASE}/library/folders/${id}`, {
      method: "DELETE",
    }),

  // folder_id 仅在非空时拼接——空串会被 FastAPI 422。
  listFiles: (folderId: string | null) =>
    authFetch<{ items: CpaLibraryFile[] }>(
      `${API_BASE}/library/files${folderId ? `?folder_id=${folderId}` : ""}`,
    ),

  uploadFiles: (
    folderId: string | null,
    files: File[],
    ragflowSync = false,
  ) => {
    const fd = new FormData();
    if (folderId) fd.set("folder_id", folderId);
    // EAI-CUSTOM: 勾选后逐文件同步 RAGFlow「合同知识库」（后端失败隔离，不影响上传本身）。
    // 始终显式传值：避免后端缺省歧义（"false" 会被 FastAPI 正确解析为 False）
    fd.set("ragflow_sync", String(ragflowSync));
    // webkitdirectory 上传带 webkitRelativePath——原样传给后端逐级建子文件夹（spec §1.2）
    fd.set(
      "paths",
      JSON.stringify(
        files.map(
          (f) =>
            (f as File & { webkitRelativePath?: string }).webkitRelativePath ??
            "",
        ),
      ),
    );
    for (const f of files) fd.append("files", f);
    return authFormFetch<{ items: CpaLibraryUploadItem[] }>(
      `${API_BASE}/library/files/upload`,
      fd,
    );
  },

  analyzeFile: (id: string) =>
    authFetch<CpaLibraryAnalyze>(`${API_BASE}/library/files/${id}/analyze`, {
      method: "POST",
    }),

  moveFile: (id: string, folderId: string | null) =>
    authFetch<CpaLibraryFile>(`${API_BASE}/library/files/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ folder_id: folderId }),
    }),

  deleteFile: (id: string) =>
    authFetch<{ ok: boolean }>(`${API_BASE}/library/files/${id}`, {
      method: "DELETE",
    }),

  /** 浏览器直接 GET（PDF 内嵌预览 / docx 下载），走完整路径。 */
  fileContentUrl: (id: string) => `${FULL_BASE}/library/files/${id}/content`,

  fileItems: (id: string) =>
    authFetch<{
      document: { id: string; file_name: string; parse_status: string };
      items: CpaItem[];
      total: number;
    }>(`${API_BASE}/library/files/${id}/items`),
};

// EAI-CUSTOM: cpa v3 货物分类术语（spec 2026-10-14 §2.4）
export const termsApi = {
  list: () => authFetch<{ items: CpaTerm[] }>(`${API_BASE}/terms`),

  create: (canonical: string, aliases: string[]) =>
    authFetch<CpaTerm>(`${API_BASE}/terms`, {
      method: "POST",
      body: JSON.stringify({ canonical, aliases }),
    }),

  update: (
    id: string,
    patch: { canonical?: string; aliases?: string[]; enabled?: boolean },
  ) =>
    authFetch<CpaTerm>(`${API_BASE}/terms/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  remove: (id: string) =>
    authFetch<{ ok: boolean }>(`${API_BASE}/terms/${id}`, {
      method: "DELETE",
    }),
};

// EAI-CUSTOM: RAGFlow SSO 知识库幂等初始化 + 连通状态（两固定库，见 ragflow_setup）
export const ragflowApi = {
  /** 连通状态——RAGFlow 不可达时后端 degraded（available=false + error），不抛 5xx。 */
  status: () => authFetch<RagflowStatusResponse>(`${API_BASE}/ragflow/status`),

  /** 幂等初始化：两库有则对齐、无则创建，重复点击仅对齐。 */
  init: () =>
    authFetch<RagflowInitResponse>(`${API_BASE}/ragflow/init`, {
      method: "POST",
    }),

  /** EAI-CUSTOM (决策 B): 手动同步该合同的分项表——聚合当前 cpa_items 为
   * Markdown 分项表,替换式上传「合同货物分项表格」并触发解析。
   * 未解析 409 / 无分项 404 / 文档不存在 404 / 服务或 RAGFlow 故障 503,
   * detail 消息经 authFetch 透传（toast 直读 e.message）。 */
  syncItems: (docId: string) =>
    authFetch<RagflowSyncItemsResponse>(
      `${API_BASE}/documents/${docId}/ragflow-sync-items`,
      { method: "POST" },
    ),
};

// EAI-CUSTOM: 易混名称区分表（2026-10-22）
export const nameSplitApi = {
  list: () => authFetch<{ items: CpaNameSplit[] }>(`${API_BASE}/name-splits`),

  create: (name_a: string, name_b: string, reason?: string) =>
    authFetch<CpaNameSplit>(`${API_BASE}/name-splits`, {
      method: "POST",
      body: JSON.stringify({ name_a, name_b, reason }),
    }),

  update: (id: string, patch: { reason?: string; enabled?: boolean }) =>
    authFetch<CpaNameSplit>(`${API_BASE}/name-splits/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  remove: (id: string) =>
    authFetch<{ ok: boolean }>(`${API_BASE}/name-splits/${id}`, {
      method: "DELETE",
    }),
};
