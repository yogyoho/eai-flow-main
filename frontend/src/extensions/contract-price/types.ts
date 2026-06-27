/**
 * TypeScript types for the contract-price-analysis API (v2).
 * Field names mirror the backend Pydantic/ORM models (snake_case) exactly.
 * v2: MinIO-backed documents (drop ragflow_doc_id) + item traceability/validation.
 */

export interface CpaDocument {
  id: string;
  file_name: string;
  storage_uri: string;
  file_hash: string;
  file_type: string;
  contract_no: string | null;
  supplier: string | null;
  sign_date: string | null;
  parse_mode: string;
  parse_status: string; // pending / parsed / failed / needs_review
  parse_meta: Record<string, unknown> | null;
  error: string | null;
  page_count: number | null;
  preview_prefix: string | null;
  parsed_at: string | null;
  created_at: string;
}

export interface CpaItem {
  id: string;
  document_id: string;
  goods_name: string;
  spec_model: string | null;
  tech_params: Record<string, string> | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  price_untaxed: number | null;
  cluster_id: string | null;
  source_contract_no: string | null;
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
  created_at: string;
}

export interface CpaCluster {
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

export interface CpaClusterDetail extends CpaCluster {
  items: CpaItem[];
}

export interface CpaRun {
  id: string;
  trigger_type: string;
  status: string; // running | completed | failed
  docs_processed: number;
  items_extracted: number;
  clusters_formed: number;
  duration_ms: number | null;
  excel_path: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface CpaDashboard {
  contract_count: number;
  item_count: number;
  cluster_count: number;
  pending_cluster_count: number;
  confirmed_cluster_count: number;
  price_range: { min: number; max: number; avg: number } | null;
  recent_runs: CpaRun[];
}

export interface CpaConfig {
  parse_mode: string;
  cluster_eps: number;
  cluster_min_samples: number;
  scheduled_enabled: boolean;
  schedule_cron: string | null;
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
  error: string | null;
}

export interface UploadResponse {
  storage_uri: string;
  file_name: string;
  size: number;
}
