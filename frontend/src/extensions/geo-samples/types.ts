// EAI-CUSTOM: geo-sample-bank Phase 1 (spec 2026-09-01).
// Mirrors backend app/extensions/geo_samples/schemas.py DocumentOut/RedactionOut/RunOut.
export type GsbStatus = "uploaded" | "parsed" | "redacted" | "reviewed" | "failed";
export type GsbStage = "survey" | "detail" | "exploration";

export interface GsbDocument {
  id: string;
  report_id: string;
  file_name: string;
  file_type: string;
  stage: GsbStage;
  mineral: string;
  year: number | null;
  region: string | null;
  status: GsbStatus;
  parse_mode: string | null;
  redaction_summary: string | null;
  review_note: string | null;
  created_at: string;
}

export interface GsbRedaction {
  id: string;
  rule: string;
  mode: "auto" | "review";
  start: number;
  end: number;
  original_hash: string;
}

export interface GsbRun {
  id: string;
  document_id: string | null;
  run_type: "parse" | "redact";
  status: "running" | "done" | "failed";
  detail: string | null;
  created_at: string;
  finished_at: string | null;
}
