import type {
  User,
  UserListResponse,
  CreateUserRequest,
  UpdateUserRequest,
  Role,
  RoleListResponse,
  CreateRoleRequest,
  UpdateRoleRequest,
  RoleHierarchyResponse,
  Department,
  DepartmentListResponse,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
  KnowledgeBase,
  KnowledgeBaseListResponse,
  CreateKnowledgeBaseRequest,
  UpdateKnowledgeBaseRequest,
  Document,
  DocumentListResponse,
  MessageResponse,
  Conversation,
  ConversationListResponse,
  CreateConversationRequest,
  UpdateConversationRequest,
  AIDocument,
  AIDocumentListResponse,
  CreateAIDocumentRequest,
  UpdateAIDocumentRequest,
  FolderListResponse,
  ChunkConfig,
  SampleReport,
  SampleReportListResponse,
  KnowledgeBaseExtended,
  CreateKnowledgeBaseRequestExtended,
  KnowledgeBaseStatus,
  RAGChatRequest,
  RAGChatResponse,
} from "../types";
import type {
  ExtractionDomain,
  ExtractionTaskCreate,
  ExtractionTaskResponse,
  ExtractionTaskListResponse,
  TemplateListResponse,
  TemplateDocument,
  TemplateVersionResponse,
} from "../knowledge-factory/types";

