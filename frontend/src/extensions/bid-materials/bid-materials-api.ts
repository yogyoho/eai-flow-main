"use client";

// EAI-CUSTOM (Plan 4, spec 2026-09-06 §2.3): 投标资料管理 API——资质版本库(MinIO 代理)+标书样例台账。
// 镜像 eia-samples/sample-library-api.ts 的自包含 fetch+CSRF 模式(extensions 路由 cookie+CSRF 契约同款);
// 自包含 fetch 封装, 未导出, 勿反向耦合。资质文件下发走 <a href> 直链(cookie 认证随行, GET 免 CSRF); fileUrl 支持 ?version=n 按版本(缺省当前版)。
// 契约以 backend/app/extensions/bid_materials/{routers,schemas}.py 实读为准(Plan 4 Task 1 核验), 差异点:
//   - rollback 请求体键为 to_version(RollbackRequest), 非 version;
//   - 资质软删响应为 {disabled:true}(非 message); 样例停用响应为 {message};
//   - 列表过滤仅透传后端实有参数——qualifications: qual_type/include_disabled/limit/offset;
//     samples: industry/project_category/q/limit/offset(标题模糊搜索键名是 q; 无 status 过滤);
//   - 文件下发仅当前版(GET /qualifications/{id}/file 无 version 参数, 版本级下发待后端扩展);
//   - 样例无单条 POST 端点——登记一律走 /samples/bulk 幂等导入(file_hash upsert);
//   - 资质类型为后端 QualType Literal 闭集(schemas.py), 预设逐一对齐——自由文本会被 422;
//   - export-whitelist 端点刻意不封装(WP-2.4 消费方是后端工具链; UI 若需直链下载即可)。
// 大纲候选(只读回看)不在 extensions 命名空间——走核心网关线程 artifacts 通道
// /api/threads/{tid}/artifacts/... , 经同一 bidRequest 咽喉点(绝对 /api/ 路径直通不拼 API_BASE,
// GET 免 CSRF); 404(线程未走大纲自拟流程)归一为 null, 由调用方区分于真错误。

export interface QualificationRecord {
  id: string;
  qual_type: string;
  cert_no: string;
  issuer: string | null;
  valid_until: string | null; // ISO date (YYYY-MM-DD)
  scope: string | null;
  current_version: number;
  org_scope: string | null;
  disabled: boolean;
  notes: string | null;
}

export interface QualificationVersionRecord {
  id: string;
  qualification_id: string;
  version: number;
  minio_key: string;
  sha256: string;
  file_ext: string;
  file_size: number;
  note: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}

export interface QualificationVersionUploadResult {
  created: boolean; // false = sha256 去重命中(幂等返回既有版)
  version: number;
  sha256: string;
}

export interface QualificationUpsertInput {
  qual_type: string;
  cert_no: string;
  issuer?: string | null;
  valid_until?: string | null; // YYYY-MM-DD
  scope?: string | null;
  org_scope?: string | null;
  notes?: string | null;
}

export interface BidSampleRecord {
  id: string;
  title: string;
  source_path: string;
  file_hash: string;
  industry: string;
  project_category: string;
  scenario: string;
  status: string;
  notes: string | null;
}

export interface BidSampleUpsertInput {
  title: string;
  source_path: string;
  file_hash: string; // 64 位十六进制(SHA-256; 后端 min/max length=64 硬校验, 空/短串 422)
  industry: string;
  project_category: string;
  scenario: string;
  status: string;
  notes?: string | null;
}

export interface BidSampleBulkResult {
  created: number;
  updated: number; // 幂等语义下恒 0(后端只分新/跳过)
  total: number;
}

export interface QualificationListParams {
  qual_type?: string;
  include_disabled?: boolean;
  limit?: number;
  offset?: number;
}

export interface BidSampleListParams {
  industry?: string;
  project_category?: string;
  q?: string; // 标题模糊搜索(后端键名 q, ilike 下推)
  limit?: number;
  offset?: number;
}

// 资质类型预设——逐字对齐后端 QualType Literal(schemas.py 闭集; 后端收 Literal, 自由文本 422)
export const QUAL_TYPE_PRESETS: { value: string; label: string }[] = [
  { value: "营业执照", label: "营业执照" },
  { value: "CMMI", label: "CMMI" },
  { value: "ISO9001", label: "ISO9001 质量体系" },
  { value: "ISO27001", label: "ISO27001 信息安全" },
  { value: "业绩证明", label: "业绩证明" },
  { value: "软件著作权", label: "软件著作权" },
  { value: "高新技术企业", label: "高新技术企业" },
  { value: "其他", label: "其他" },
];

// 场景枚举——对齐 SampleCreate.scenario(值域暂不收枚举, 台账自由文本; 本期单一场景)
export const SAMPLE_SCENARIOS: { value: string; label: string }[] = [
  { value: "bid_sample", label: "投标样例" },
];

// 状态枚举——对齐 BidSample.status(值域暂不收枚举; bank_compile registration.json 产 indexed)
export const SAMPLE_STATUSES: { value: string; label: string }[] = [
  { value: "indexed", label: "已入库" },
  { value: "ragflow_pushed", label: "已推 RAGFlow" },
  { value: "disabled", label: "已停用" },
];

const API_BASE = "/api/extensions/bid-materials";

