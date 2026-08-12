/**
 * TypeScript types for the spare-parts-analysis API (v2).
 * 字段名与后端 Pydantic/ORM 模型(snake_case)一一对应。
 * v2: MinIO 文档(去 ragflow_doc_id)+ 明细溯源/校验 + 客户维度(D3)。
 */

export interface CspDocument {
  id: string;
  file_name: string;
  storage_uri: string;
  file_hash: string;
  file_type: string;
  contract_no: string | null;
  supplier: string | null;
  customer_id: string | null;
  customer_name: string | null;
  project_name: string | null;
  project_location: string | null;
  sign_date: string | null;
  parse_mode: string;
  parse_status: string; // pending / parsed / failed / needs_review
  confirm_status: string; // pending / confirmed / skipped / clustered
  parse_meta: Record<string, unknown> | null;
  error: string | null;
  page_count: number | null;
  preview_prefix: string | null;
  parsed_at: string | null;
  created_at: string;
}

export interface CspItem {
  id: string;
  document_id: string;
  part_name: string;
  spec: string | null;
  tech_params: Record<string, string> | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  price_untaxed: number | null;
  cluster_id: string | null;
  source_contract_no: string | null;
  customer_id: string | null;
  customer_name: string | null;
  is_outlier: boolean;
  // traceability (page-relative bbox 0~1)
  source_page: number | null;
  source_bbox: number[] | null;
  source_table_idx: number | null;
  source_row_idx: number | null;
  // validation (scanned-contract OCR)
  confidence: number | null;
  validation_status: string; // ok / needs_review / corrected
  edit_note: string | null;
  run_id: string | null;
  created_at: string;
}

export interface CspCluster {
  id: string;
  category: string;
  representative_name: string;
  status: string; // pending | confirmed | rejected
  stats: Record<string, number | null> | null;
  item_count: number;
  version: number;
  confirmed_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CspClusterDetail extends CspCluster {
  items: CspItem[];
}

export interface CspRun {
  id: string;
  trigger_type: string;
  label: string | null;
  status: string; // running | completed | failed
  docs_processed: number;
  items_extracted: number;
  clusters_formed: number;
  duration_ms: number | null;
  customers_resolved: number;
  error: string | null;
  scope: Record<string, unknown> | null;
  progress: { total: number; done: number; failed: number; phase?: string; processing?: string[] } | null;
  started_at: string;
  finished_at: string | null;
}

export interface CspDashboardCharts {
  top_goods: { name: string; item_count: number; avg_price: number }[];
  price_ranges: { range: string; count: number }[];
  validation: { status: string; count: number }[];
  cluster_sizes: { range: string; count: number }[];
  by_customer: { name: string; count: number; avg_price: number; min: number; max: number }[];
}

export interface CspDashboard {
  contract_count: number;
  item_count: number;
  cluster_count: number;
  customer_count: number;
  pending_cluster_count: number;
  confirmed_cluster_count: number;
  outlier_count: number;
  price_range: { min: number; max: number; avg: number } | null;
  charts: CspDashboardCharts | null;
  recent_runs: CspRun[];
}

export interface CspConfig {
  parse_mode: string;
  cluster_eps: number;
  cluster_min_samples: number;
  scheduled_enabled: boolean;
  schedule_cron: string | null;
  price_table_keywords: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export interface PipelineRunResponse {
  run_id: string;
  status: string;
  message: string;
}

export interface PipelineStatus {
  run_id: string;
  status: string;
  docs_processed: number;
  items_extracted: number;
  clusters_formed: number;
  customers_resolved: number;
  error: string | null;
}

export interface UploadResponse {
  storage_uri: string;
  file_name: string;
  size: number;
}

// --- 客户维度 (D3: master/alias 归并) ---

export interface CspCustomer {
  id: string;
  canonical_name: string;
  aliases: string[];
  source: string | null;
  status: string; // active | pending | merged
  merged_into: string | null;
  doc_count: number;
  created_at: string;
  updated_at: string;
}

export interface CspCustomerCreate {
  canonical_name: string;
  aliases: string[];
}

export interface CspCustomerUpdate {
  canonical_name?: string;
  aliases?: string[];
}

export interface CspCustomerResolveResult {
  raw_name: string;
  customer_id: string | null;
}

/** 明细按客户聚合(GET /items/customers)。 */
export interface CspItemCustomer {
  customer_id: string | null;
  customer_name: string;
  count: number;
}
