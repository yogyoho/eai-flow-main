// EAI-CUSTOM: geo-sample-bank Phase 1 (spec 2026-09-01).
// Mirrors backend app/extensions/geo_samples/schemas.py DocumentOut/RedactionOut/RunOut.
export type GsbStatus =
  | "uploaded"
  | "parsed"
  | "redacted"
  | "reviewed"
  | "failed"
  | "compiled"; // Phase 2 编译态（service.run_compile 写回；Phase 1 类型镜像漏更，T4 删除按钮守卫首次比对暴露）
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

// ore_pack 孵化草稿（P5 T6）——镜像 backend GsbOrePackDraft + crud.draft_payload
// （draft_json/errors 为 JSON 解码后的对象/数组；失败草稿 draft_json=null）。
export interface GsbOrePackDraft {
  id: string;
  mineral: string;
  slices_hash: string;
  draft_json: Record<string, unknown> | null;
  errors: string[];
  review_status: "draft" | "approved" | "rejected";
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

// approve 响应在草稿字段之上附加 repo 落盘路径 + standards_index 扩容义务清单。
export interface GsbOrePackApproveResult extends GsbOrePackDraft {
  written: string;
  standards_index_obligations: string[];
}
