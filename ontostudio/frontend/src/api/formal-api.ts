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

export function runFormalInfer(minConfidence = 0.7, dry = false): Promise<InferStats> {
  return authFetch<InferStats>(
    `${BASE}/infer?min_confidence=${minConfidence}${dry ? "&dry=true" : ""}`,
    { method: "POST" },
  );
}

// ---- CQ 验收（F5，2026-10-02）----

/** 单条 CQ 结果：ASK 真跑于内核，passed = actual === expected。 */
export interface CqResult {
  id: string;
  question: string;
  expected: boolean;
  actual: boolean;
  passed: boolean;
  error?: string;
}

export function runCqs(): Promise<{ results: CqResult[] }> {
  return authFetch<{ success: boolean; results: CqResult[] }>(`${BASE}/cq/run`, {
    method: "POST",
  });
}

// ---- 规则源码（F1）/ 派生下钻（F2）----

export type RuleOrigin = "yaml" | "builtin" | "chain";

export interface RuleSource {
  name: string;
  /** 自包含 CONSTRUCT 查询（含 PREFIX）。 */
  construct: string;
  origin: RuleOrigin;
  /** F8：false = 已停用（rules_state overlay）。 */
  enabled: boolean;
}

export function fetchFormalRules(): Promise<{ rules: RuleSource[] }> {
  return authFetch<{ success: boolean; rules: RuleSource[] }>(`${BASE}/rules`);
}

/** F8 规则启停：启用即单规则重算、停用即撤派生图。 */
export function setRuleEnabled(name: string, enabled: boolean): Promise<{ rule: string; enabled: boolean; count: number }> {
  return authFetch(`${BASE}/rules/${encodeURIComponent(name)}/enabled`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

/** F9 推理历史行（ts 倒序由后端保证）。 */
export interface InferHistoryRow {
  ts: string;
  min_conf: number;
  input_triples: number;
  entailment_triples: number;
  rule_counts: Record<string, number>;
  duration_ms: number;
}

export function fetchInferHistory(limit = 20): Promise<{ history: InferHistoryRow[] }> {
  return authFetch(`${BASE}/history?limit=${limit}`);
}

export interface DerivationRow {
  s: string;
  p: string;
  o: string;
}

export function fetchRuleDerivations(
  name: string,
  limit = 200,
  offset = 0,
): Promise<{ total: number; rows: DerivationRow[] }> {
  return authFetch(
    `${BASE}/rules/${encodeURIComponent(name)}/derivations?limit=${limit}&offset=${offset}`,
  );
}

// ---- 单三元组溯源（F3，2026-10-02 二期）----

export interface TraceEvidence {
  s: string;
  p: string;
  o: string;
}

export interface RuleTrace {
  rule: string;
  kind: "chain" | "requirements" | "sameas";
  satisfied: boolean;
  evidence: TraceEvidence[];
  /** requirements 类：资质满足对照。 */
  details?: Array<{ qualification: string; held: boolean }>;
  /** F4 反事实：断裂位置与提示。 */
  missing_at?: number;
  missing_pred?: string;
  reached?: string;
  hint?: string;
}

export function fetchRuleTrace(name: string, s: string, p: string, o: string): Promise<RuleTrace> {
  return authFetch(
    `${BASE}/rules/${encodeURIComponent(name)}/trace?s=${encodeURIComponent(s)}&p=${encodeURIComponent(p)}&o=${encodeURIComponent(o)}`,
  );
}

/** F4 反事实：期望派生 (s, *, o) 未出现时，逐段定位断言图断裂点。 */
export function fetchRuleExplainMiss(name: string, s: string, o: string): Promise<RuleTrace> {
  return authFetch(
    `${BASE}/rules/${encodeURIComponent(name)}/explain-miss?s=${encodeURIComponent(s)}&o=${encodeURIComponent(o)}`,
  );
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
  return authFetch<FormalValidateResult>(`${BASE}/validate`);
}

// ---- load（全量装载 = 对账，人审闭环切片语义）----

export interface FormalLoadResult {
  success: boolean;
  entities: number;
  relations: number;
  mentions: number;
  deduped_entities: number;
  skipped_entities: string[];
  skipped_relations: string[];
  skipped_mentions: string[];
}

/**
 * POST /formal/load：重读 dg_* 全表装进断言图（行级 force_status——装载即对账）。
 * degraded 自愈的执行者：投影失败后重跑本端点即恢复一致（数据无损失）。
 */
export function runFormalLoad(domain?: string): Promise<FormalLoadResult> {
  return authFetch<FormalLoadResult>(
    `${BASE}/load${domain ? `?domain=${encodeURIComponent(domain)}` : ""}`,
    { method: "POST" },
  );
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
