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

export type KBBusinessType = "sample_reports" | "template_library" | "laws_regulations";
export type ChunkMethod = "naive" | "report" | "paper" | "laws" | "book" | "qa";
export type ReportType = "general" | "engineering_report";

export interface ChunkConfig {
  chunk_method: ChunkMethod;
  report_type?: ReportType;
  heading_depth?: number;
  include_page_index?: boolean;
  chunk_token_num?: number;
  delimiter?: string;
  preserve_tables?: boolean;
  ocr_enabled?: boolean;
  auto_parse?: boolean;
}

export interface SampleReport extends Document {
  knowledge_base_name?: string;
  quality_score?: number;
  chapters?: number;
  sections?: number;
  template_version?: string;
  parse_progress?: number;
}

export interface SampleReportListResponse {
  reports: SampleReport[];
  total: number;
}

export interface CreateKnowledgeBaseRequestExtended extends CreateKnowledgeBaseRequest {
  business_type?: KBBusinessType;
  chunk_config?: ChunkConfig;
}

export interface KnowledgeBaseExtended extends KnowledgeBase {
  business_type?: KBBusinessType;
  document_count?: number;
  chunk_count?: number;
}

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

export function isDocumentReady(status: string | undefined): boolean {
  if (!status) return false;
  const s = String(status).toLowerCase().trim();
  return (
    s === DocumentStatus.SUCCESS
    || s === DocumentStatus.DONE
    || s === DocumentStatus.COMPLETED
    || s === DocumentStatus.PARSED
    || s === "1"
  );
}

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
