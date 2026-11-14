/**
 * bid-write API 类型（P0-M0 F1 响应矩阵 + M1 断言摘要）。
 *
 * 字段名严格镜像后端 `backend/app/extensions/bid_write/schemas.py` 与
 * `routers.py` 的实际返回（snake_case）。本模块只展示后端已有数据：
 * 生成正文、素材实体库、报价计算内核尚未落地时不伪造业务值。
 */

import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

export interface MatrixCounts {
  total: number;
  star: number;
  blocked: number;
}

export interface TenderDocEntry {
  name?: string;
  filename?: string;
  doc_id?: string;
  role?: string;
  status?: string;
  path?: string;
}

export interface WriteTaskEngineMeta {
  docs?: TenderDocEntry[];
  schema_version?: string;
  matrix_counts?: MatrixCounts;
  provenance?: Record<string, unknown>;
  fields_conf?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WriteTaskOut {
  id: string;
  biz_no: string | null;
  status: string;
  progress: Record<string, unknown>;
  error: string | null;
  project_name: string | null;
  lot_name: string | null;
  tender_no: string | null;
  created_at: string | null;
  engine_meta: WriteTaskEngineMeta;
}

export interface WriteTaskListResponse {
  items: WriteTaskOut[];
}

export interface MatrixRowOut {
  clause_id: string;
  kind: string;
  source_path: string;
  requirement: string;
  star: boolean;
  strategy: string;
  target_section: string;
  evidence_refs: unknown[];
  status: string;
  conf: number | null;
  verified: boolean;
  note: string;
}

export interface MatrixVocab {
  strategies: string[];
  statuses: string[];
  kinds: string[];
}

export interface MatrixResponse {
  items: MatrixRowOut[];
  schema_version: string;
  vocab: MatrixVocab;
}

export interface MatrixRowPatch {
  strategy?: string;
  status?: string;
  target_section?: string;
  note?: string;
  evidence_refs?: unknown[];
}

export interface GapItem {
  clause_id: string;
  kind: string;
  requirement: string;
  star: boolean;
  status: string;
  material_state: string;
  evidence_refs: unknown[];
}

export interface AssertionPendingItem {
  assertion_id: string;
  skill: string;
  status: string;
  message: string;
  human_action: string | null;
}

export interface AssertionSkippedItem {
  assertion_id: string;
  level: string;
  skipped_reason: string | null;
  message: string;
}

export interface AssertionsSummary {
  run_at: string | null;
  skills: string[] | null;
  schema_version: string;
  blocked: boolean;
  pending: AssertionPendingItem[];
  skipped: AssertionSkippedItem[];
}

export interface GapsResponse {
  items: GapItem[];
  summary: {
    total: number;
    material_ready: number;
    pending_note?: string;
  };
  assertions: AssertionsSummary | null;
}

export interface RegistryLevel {
  name?: string;
  blk?: boolean;
  render?: string;
  todo?: string;
  pre_review_state?: string;
  retry?: string;
  [key: string]: unknown;
}

export interface RegistryAssertion {
  id: string;
  skill: string;
  name: string;
  level: string;
  blocks_export: boolean;
  rule_ref: string | null;
  expr: string;
  human_action: string | null;
  delegates_to: string | null;
}

export interface RegistryResponse {
  schema_version: string;
  levels: Record<string, RegistryLevel>;
  items: RegistryAssertion[];
}

// ── 批廿五 P1-δ:生成/导出门禁/素材/policy/metrics 面(字段=后端
// schemas.py / routers.py 返回逐一对照,snake_case 直透)──────────────────

export interface GenerateKnobs {
  unit_prices?: Record<string, string>;
  sign_date?: string;
  price_note?: string;
  general_commitments?: { text: string; clause_id: string }[];
  page_estimates?: Record<string, number>;
  total_pages?: number;
  warranty_period?: string;
}

export interface L4Issue {
  rule_id: string;
  verdict: string;
  severity?: string;
  reason?: string;
  evidence?: unknown[];
  [key: string]: unknown;
}

/** L4 语义审查面(advisory-only;run_l4_review 返回形)。 */
export interface L4Face {
  executed: boolean;
  counts: Record<string, number>;
  issues: L4Issue[];
  participants: string[];
  input_missing: string[];
  watermark_removed: boolean;
  scope_note: string;
}

/** run_export_gate 返回形(watermark=null=L4 审查通过已摘除)。 */
export interface ExportGateResponse {
  blocked: boolean;
  reasons: string[];
  watermark: string | null;
  assertion_counts: Record<string, number>;
  rule_counts: Record<string, number>;
  l1_fatal_fail: string[];
  l4: L4Face | null;
  scope_note: Record<string, unknown>;
  schema_version: string;
  results: unknown[];
  metrics?: MetricsFace;
}

export interface GenerateResponse {
  verdict: ExportGateResponse;
  blocked: boolean;
  biz_no: string | null;
  status: string;
}

export interface MaterialOut {
  id: string;
  entity_type: string;
  name: string;
  fields: Record<string, unknown>;
  evidence_refs: unknown[];
  verifiable: boolean;
  created_at: string | null;
}

export interface MaterialIn {
  entity_type: string;
  name: string;
  fields?: Record<string, unknown>;
  evidence_refs?: unknown[];
}

export interface MaterialPatch {
  name?: string;
  fields?: Record<string, unknown>;
  evidence_refs?: unknown[];
}

export interface PolicyBody {
  letter_defaults?: { validity_days?: number; sign_date?: string } | null;
  tax_rate?: number | null;
  price_adjust_mechanism?: boolean | null;
}

export interface MetricsFace {
  slot_fill_rate: number | null;
  assertion_pass_rate: number | null;
  d0_count: number;
  d1_count: number;
  manual_edit_ratio: number | null;
  latency_ms: number;
  retry_count: number;
  note?: string;
}

export interface TaskMetricsResponse {
  metrics: MetricsFace | null;
  run_at: string | null;
}

export interface BoqItem {
  id: string;
  name: string;
  qty: number | string;
  unit: string;
}

/** 正文 AST 存储(批廿八 M2;GET 未保存 ast=null 诚实面,PUT 全量幂等)。 */
export interface TaskDocumentResponse {
  ast: AstJsonNode | null;
  schema_version: string;
  updated_at: string | null;
}

// ── 批三十二:不可变修订 + workflow subject 审批面 ─────────────────────────

export interface ApprovalRevision {
  id: string;
  revision_no: number;
  status: string;
  doc_hash: string;
  schema_version: string;
  assertion_snapshot: Record<string, unknown>;
  approval_instance_id: string | null;
  hash_ok: boolean;
  created_at: string | null;
  submitted_at: string | null;
  decided_at: string | null;
}

export interface ApprovalReview {
  id: string;
  node_id: string;
  node_label: string;
  reviewer_id: string;
  reviewer_role: string;
  sequence: number;
  status: string;
  comment: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApprovalInstance {
  instance_id: string;
  status: string;
  current_node_id: string | null;
  current_node_label: string;
  gate_mode: string;
  definition_id: string | null;
  workflow_source: string;
  label: string | null;
  created_by: string;
  created_at: string | null;
  decided_at: string | null;
  can_act: boolean;
  my_review: {
    id: string;
    node_id: string;
    reviewer_id: string;
    status: string;
    comment: string | null;
  } | null;
  reviews: ApprovalReview[];
}

export interface TaskApprovalResponse {
  revision: ApprovalRevision | null;
  approval: ApprovalInstance | null;
  revisions: ApprovalRevision[];
  is_owner: boolean;
}

// ── 批三十三:批准修订 DOCX 交付包 ─────────────────────────────────────────

export interface ExportRecord {
  id: string;
  revision_id: string;
  doc_hash: string;
  bundle_sha256: string;
  file_count: number;
  total_bytes: number;
  watermark: string | null;
  created_at: string | null;
}

export interface ExportHistoryResponse {
  items: ExportRecord[];
}

export interface ExportDownload {
  blob: Blob;
  filename: string;
  exportId: string;
  sha256: string;
  fileCount: number;
  totalBytes: number;
  watermarked: boolean;
}

export interface ApprovalSubmitInput {
  ast: AstJsonNode;
  schema_version: string;
  document_hash?: string;
  workflow_definition_id?: string;
  reviewer_ids?: string[];
  gate_mode?: string;
  ratio_threshold?: number;
  label?: string;
  comment?: string;
}

export interface ApprovalActionInput {
  instance_id: string;
  action: "approved" | "rejected";
  comment?: string;
}
