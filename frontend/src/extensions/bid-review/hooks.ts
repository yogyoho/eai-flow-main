"use client";

/**
 * TanStack Query hooks for the bid-review API(Task 17)。
 * Query key 前缀 `["bid-review", …]`;mutation onSuccess 失效对应前缀,列表/详情/
 * 问题三面同步刷新。确认门 confirm 与反馈 feedback 分开成 hook,409(ApiError.status)
 * 分流由调用方组件做(spec §3.2:确认门 409 → toast「存在未复核致命项」)。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  adjudicateBaseline,
  confirmTask,
  feedbackIssue,
  fetchBaselines,
  getTask,
  listRulepacks,
  listTaskIssues,
  listTasks,
  type FeedbackBody,
} from "./api";

export const bidReviewKeys = {
  tasks: ["bid-review", "tasks"] as const,
  task: (taskId: string) => ["bid-review", "task", taskId] as const,
  issues: (taskId: string) => ["bid-review", "issues", taskId] as const,
  baselines: (taskId: string) => ["bid-review", "baselines", taskId] as const,
  rulepacks: ["bid-review", "rulepacks"] as const,
};

/** GET /tasks/{id} —— 任务详情(taskId 为空时不发请求)。 */
export function useBidTask(taskId: string | null | undefined) {
  return useQuery({
    queryKey: bidReviewKeys.task(taskId ?? ""),
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
  });
}

/** GET /tasks/{id}/baselines —— 基线行级快照(EAI-CUSTOM 2026-10-30 分期建议
 * 一期 s3/s4;taskId 为空时不发请求)。二期返回 {items, labels, adjudications}。 */
export function useBidBaselines(taskId: string | null | undefined) {
  return useQuery({
    queryKey: bidReviewKeys.baselines(taskId ?? ""),
    queryFn: () => fetchBaselines(taskId!),
    enabled: Boolean(taskId),
  });
}

/** POST /tasks/{id}/baselines/adjudicate —— 冲突裁定(EAI-CUSTOM 2026-10-31 二期
 * spec §1.3):onSuccess 用响应整包 setQueryData(响应即更新投影,免 refetch);
 * 409(过门)/422(未知路径/非法值)由调用方组件分流。 */
export function useBidAdjudicate(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { path: string; value: unknown; note?: string }) =>
      adjudicateBaseline(taskId, body),
    onSuccess: (data) => {
      qc.setQueryData(bidReviewKeys.baselines(taskId), data);
    },
  });
}

/** GET /tasks/{id}/issues —— 任务问题列表(taskId 为空时不发请求)。 */
export function useBidIssues(taskId: string | null | undefined) {
  return useQuery({
    queryKey: bidReviewKeys.issues(taskId ?? ""),
    queryFn: () => listTaskIssues(taskId!),
    enabled: Boolean(taskId),
  });
}

/** GET /rulepacks —— 规则包清单(规则库页)。 */
export function useBidRulepacks() {
  return useQuery({
    queryKey: bidReviewKeys.rulepacks,
    queryFn: listRulepacks,
  });
}

/** POST /issues/{id}/feedback —— 复核三连;成功后失效该任务的问题列表。
 * 入参扁平(issueId/taskId + FeedbackBody 三字段);taskId 仅为失效定位,
 * 请求体只含 action/new_severity/note。 */
export function useBidFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { issueId: string; taskId: string } & FeedbackBody) => {
      // 请求体只含 FeedbackBody 三字段;note 缺省补空串,new_severity 仅档位动作携带。
      const body: FeedbackBody = {
        action: input.action,
        note: input.note ?? "",
        ...(input.new_severity !== undefined
          ? { new_severity: input.new_severity }
          : {}),
      };
      return feedbackIssue(input.issueId, body);
    },
    onSuccess: (_data, input) => {
      void qc.invalidateQueries({
        queryKey: bidReviewKeys.issues(input.taskId),
      });
      void qc.invalidateQueries({ queryKey: bidReviewKeys.rulepacks });
    },
  });
}

/** POST /tasks/{id}/confirm —— 基准确认门;成功后失效任务详情/列表/问题(续跑刷新)。 */
export function useBidConfirmTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => confirmTask(taskId),
    onSuccess: (_data, taskId) => {
      void qc.invalidateQueries({ queryKey: bidReviewKeys.task(taskId) });
      void qc.invalidateQueries({ queryKey: bidReviewKeys.tasks });
      void qc.invalidateQueries({ queryKey: bidReviewKeys.issues(taskId) });
    },
  });
}

/** GET /tasks —— 任务列表共享查询(UX 重构 Plan 1):TasksView 列表与 layout
 * 侧栏徽标/任务 chip 同 key(bidReviewKeys.tasks)同缓存,mutation invalidate
 * 一处失效多处同步。 */
export function useBidTasks() {
  return useQuery({ queryKey: bidReviewKeys.tasks, queryFn: listTasks });
}
