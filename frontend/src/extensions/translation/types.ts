/**
 * Types for the translation workbench (EAI-CUSTOM).
 */

export type TltState =
  | "stored"
  | "pending"
  | "running"
  | "check_failed"
  | "retrying"
  | "exceeded"
  | "indexed"
  | "delivered"
  | "archived"
  | "failed"
  | "cancelled"
  | "superseded";

export interface TltFolder {
  id: string;
  parent_id: string | null;
  name: string;
}

export interface TltTask {
  id: string;
  kb_id: string;
  document_id: string | null;
  doc_sha: string;
  source_lang: string;
  content_tag: string | null;
  state: TltState;
  quality_tier: string;
  progress: number;
  retry_count: number;
  task_version: number;
  gate_failures: Record<string, string[]> | null;
  error_detail: Record<string, unknown> | null;
  superseded_by: string | null;
  folder_id: string | null;
  deliverable_uri: string | null;
  ragflow_zh_doc_id: string | null;
  file_name: string;
  size_bytes: number | null;
  created_at: string | null;
  updated_at: string | null;
  source_uri: string | null;
  kb_name: string | null;
  uncertainty: { block: string; spans: string[] }[] | null;
}

export interface TltTaskPage {
  items: TltTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface TltUploadResult {
  task_id: string;
  file: string;
  reused: boolean;
  /** reused=true 时：已有任务的原文件名（供 UI 明确告知用户）。 */
  existing_file?: string | null;
  /** reused=true 时：已有任务所在文件夹（null=根）。 */
  existing_folder_id?: string | null;
}