const API_BASE = "/api/extensions";
const KF_API_BASE = "/api/kf";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function kfRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  let response: Response;
  try {
    response = await fetch(`${KF_API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiError(0, msg.includes("fetch") ? "Network connection failed, please check if backend is running" : msg);
  }

  if (!response.ok) {
    let message = "Request failed";
    const contentType = response.headers.get("content-type");
    try {
      if (contentType?.includes("application/json")) {
        const error = await response.json();
        message =
          typeof error.detail === "string"
            ? error.detail
            : Array.isArray(error.detail)
              ? error.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") || message
              : message;
      } else {
        const text = await response.text();
        if (text) message = text.slice(0, 200);
      }
    } catch {
      message = response.statusText || `Error ${response.status}`;
    }
    throw new ApiError(response.status, message);
  }

  return response.json();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiError(0, msg.includes("fetch") ? "Network connection failed, please check if backend is running" : msg);
  }

  if (!response.ok) {
    let message = "Request failed";
    const contentType = response.headers.get("content-type");
    try {
      if (contentType?.includes("application/json")) {
        const error = await response.json();
        message =
          typeof error.detail === "string"
            ? error.detail
            : Array.isArray(error.detail)
              ? error.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") || message
              : message;
      } else {
        const text = await response.text();
        if (text) message = text.slice(0, 200);
      }
    } catch {
      message = response.statusText || `Error ${response.status}`;
    }
    throw new ApiError(response.status, message);
  }

  return response.json();
}

// Auth is now handled by Gateway Auth (HttpOnly cookie, sent via credentials: "include").
// The Extensions /api/extensions/auth/* endpoints have been removed.

// ===== User API =====

export const userApi = {
  list: (params?: { skip?: number; limit?: number; dept_id?: string; role_id?: string; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.dept_id) query.set("dept_id", params.dept_id);
    if (params?.role_id) query.set("role_id", params.role_id);
    if (params?.status) query.set("status", params.status);
    return request<UserListResponse>(`/users?${query}`);
  },

  get: (id: string) => request<User>(`/users/${id}`),

  create: (data: CreateUserRequest) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateUserRequest) =>
    request<User>(`/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<MessageResponse>(`/users/${id}`, { method: "DELETE" }),

  resetPassword: (id: string, newPassword: string) =>
    request<MessageResponse>(`/users/${id}/reset-password?new_password=${newPassword}`, { method: "POST" }),

  // Multi-department APIs
  getDepartments: (id: string) =>
    request<{ dept_ids: string[]; primary_dept_id: string | null }>(`/users/${id}/departments`),

  updateDepartments: (id: string, deptIds: string[], primaryDeptId?: string) =>
    request<{ dept_ids: string[]; primary_dept_id: string | null }>(
      `/users/${id}/departments`,
      { method: "PUT", body: JSON.stringify({ dept_ids: deptIds, primary_dept_id: primaryDeptId }) }
    ),
};

// ===== Role API =====

export const roleApi = {
  list: (params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<RoleListResponse>(`/roles?${query}`);
  },

  get: (id: string) => request<Role>(`/roles/${id}`),

  create: (data: CreateRoleRequest) =>
    request<Role>("/roles", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateRoleRequest) =>
    request<Role>(`/roles/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<MessageResponse>(`/roles/${id}`, { method: "DELETE" }),

  // Hierarchy APIs
  getHierarchy: (id: string) =>
    request<RoleHierarchyResponse>(`/roles/${id}/hierarchy`),

  getAncestors: (id: string) =>
    request<Role[]>(`/roles/${id}/hierarchy/ancestors`),

  getDescendants: (id: string) =>
    request<Role[]>(`/roles/${id}/hierarchy/descendants`),
};

// ===== Department API =====

export const deptApi = {
  list: (params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<DepartmentListResponse>(`/departments?${query}`);
  },

  get: (id: string) => request<Department>(`/departments/${id}`),

  create: (data: CreateDepartmentRequest) =>
    request<Department>("/departments", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateDepartmentRequest) =>
    request<Department>(`/departments/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<MessageResponse>(`/departments/${id}`, { method: "DELETE" }),
};

// ===== Knowledge Base API =====

export const kbApi = {
  list: (params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<KnowledgeBaseListResponse>(`/knowledge-bases?${query}`);
  },

  get: (id: string) => request<KnowledgeBase>(`/knowledge-bases/${id}`),

  create: (data: CreateKnowledgeBaseRequest) =>
    request<KnowledgeBase>("/knowledge-bases", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateKnowledgeBaseRequest) =>
    request<KnowledgeBase>(`/knowledge-bases/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<MessageResponse>(`/knowledge-bases/${id}`, { method: "DELETE" }),

  listDocs: (kbId: string, params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<DocumentListResponse>(`/knowledge-bases/${kbId}/documents?${query}`);
  },

  uploadDoc: (kbId: string, file: File, chunkConfig?: ChunkConfig) => {
    const formData = new FormData();
    formData.append("file", file);
    if (chunkConfig) {
      formData.append("chunk_config", JSON.stringify(chunkConfig));
    }
    return fetch(`${API_BASE}/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      credentials: "include",
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(res.status, err.detail || "Upload failed");
      }
      return res.json() as Promise<Document>;
    });
  },

  deleteDoc: (kbId: string, docId: string) =>
    request<MessageResponse>(`/knowledge-bases/${kbId}/documents/${docId}`, { method: "DELETE" }),

  listChunks: (kbId: string, docId: string, params?: { page?: number; size?: number }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.size) query.set("size", String(params.size));
    return request<{
      total: number;
      chunks: Array<{ id?: string; content?: string; document_id?: string; [k: string]: unknown }>;
      message?: string;
    }>(`/knowledge-bases/${kbId}/documents/${docId}/chunks?${query}`);
  },

  // Get knowledge base sync status
  getStatus: (id: string) => request<KnowledgeBaseStatus>(`/knowledge-bases/${id}/status`),

  // Chat with knowledge base
  chat: (id: string, data: RAGChatRequest) =>
    request<RAGChatResponse>(`/knowledge-bases/${id}/chat`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ===== Conversation API =====

export const conversationApi = {
  list: (params?: { skip?: number; limit?: number; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.status) query.set("status", params.status);
    return request<ConversationListResponse>(`/conversations?${query}`);
  },

  get: (threadId: string) => request<Conversation>(`/conversations/${threadId}`),

  create: (data?: CreateConversationRequest) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(data || {}) }),

  update: (threadId: string, data: UpdateConversationRequest) =>
    request<Conversation>(`/conversations/${threadId}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (threadId: string, hard?: boolean) =>
    request<MessageResponse>(`/conversations/${threadId}?hard=${hard || false}`, { method: "DELETE" }),
};

// ===== Document Manager API =====

export const docmgrApi = {
  list: (params?: {
    folder?: string;
    starred?: boolean;
    shared?: boolean;
    q?: string;
    skip?: number;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.folder) query.set("folder", params.folder);
    if (params?.starred !== undefined) query.set("starred", String(params.starred));
    if (params?.shared !== undefined) query.set("shared", String(params.shared));
    if (params?.q) query.set("q", params.q);
    if (params?.skip !== undefined) query.set("skip", String(params.skip));
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    return request<AIDocumentListResponse>(`/docmgr/documents?${query}`);
  },

  get: (id: string) => request<AIDocument>(`/docmgr/documents/${id}`),

  create: (data: CreateAIDocumentRequest) =>
    request<AIDocument>("/docmgr/documents", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: UpdateAIDocumentRequest) =>
    request<AIDocument>(`/docmgr/documents/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<MessageResponse>(`/docmgr/documents/${id}`, { method: "DELETE" }),

  listFolders: () => request<FolderListResponse>("/docmgr/folders"),

  export: (id: string, format: "md" | "txt" | "docx" = "md") => {
    return fetch(`${API_BASE}/docmgr/documents/${id}/export?format=${format}`, {
      credentials: "include",
    });
  },

  aiEdit: (data: {
    text: string;
    operation: "polish" | "expand" | "condense" | "brainstorm";
    model_name?: string;
  }) =>
    request<{ result: string }>("/docmgr/documents/ai-edit", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ===== Models API (direct gateway, not under /api/extensions) =====

interface ModelInfo {
  name: string;
  display_name?: string;
  description?: string;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
}

async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  let response: Response;
  try {
    response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_BASE_URL || ""}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "Network connection failed");
  }
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  return response.json();
}

