/**
 * 形式化内核 /formal/* 数据适配层（kernel P5 服务面, EAI-CUSTOM）.
 *
 * 推理工作台（infer）/ 校验中心（validate = SHACL + 国标五项）/ 导出互操作（export
 * Turtle|JSON-LD）三页的数据源。路径均为扩展内相对路径（authFetch base =
 * /api/ontostudio/api/extensions，见 @/lib/api——全路径会产生双前缀）。
 */
import { authFetch } from "@/lib/api";

const BASE = "/ontology/formal";

// ---- infer ----

export interface InferStats {
  success: boolean;
  input_triples: number;
  entailment_triples: number;
  filtered_low_confidence: number;
  rule_counts: Record<string, number>;
  duration_ms: number;
  errors: string[];
}

export function runFormalInfer(minConfidence = 0.7): Promise<InferStats> {
  return authFetch<InferStats>(`/formal/infer?min_confidence=${minConfidence}`, {
    method: "POST",
  });
}

// ---- validate ----

export interface ShaclViolation {
  focusNode: string | null;
  path: string | null;
  message: string | null;
  severity: string | null;
  source: string | null;
}

export interface ShaclReport {
  conforms: boolean;
  violations: ShaclViolation[];
  duration_ms: number;
}

/** 国标 GB/T 48000.3 单项符合性检查结果（条款 5.3/5.4/附录 A/条款 9）。 */
export interface ConformanceCheck {
  name: string;
  clause: string;
  passed: boolean;
  detail: string;
}

export interface FormalValidateResult {
  success: boolean;
  shacl: ShaclReport;
  conformance: ConformanceCheck[];
}

export function fetchFormalValidate(): Promise<FormalValidateResult> {
  return authFetch<FormalValidateResult>("/formal/validate");
}

// ---- export ----

export type ExportFormat = "turtle" | "json-ld";
export type ExportGraphs = "all" | "schema" | "asserted" | "entailment";

/** Turtle 返回纯文本（authFetch 只会解析 JSON，这里单走 fetch）。 */
export async function fetchFormalExportText(
  format: ExportFormat,
  graphs: ExportGraphs,
): Promise<string> {
  const response = await fetch(
    `/api/ontostudio/api/extensions${BASE}/export?format=${format}&graphs=${graphs}`,
    { credentials: "include" },
  );
  if (!response.ok) {
    throw new Error(`导出失败（${response.status}）`);
  }
  return response.text();
}

/** JSON-LD 端点包了 {success, document} 信封，走 authFetch。 */
export function fetchFormalExportJsonld(
  graphs: ExportGraphs = "schema",
): Promise<{ success: boolean; document: unknown }> {
  return authFetch(`/formal/export?format=json-ld&graphs=${graphs}`);
}

/** 浏览器侧下载（blob + 隐式锚点，导出互操作页"下载"按钮）。 */
export function downloadText(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
