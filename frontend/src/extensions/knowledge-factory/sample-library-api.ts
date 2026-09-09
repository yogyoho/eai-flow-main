"use client";

// EAI-CUSTOM: 样例库 API（coal-eia-report v2 BS3 MVP——样例台账 + 入库向导）。
// 自包含 kfRequest 副本（api/index.ts 的 kfRequest 未导出，勿反向耦合）。

export interface KFSampleRecord {
  id: string;
  title: string;
  source_path: string;
  file_hash: string;
  scenario: string;
  variant: string | null;
  status: string;
  confidence: number | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface KFSampleListResponse {
  samples: KFSampleRecord[];
  total: number;
}

export interface KFSampleUpsertInput {
  title: string;
  source_path: string;
  file_hash: string;
  scenario: string;
  variant?: string | null;
  status: string;
  confidence?: number | null;
  notes?: string | null;
}

export interface KFSampleBulkImportResult {
  created: number;
  updated: number;
  total: number;
}

export interface KFSampleListParams {
  scenario?: string;
  status?: string;
  search?: string;
  page?: number;
  limit?: number;
}

// 场景枚举——对齐后端 schemas.SampleScenario（coal-eia v2 回填对账定稿场景矩阵）
export const SAMPLE_SCENARIOS: { value: string; label: string }[] = [
  { value: "planning_eia", label: "规划环评" },
  { value: "project_eia_underground", label: "项目环评·井工" },
  { value: "project_eia_openpit", label: "项目环评·露天" },
  { value: "post_eia", label: "后评价" },
  { value: "tracking_eia", label: "跟踪评价" },
  { value: "reclamation_plan", label: "复垦方案" },
  { value: "other", label: "其他/片段" },
];

// 状态枚举——对齐后端 schemas.SampleStatus
export const SAMPLE_STATUSES: { value: string; label: string }[] = [
  { value: "parsed", label: "已解析" },
  { value: "converted", label: "已转换" },
  { value: "filename_only", label: "仅登记" },
  { value: "encrypted", label: "加密不可读" },
  { value: "converted_failed", label: "转换失败" },
];

export const SCENARIO_LABELS: Record<string, string> = Object.fromEntries(
  SAMPLE_SCENARIOS.map((s) => [s.value, s.label]),
);

export const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  SAMPLE_STATUSES.map((s) => [s.value, s.label]),
);

const API_BASE = "/api/kf";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function withCsrf(headers: HeadersInit, method?: string): HeadersInit {
  if (method && method !== "GET") {
    const token = getCsrfToken();
    if (token) {
      return { ...headers, "X-CSRF-Token": token };
    }
  }
  return headers;
}

async function sampleRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = withCsrf(
    { "Content-Type": "application/json", ...options.headers },
    options.method,
  );
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiError(0, msg.includes("fetch") ? "网络连接失败，请确认后端服务已启动" : msg);
  }
  if (!response.ok) {
    let message = "请求失败";
    try {
      const contentType = response.headers.get("content-type");
      if (contentType?.includes("application/json")) {
        const error = await response.json();
        if (typeof error.detail === "string") {
          message = error.detail;
        } else if (Array.isArray(error.detail)) {
          message = error.detail
            .map((x: { msg?: string }) => x?.msg)
            .filter(Boolean)
            .join("; ");
        }
      } else {
        const text = await response.text();
        if (text) message = text.slice(0, 200);
      }
    } catch {
      message = response.statusText || `Error ${response.status}`;
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

function buildQuery(params: KFSampleListParams): string {
  const query = new URLSearchParams();
  if (params.scenario) query.set("scenario", params.scenario);
  if (params.status) query.set("status", params.status);
  if (params.search) query.set("search", params.search);
  if (params.page && params.page > 1) query.set("page", String(params.page));
  if (params.limit) query.set("limit", String(params.limit));
  const s = query.toString();
  return s ? `?${s}` : "";
}

export const sampleLibraryApi = {
  list: (params: KFSampleListParams = {}) =>
    sampleRequest<KFSampleListResponse>(`/samples${buildQuery(params)}`),

  create: (data: KFSampleUpsertInput) =>
    sampleRequest<KFSampleRecord>("/samples", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  importBulk: (items: KFSampleUpsertInput[]) =>
    sampleRequest<KFSampleBulkImportResult>("/samples/import-bulk", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  get: (id: string) => sampleRequest<KFSampleRecord>(`/samples/${id}`),

  update: (id: string, data: Partial<KFSampleUpsertInput>) =>
    sampleRequest<KFSampleRecord>(`/samples/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  remove: (id: string) =>
    sampleRequest<{ message: string }>(`/samples/${id}`, { method: "DELETE" }),
};