export const modelsApi = {
  list: () => fetchApi<{ models: ModelInfo[] }>("/api/models"),
};

// ===== Web Scraper API =====

interface ScrapeRequest {
  url: string;
  prompt?: string;
  provider?: string;
  schema_name?: string;
  custom_schema?: string;
  llm_model?: string;
  timeout?: number;
  proxy?: Record<string, unknown>;
  auth?: Record<string, unknown>;
}

interface ScrapeResponse {
  task_id: string;
  status: string;
  message: string;
}

interface ProviderInfo {
  name: string;
  display_name?: string;
  supports_structured: boolean;
  is_primary: boolean;
}

interface SchemaInfo {
  name: string;
  display_name: string;
  description: string;
  category: string;
  supports_structured: boolean;
}

interface ScrapDraftCreate {
  source_url: string;
  source_title?: string;
  schema_name: string;
  schema_display_name?: string;
  raw_content: string;
  structured_data?: string;
  title: string;
  tags?: string[];
  category?: string;
}

interface ScrapDraftUpdate {
  title?: string;
  raw_content?: string;
  structured_data?: string;
  tags?: string[];
  category?: string;
}

export interface ScrapDraft {
  id: string;
  source_url: string;
  source_title?: string;
  schema_name: string;
  schema_display_name?: string;
  title: string;
  tags: string[];
  category?: string;
  status: string;
  source_provider: string;
  scrape_date: string;
  knowledge_base_id?: string;
  created_at: string;
  updated_at: string;
}

export interface ScrapDraftDetail extends ScrapDraft {
  raw_content: string;
  structured_data?: string;
  document_id?: string;
}

interface ScrapDraftListResponse {
  drafts: ScrapDraft[];
  total: number;
  page: number;
  page_size: number;
}

interface ImportDraftRequest {
  knowledge_base_id: string;
  chunk_method?: string;
  auto_parse?: boolean;
}

interface ImportDraftResponse {
  success: boolean;
  draft_id: string;
  document_id: string;
  knowledge_base_id: string;
  message: string;
}

