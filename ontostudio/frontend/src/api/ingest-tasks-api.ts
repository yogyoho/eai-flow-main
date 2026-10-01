/**
 * 抽取任务 API 适配层（EAI-CUSTOM 2026-10-01 T6 前端接线）.
 *
 * 对应后端 ontostudio/backend/app/doc_graph/ingest_tasks.py 的 5+1 端点
 * （设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B2）。
 * 相对路径写法同 ontology-graph-api（authFetch 默认 base 已含 /api/extensions 前缀）。
 */
import { authFetch } from "@/lib/api";

const BASE = "/ingest-tasks";

/** 任务阶段枚举（D3/2A：阶段制，无百分比——后端无进度生产者）。 */
export type TaskStatus =
  | "queued"
  | "extracting"
  | "loading"
  | "done"
  | "completed_empty"
  | "failed"
  | "aborted";

export interface IngestTask {
  id: string;
  sample_id: string;
  sample_title: string | null;
  document_id: string;
  force_review: boolean;
  status: TaskStatus;
  error: string | null;
  stats: {
    entities?: number;
    relations?: number;
    mentions?: number;
    entities_upserted?: number;
    dropped?: { entities: number; relations: number };
  } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SampleRef {
  id: string;
  title: string;
  status: string;
  entity_count: number;
  updated_at: string;
}

export interface TaskStats {
  tasks_by_status: Record<string, number>;
  confidence: Record<string, number>;
}

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchTasks(signal?: AbortSignal): Promise<{ tasks: IngestTask[] }> {
  return authFetch<{ tasks: IngestTask[] }>(`${BASE}`, { signal });
}

export async function fetchTaskStats(signal?: AbortSignal): Promise<TaskStats> {
  return authFetch<TaskStats>(`${BASE}/stats`, { signal });
}

export async function fetchSamples(signal?: AbortSignal): Promise<{ samples: SampleRef[] }> {
  return authFetch<{ samples: SampleRef[] }>(`${BASE}/samples`, { signal });
}

export async function createTask(
  body: { sample_id: string; force_review?: boolean },
): Promise<{ id: string; status: string; document_id: string }> {
  return authFetch(`${BASE}`, { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) });
}

export async function deleteTask(taskId: string): Promise<{ id: string; result: string }> {
  return authFetch(`${BASE}/${taskId}`, { method: "DELETE" });
}

/** 阶段枚举 → 中文文案（T3/2A：阶段制文案，无百分比）。 */
export const STATUS_LABEL: Record<TaskStatus, string> = {
  queued: "排队中",
  extracting: "抽取中",
  loading: "装载中",
  done: "已完成",
  completed_empty: "无命中",
  failed: "失败",
  aborted: "已中止",
};

/** 阶段 → 状态点色（对齐全站语义色惯例）。 */
export const STATUS_DOT: Record<TaskStatus, string> = {
  queued: "bg-warning",
  extracting: "bg-primary",
  loading: "bg-primary",
  done: "bg-success",
  completed_empty: "bg-muted-foreground",
  failed: "bg-destructive",
  aborted: "bg-muted-foreground",
};

export function isActiveStatus(s: TaskStatus): boolean {
  return s === "queued" || s === "extracting" || s === "loading";
}
