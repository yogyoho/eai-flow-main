/**
 * TypeScript types for the bid-review extension API.
 *
 * Field names mirror the backend Pydantic schemas (snake_case) exactly —
 * `backend/app/extensions/bid_review/schemas.py`(Task 2;A8:verdict/action
 * 均为引擎产出层取值,false_positive 等人工回写值仅落库不经 schema 校验)。
 */

/** 审查任务(backend TaskOut)。status 词汇=后端 models.py:30:created|parsing|extracting|
 * awaiting_confirm|running|done|failed(终态成功=done,后端无 completed;Task 12 修复轮勘误);
 * mode: quick|deep */
export interface TaskOut {
  id: string;
  owner_id: string;
  status: string;
  mode: string;
  progress: Record<string, unknown>;
  error: string | null;
  engine_meta: Record<string, unknown>;
  prev_task_id: string | null;
  created_at: string;
  /** 每任务问题计数(micro-A 2026-10-29):仅 GET /tasks 列表聚合填充;单任务端点
   * null=未统计(禁伪零)。fatal_unhandled=fatal 且未被人工判误报(verdict≠
   * false_positive,误报回流后自然回落);need_human_count=need_human 旗标计数。 */
  fatal_unhandled: number | null;
  need_human_count: number | null;
}

/** 审查问题(backend IssueOut)。 */
export interface IssueOut {
  id: string;
  task_id: string;
  rule_id: string;
  layer: string;
  severity: string;
  verdict: string;
  clause_id: string | null;
  message: string;
  fix: string;
  evidence: unknown[];
  dedup_key: string;
  need_human: boolean;
  confidence: number;
  created_at: string;
}

/** 基准包(backend BaselineOut)。 */
export interface BaselineOut {
  id: string;
  task_id: string;
  kind: string;
  payload: Record<string, unknown>;
  confirmed: boolean;
  created_at: string;
}