export const scraperApi = {
  scrape: (data: ScrapeRequest) =>
    request<ScrapeResponse>("/web-scraper/scrape", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listProviders: () =>
    request<{ providers: ProviderInfo[] }>("/web-scraper/providers"),

  listSchemas: () =>
    request<{ schemas: SchemaInfo[] }>("/web-scraper/schemas"),

  cancel: (taskId: string) =>
    request<MessageResponse>(`/web-scraper/cancel/${taskId}`, { method: "POST" }),

  getResult: (taskId: string) =>
    request<{
      task_id: string;
      status: string;
      result?: string;
      error?: string;
      provider_used?: string;
      structured_data?: Record<string, unknown>;
    }>(`/web-scraper/result/${taskId}`),

  listDrafts: (params?: { status?: string; page?: number; page_size?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.page !== undefined) query.set("page", String(params.page));
    if (params?.page_size !== undefined) query.set("page_size", String(params.page_size));
    return request<ScrapDraftListResponse>(`/web-scraper/drafts?${query}`);
  },

  getDraft: (id: string) =>
    request<ScrapDraftDetail>(`/web-scraper/drafts/${id}`),

  createDraft: (data: ScrapDraftCreate) =>
    request<ScrapDraft>(`/web-scraper/drafts`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateDraft: (id: string, data: ScrapDraftUpdate) =>
    request<ScrapDraft>(`/web-scraper/drafts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteDraft: (id: string) =>
    request<MessageResponse>(`/web-scraper/drafts/${id}`, { method: "DELETE" }),

  importDraft: (id: string, data: ImportDraftRequest) =>
    request<ImportDraftResponse>(`/web-scraper/drafts/${id}/import`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ===== Knowledge Factory API =====

export const kfApi = {
  // Knowledge base
  listKnowledgeBases: (params?: { skip?: number; limit?: number; kb_type?: string }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.kb_type) query.set("kb_type", params.kb_type);
    return request<KnowledgeBaseListResponse>(`/knowledge-bases?${query}`);
  },

  createKnowledgeBase: (data: CreateKnowledgeBaseRequest) =>
    request<KnowledgeBase>("/knowledge-bases", { method: "POST", body: JSON.stringify(data) }),

  // Documents
  listDocs: (kbId: string, params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<DocumentListResponse>(`/knowledge-bases/${kbId}/documents?${query}`);
  },

  uploadDoc: (kbId: string, file: File, chunkConfig?: ChunkConfig) => {
    const formData = new FormData();
    formData.append("file", file);
    if (chunkConfig) {
      formData.append("chunk_config", JSON.stringify(chunkConfig));
    }
    return fetch(`${API_BASE}/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      credentials: "include",
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(res.status, err.detail || "Upload failed");
      }
      return res.json() as Promise<SampleReport>;
    });
  },

  deleteDoc: (kbId: string, docId: string) =>
    request<MessageResponse>(`/knowledge-bases/${kbId}/documents/${docId}`, { method: "DELETE" }),

  // Batch upload
  uploadDocs: async (
    kbId: string,
    files: File[],
    chunkConfig?: ChunkConfig,
    onProgress?: (current: number, total: number) => void
  ) => {
    const results: SampleReport[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file) continue;
      const result = await kfApi.uploadDoc(kbId, file, chunkConfig);
      results.push(result);
      onProgress?.(i + 1, files.length);
    }
    return results;
  },

  // Sample reports (aggregated document list)
  listSampleReports: (params?: {
    kb_id?: string;
    skip?: number;
    limit?: number;
    status?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.kb_id) query.set("kb_id", params.kb_id);
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.status) query.set("status", params.status);
    return request<SampleReportListResponse>(`/knowledge-factory/reports?${query}`);
  },

  getSampleReport: (reportId: string) =>
    request<SampleReport>(`/knowledge-factory/reports/${reportId}`),

  updateSampleReport: (reportId: string, data: { quality_score?: number; template_version?: string }) =>
    request<SampleReport>(`/knowledge-factory/reports/${reportId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteSampleReport: (reportId: string) =>
    request<MessageResponse>(`/knowledge-factory/reports/${reportId}`, { method: "DELETE" }),

  syncReportStatus: (reportId: string) =>
    request<{ status: string; progress?: number }>(`/knowledge-factory/reports/${reportId}/sync`),

  // ============== Knowledge Factory: Extraction ==============

  // Domains
  listDomains: () =>
    kfRequest<{ domains: ExtractionDomain[]; total: number }>("/domains"),

  // Extraction tasks
  createTask: (data: ExtractionTaskCreate) =>
    kfRequest<ExtractionTaskResponse>("/extraction/tasks", { method: "POST", body: JSON.stringify(data) }),

  listTasks: (params?: { page?: number; limit?: number; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.status) query.set("status", params.status);
    return kfRequest<ExtractionTaskListResponse>(`/extraction/tasks?${query}`);
  },

  getTask: (taskId: string) =>
    kfRequest<ExtractionTaskResponse>(`/extraction/tasks/${taskId}`),

  pauseTask: (taskId: string) =>
    kfRequest<{ message: string }>(`/extraction/tasks/${taskId}/pause`, { method: "POST" }),

  resumeTask: (taskId: string) =>
    kfRequest<{ message: string }>(`/extraction/tasks/${taskId}/resume`, { method: "POST" }),

  cancelTask: (taskId: string) =>
    kfRequest<{ message: string }>(`/extraction/tasks/${taskId}/cancel`, { method: "POST" }),

  rerunTask: (taskId: string) =>
    kfRequest<ExtractionTaskResponse>(`/extraction/tasks/${taskId}/rerun`, { method: "POST" }),

  // Template management
  listTemplates: (params?: {
    page?: number;
    limit?: number;
    domain?: string;
    status?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.domain) query.set("domain", params.domain);
    if (params?.status) query.set("status", params.status);
    return kfRequest<TemplateListResponse>(`/templates?${query}`);
  },

  getTemplate: (templateId: string) =>
    kfRequest<TemplateDocument>(`/templates/${templateId}`),

  updateTemplate: (templateId: string, data: Partial<TemplateDocument>) =>
    kfRequest<{ message: string; id: string }>(`/templates/${templateId}`, { method: "PUT", body: JSON.stringify(data) }),

  publishTemplate: (templateId: string) =>
    kfRequest<{ message: string; id: string }>(`/templates/${templateId}/publish`, { method: "POST" }),

  deleteTemplate: (templateId: string) =>
    kfRequest<{ message: string }>(`/templates/${templateId}`, { method: "DELETE" }),

  exportTemplate: (templateId: string) => `${KF_API_BASE}/templates/${templateId}/export`,

  getTemplateVersions: (templateId: string) =>
    kfRequest<TemplateVersionResponse[]>(`/templates/${templateId}/versions`),
};
