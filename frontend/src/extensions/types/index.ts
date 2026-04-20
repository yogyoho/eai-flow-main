export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  role_id?: string;
  role_name?: string;
  dept_id?: string;
  dept_name?: string;
  status: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string;
  phone?: string;
  emp_no?: string;
  hire_date?: string;
  dept_id?: string;
  dept_name?: string;
  dept_ids?: string[];
  primary_dept_id?: string;
  role_id?: string;
  role_name?: string;
  status: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  users: User[];
  total: number;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
  phone?: string;
  emp_no?: string;
  hire_date?: string;
  dept_id?: string;
  dept_ids?: string[];
  role_id?: string;
}

export interface UpdateUserRequest {
  email?: string;
  full_name?: string;
  phone?: string;
  emp_no?: string;
  hire_date?: string;
  dept_id?: string;
  dept_ids?: string[];
  role_id?: string;
  status?: string;
  is_deleted?: boolean;
}

export interface Role {
  id: string;
  name: string;
  code: string;
  permissions: string[];
  is_system: boolean;
  description?: string;
  level?: number;
  parent_role_id?: string;
  parent_role_name?: string;
  created_at: string;
}

export interface RoleListResponse {
  roles: Role[];
  total: number;
}

export interface CreateRoleRequest {
  name: string;
  code: string;
  permissions?: string[];
  description?: string;
  level?: number;
  parent_role_id?: string;
}

export interface UpdateRoleRequest {
  name?: string;
  permissions?: string[];
  description?: string;
  level?: number;
  parent_role_id?: string;
}

export interface RoleHierarchyResponse {
  role: Role;
  ancestors: Role[];
  inherited_permissions: string[];
  direct_permissions: string[];
  all_permissions: string[];
}

export interface Department {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  leader_id?: string;
  leader_name?: string;
  sort_order: number;
  code?: string;
  status?: string;
  created_at: string;
  children?: Department[];
}

export interface DepartmentListResponse {
  departments: Department[];
  total: number;
}

export interface CreateDepartmentRequest {
  name: string;
  description?: string;
  parent_id?: string;
  leader_id?: string;
  sort_order?: number;
  code?: string;
  status?: string;
}

export interface UpdateDepartmentRequest {
  name?: string;
  description?: string;
  parent_id?: string;
  leader_id?: string;
  sort_order?: number;
  code?: string;
  status?: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string;
  ragflow_dataset_id?: string;
  owner_id: string;
  owner_name?: string;
  access_type: string;
  /** 知识库类型：ragflow | pageindex（旧数据可能缺省，前端按 ragflow 展示） */
  kb_type?: string;
  allowed_depts?: string[];
  embedding_model?: string;
  chunk_method: string;
  status: string;
  created_at: string;
}

export interface KnowledgeBaseListResponse {
  knowledge_bases: KnowledgeBase[];
  total: number;
}

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  access_type?: string;
  kb_type?: string;
  allowed_depts?: string[];
  embedding_model?: string;
  chunk_method?: string;
}

export interface UpdateKnowledgeBaseRequest {
  name?: string;
  description?: string;
  access_type?: string;
  kb_type?: string;
  allowed_depts?: string[];
  embedding_model?: string;
  chunk_method?: string;
}

export interface Document {
  id: string;
  knowledge_base_id: string;
  name: string;
  file_path: string;
  file_size: number;
  file_type?: string;
  ragflow_document_id?: string;
  status: string;
  error_message?: string;
  created_at: string;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
}

export interface CreateDocumentRequest {
  file: File;
}

export interface RAGChatRequest {
  query: string;
  top_k?: number;
  similarity_threshold?: number;
  vector_similarity_weight?: number;
}

export interface RAGChatResponse {
  answer: string;
  sources: Array<{
    content: string;
    document_name?: string;
    document_id?: string;
    score?: number;
  }>;
}

export interface KnowledgeBaseStatus {
  status: string;
  document_count?: number;
  chunk_count?: number;
  message?: string;
}

export interface MessageResponse {
  message: string;
  success?: boolean;
}

