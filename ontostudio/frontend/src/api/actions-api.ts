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
