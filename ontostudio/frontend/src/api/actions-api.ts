/**
 * 动作层 /actions 数据适配层（人审闭环切片 T4, EAI-CUSTOM 2026-09-26）.
 *
 * 消解审核页「确认/驳回」按钮的数据源——与 formal-api 分文件（actions 与 formal
 * 是两个路由组），但请求/鉴权封装复用同一 authFetch（eng-review 2B 决议）。
 * 路径为扩展内相对路径（authFetch base = /api/ontostudio/api/extensions）。
 *
 * 响应契约（invoke_action_core）：projected + errors 由投影决定——
 * projected:false + errors 非空 = degraded（DB 已提交、图未更新，重跑全量装载自愈）；
 * HTTP 409 = 前置条件不满足（可能已驳回/已合并，UI 必须中性提示，不得渲染为已确认）。
 */
import { authFetch } from "@/lib/api";

const BASE = "/ontology/actions";

export interface ActionInvokeResult {
  action_id: string;
  target: string;
  pk: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  audit_id: string;
  source: string;
  projected: boolean;
  errors: string[];
}

export type ReviewDecision = "confirm" | "reject";

/** 人审动作：确认（→active）或驳回（→rejected）。走单条治理管线（权限/范围/事务/审计/投影）。 */
export function invokeReviewEntity(pk: string, decision: ReviewDecision): Promise<ActionInvokeResult> {
  return authFetch<ActionInvokeResult>(`${BASE}/invoke`, {
    method: "POST",
    body: JSON.stringify({ action_id: `review_entity.${decision}`, pk }),
  });
}

// ── 批量执行（EAI-CUSTOM 2026-09-29 批量确认摊销）────────────────────────────
// POST /actions/invoke_batch：同批同一动作，行级写逐条提交（审计逐条留痕、失败行隔离），
// 全批只做一次投影装载 + 一次 refresh（单条 ≈34s/条 的全局重推理被摊销为 O(1)）。
// HTTP 恒 200（部分成功是正常形态）；只有鉴权/声明级失败才 4xx/5xx。

/** 逐行结果：ok=false 时带 status_code/detail（404 范围外 / 409 前置不满足 / 500 DB 故障）。 */
export interface BatchRowResult {
  pk: string;
  ok: boolean;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  audit_id?: string;
  status_code?: number;
  detail?: string;
  projected: boolean;
  errors: string[];
}

export interface BatchInvokeResult {
  action_id: string;
  target: string;
  requested: number;
  results: BatchRowResult[];
  succeeded: string[];
  failed: Array<{ pk: string; status_code: number; detail: string }>;
  /** 全批投影（refresh）是否成功；无可投影行（全行失败）时恒 true。 */
  projected: boolean;
  projected_pks: string[];
  errors: string[];
  source: string;
}

/** 批量人审动作：pks 上限 200（后端 _MAX_BATCH_PKS，超限 422），重复 pk 422。 */
export function invokeReviewEntityBatch(pks: string[], decision: ReviewDecision): Promise<BatchInvokeResult> {
  return authFetch<BatchInvokeResult>(`${BASE}/invoke_batch`, {
    method: "POST",
    body: JSON.stringify({ action_id: `review_entity.${decision}`, pks }),
  });
}

/** 把 HTTP 409 归一为可判别的错误类型（UI 据此渲染中性「状态已变更」而非红错）。 */
export class ActionConflictError extends Error {
  readonly detail: string;
  constructor(detail: string) {
    super(`前置条件不满足：${detail}`);
    this.name = "ActionConflictError";
    this.detail = detail;
  }
}

export async function invokeReviewEntitySafe(
  pk: string,
  decision: ReviewDecision,
): Promise<ActionInvokeResult> {
  try {
    return await invokeReviewEntity(pk, decision);
  } catch (e) {
    // authFetch 对非 2xx 抛带 status 的 Error（见 @/lib/api）——按 status 精确归一 409。
    const status = (e as { status?: number } | null)?.status;
    if (status === 409) {
      throw new ActionConflictError(e instanceof Error ? e.message : String(e));
    }
    throw e;
  }
}