export class ApiError extends Error {
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

async function bidRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  // multipart(FormData)体不注入 JSON Content-Type——手工 application/json 会压掉
  // 浏览器自动生成的 multipart boundary, 后端解析不到 file 字段。
  const isForm = options.body instanceof FormData;
  const headers = withCsrf(
    isForm
      ? { ...options.headers }
      : { "Content-Type": "application/json", ...options.headers },
    options.method,
  );
  // 核心 /api/ 开头的绝对路径直通(线程 artifacts 通道在核心网关命名空间)——其余拼 extensions API_BASE
  const url = path.startsWith("/api/") ? path : `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiError(
      0,
      msg.includes("fetch") ? "网络连接失败，请确认后端服务已启动" : msg,
    );
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

function buildQuery(params: {
  qual_type?: string;
  include_disabled?: boolean;
  industry?: string;
  project_category?: string;
  q?: string;
  limit?: number;
  offset?: number;
}): string {
  const query = new URLSearchParams();
  if (params.qual_type) query.set("qual_type", params.qual_type);
  if (params.include_disabled) query.set("include_disabled", "true");
  if (params.industry) query.set("industry", params.industry);
  if (params.project_category)
    query.set("project_category", params.project_category);
  if (params.q) query.set("q", params.q);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  const s = query.toString();
  return s ? `?${s}` : "";
}

// ============== 大纲候选（只读回看） ==============

// 候选章节——对齐 candidates/tech_outline.candidates.json（outline_merge.py validate 契约:
// no 为非布尔 int; title 非空串; clause_ids 非空字符串数组; notes 可空）
export interface OutlineChapter {
  no: number;
  title: string;
  clause_ids: string[];
  notes: string | null;
}

// 大纲候选文件本体——B1 大纲自拟产物（B2 消费其章锚点）; source_pack 为 null = 无骨架包自由拟
export interface OutlineCandidatesPayload {
  source_pack: string | null;
  confirmed: boolean;
  chapters: OutlineChapter[];
  managed_node_ids: string[];
}

// 候选文件 artifacts 虚拟路径——双斜杠契约: 网关 artifacts 路由捕获 {path:path} 且要求虚拟路径
// 以 /mnt/user-data 开头, 故 URL 以 /artifacts//mnt 起头（nginx 保留双斜杠, live 验证 200）。
// 勿"修复"成单斜杠——单斜杠会被并入路由段, 404。
const OUTLINE_CANDIDATES_VPATH =
  "/mnt/user-data/workspace/bid/candidates/tech_outline.candidates.json";

export const bidMaterialsApi = {
  qualifications: {
    list: (params: QualificationListParams = {}) =>
      bidRequest<QualificationRecord[]>(`/qualifications${buildQuery(params)}`),

    expiring: (days = 90) =>
      bidRequest<QualificationRecord[]>(
        `/qualifications/expiring?days=${days}`,
      ),

    create: (data: QualificationUpsertInput) =>
      bidRequest<QualificationRecord>("/qualifications", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    get: (id: string) =>
      bidRequest<QualificationRecord>(`/qualifications/${id}`),

    update: (id: string, data: Partial<QualificationUpsertInput>) =>
      bidRequest<QualificationRecord>(`/qualifications/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    disable: (id: string) =>
      bidRequest<{ disabled: boolean }>(`/qualifications/${id}`, {
        method: "DELETE",
      }),

    versions: (id: string) =>
      bidRequest<QualificationVersionRecord[]>(
        `/qualifications/${id}/versions`,
      ),

    uploadVersion: (id: string, file: File, note?: string) => {
      const form = new FormData();
      form.append("file", file);
      if (note) form.append("note", note); // 后端 multipart 键名 note(max_length=200)
      // 不设 Content-Type——浏览器自带 multipart boundary; CSRF 由 bidRequest 单一咽喉点统一注入
      return bidRequest<QualificationVersionUploadResult>(
        `/qualifications/${id}/versions`,
        {
          method: "POST",
          headers: {},
          body: form,
        },
      );
    },

    rollback: (id: string, toVersion: number) =>
      bidRequest<QualificationRecord>(`/qualifications/${id}/rollback`, {
        method: "POST",
        body: JSON.stringify({ to_version: toVersion }), // 后端 RollbackRequest 键名 to_version
      }),

    // ?version=n 按版本下发(后端 b45f97185 补齐 spec §2.3); 缺省=当前版语义不变
    fileUrl: (id: string, version?: number) =>
      `${API_BASE}/qualifications/${id}/file${version ? `?version=${version}` : ""}`,
  },
  samples: {
    list: (params: BidSampleListParams = {}) =>
      bidRequest<BidSampleRecord[]>(`/samples${buildQuery(params)}`),

    importBulk: (items: BidSampleUpsertInput[]) =>
      bidRequest<BidSampleBulkResult>("/samples/bulk", {
        method: "POST",
        body: JSON.stringify({ items }),
      }),

    get: (id: string) => bidRequest<BidSampleRecord>(`/samples/${id}`),

    disable: (id: string) =>
      bidRequest<{ message: string }>(`/samples/${id}`, { method: "DELETE" }),
  },
  outline: {
    // 只读回看线程的大纲候选; 404 = 线程未产候选（未走大纲自拟流程, 含零条款跳过分支）→ null,
    // 其余错误（含 403 非本线程 owner）原样上抛由调用方分型提示
    candidates: async (
      threadId: string,
    ): Promise<OutlineCandidatesPayload | null> => {
      try {
        return await bidRequest<OutlineCandidatesPayload>(
          `/api/threads/${encodeURIComponent(threadId)}/artifacts/${OUTLINE_CANDIDATES_VPATH}`,
        );
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  },
};