export interface Conversation {
  id: string;
  thread_id: string;
  user_id: string;
  title?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface CreateConversationRequest {
  title?: string;
  thread_id?: string;
}

export interface UpdateConversationRequest {
  title?: string;
  status?: string;
}

// ============== AI Document Types ==============

export interface AIDocument {
  id: string;
  user_id: string;
  source_thread_id?: string;
  title: string;
  content?: string;
  folder: string;
  is_starred: boolean;
  is_shared: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AIDocumentListResponse {
  documents: AIDocument[];
  total: number;
}

export interface CreateAIDocumentRequest {
  title: string;
  content?: string;
  folder?: string;
  source_thread_id?: string;
}

export interface UpdateAIDocumentRequest {
  title?: string;
  content?: string;
  folder?: string;
  is_starred?: boolean;
  is_shared?: boolean;
  status?: string;
}

export interface FolderListResponse {
  folders: string[];
}

// ============== Knowledge Factory Types ==============

/**
 * 知识库业务类型
 */
export type KBBusinessType =
  | "sample_reports" // 样例报告库
  | "template_library" // 报告模板库
  | "laws_regulations"; // 法规标准库

/**
 * RAGFlow 分块方法
 */
export type ChunkMethod = "naive" | "report" | "paper" | "laws" | "book" | "qa";

/**
 * 报告类型（配合 report 分块方法）
 */
export type ReportType = "general" | "engineering_report";

/**
 * 分块配置
 */
export interface ChunkConfig {
  /** 分块方法 */
  chunk_method: ChunkMethod;
  /** 报告类文档专用 */
  report_type?: ReportType;
  /** 标题识别深度 (1-6)，默认3 */
  heading_depth?: number;
  /** 是否包含页码溯源，默认 true */
  include_page_index?: boolean;
  /** 每块token数，默认128 */
  chunk_token_num?: number;
  /** 自定义分隔符 */
  delimiter?: string;
  /** 是否保留表格，默认 true */
  preserve_tables?: boolean;
  /** 是否启用OCR，默认 true */
  ocr_enabled?: boolean;
  /** 是否自动解析，默认 true */
  auto_parse?: boolean;
}

/**
 * 样例报告（扩展自 Document）
 */
export interface SampleReport extends Document {
  /** 关联的知识库名称 */
  knowledge_base_name?: string;
  /** 质量评分 */
  quality_score?: number;
  /** 章节数 */
  chapters?: number;
  /** 节数 */
  sections?: number;
  /** 关联的模板版本 */
  template_version?: string;
  /** 解析进度 (0-100) */
  parse_progress?: number;
}

/**
 * 样例报告列表响应
 */
export interface SampleReportListResponse {
  reports: SampleReport[];
  total: number;
}

/**
 * 知识库创建请求（扩展）
 */
export interface CreateKnowledgeBaseRequestExtended extends CreateKnowledgeBaseRequest {
  /** 业务类型 */
  business_type?: KBBusinessType;
  /** 分块配置 */
  chunk_config?: ChunkConfig;
}

/**
 * 知识库响应（扩展）
 */
export interface KnowledgeBaseExtended extends KnowledgeBase {
  /** 业务类型 */
  business_type?: KBBusinessType;
  /** 文档数量 */
  document_count?: number;
  /** 分块数量 */
  chunk_count?: number;
}

// ============== Document Status（与后端 schemas.py DocumentStatus 枚举对齐）==============

/**
 * 文档状态常量，与后端 DocumentStatus 枚举一一对应。
 * 所有前端状态判断统一引用此处，请勿硬编码字符串。
 */
export const DocumentStatus = {
  PENDING: "pending",
  UPLOADING: "uploading",
  PROCESSING: "processing",
  SUCCESS: "success",
  DONE: "done",
  COMPLETED: "completed",
  PARSED: "parsed",
  FAILED: "failed",
} as const;

export type DocumentStatusValue = (typeof DocumentStatus)[keyof typeof DocumentStatus];

/**
 * 判断后端返回的任意 status 值是否为「解析完成，可供抽取等下游操作使用」。
 * 对应后端 schemas.is_doc_ready()。
 */
export function isDocumentReady(status: string | undefined): boolean {
  if (!status) return false;
  const s = String(status).toLowerCase().trim();
  return (
    s === DocumentStatus.SUCCESS
    || s === DocumentStatus.DONE
    || s === DocumentStatus.COMPLETED
    || s === DocumentStatus.PARSED
    || s === "1" // RAGFlow 部分版本返回数字 "1" 表示解析完成
  );
}

/**
 * 将后端/RAGFlow 返回的任意 status 值归一化为 DocumentStatus 值。
 * 对应后端 schemas.to_doc_status()。
 */
export function normalizeDocStatus(raw: string | undefined | null): DocumentStatusValue {
  if (!raw) return DocumentStatus.PENDING;
  const s = String(raw).toLowerCase().trim();
  const mapping: Record<string, DocumentStatusValue> = {
    "1": DocumentStatus.SUCCESS,
    done: DocumentStatus.DONE,
    completed: DocumentStatus.COMPLETED,
    parsed: DocumentStatus.PARSED,
    success: DocumentStatus.SUCCESS,
    fail: DocumentStatus.FAILED,
    failed: DocumentStatus.FAILED,
    uploading: DocumentStatus.UPLOADING,
    processing: DocumentStatus.PROCESSING,
  };
  return mapping[s] ?? DocumentStatus.PENDING;
}

// ============== Web Scraper Types ==============

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
