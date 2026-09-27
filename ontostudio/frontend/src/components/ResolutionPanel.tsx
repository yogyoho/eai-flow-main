/* 复制自 frontend/src/extensions/ontology/components/ResolutionPanel.tsx（S2 Task 1）——
 * 2026-09-27 按 docs/designs/ontostudio-frontend-redesign-20260926.html#resolve 完全移植：
 * 布局 = 超管横幅 + 双列（左：待确认实体卡流 / 右：相似合并建议 + 四态契约表）。
 * 数据流原样保留：pending 升序列表、按选中实体拉相似建议、确认/驳回四态（T4）、
 * 合并/撤销（可回放）、mergedCount 由页面图快照传入。 */
"use client";

/**
 * 实体消解审核面板 (EAI-CUSTOM)。
 *
 * 数据全部走 doc-graph resolution REST + actions invoke（authFetch 自动补前缀）：
 * - 左列待确认实体卡（置信度升序）：确认/驳回四态（成功绿勾 / degraded 黄警自愈指引 /
 *   409 中性「状态已变更」/ 在途 spinner——eng-review T5① 契约）；
 * - 点选卡片 → 右列加载该实体 Top5 相似建议（合并/不合并，undo 可回放）；
 * - 合并/确认成功后 invalidate ["ontology"] + onRefreshGraph（图快照与 KPI 联动）。
 * 错误接住（后端契约）：404 → 提示+自动刷新；409 → detail 直出；422 → 固定文案。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  GitMerge,
  Loader2,
  RefreshCw,
  Undo2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchPending,
  fetchSuggestions,
  mergeEntities,
  PENDING_REVIEW_LIMIT,
  unmergeEntities,
  type PendingPage,
  type SuggestionsResult,
} from "@/api/ontology-graph-api";
import {
  ActionConflictError,
  invokeReviewEntitySafe,
  type ActionInvokeResult,
  type ReviewDecision,
} from "@/api/actions-api";
import {
  ACCENT_SOFT,
  AMBER,
  BLUE,
  CARD,
  CARD_BORDER,
  GREEN,
  INK,
  INK_2,
  INK_3,
  PAGE_BG,
  RED,
} from "@/components/chartTheme";
import { withAlpha } from "@/explorer/graphTheme";
import { cn } from "@/lib/utils";

type ApiError = Error & { status?: number };

interface Notice {
  kind: "error" | "info";
  text: string;
}

/** 人审动作（确认/驳回）的行级 UI 状态——四态实现契约见设计稿「操作反馈四态」。 */
interface ReviewUiState {
  phase: "idle" | "running" | "done";
  decision?: ReviewDecision;
  outcome?: "ok" | "degraded" | "conflict";
  message?: string;
}

const REVIEW_IDLE: ReviewUiState = { phase: "idle" };

interface UndoableMerge {
  mergeId: string;
  candidateName: string;
  canonicalName: string;
}

interface MergeVars {
  candidateId: string;
  canonicalId: string;
  candidateName: string;
  canonicalName: string;
}

interface ResolutionPanelProps {
  /** 已合并实体计数（页面从图快照统计）；null = 图快照未就绪，显示 "—"。 */
  mergedCount: number | null;
  /** merge/unmerge 成功后触发地图图数据重载（页面 invalidate 图全量查询）。 */
  onRefreshGraph?: () => void;
}

/** 后端错误语义 → UI 文案：404 固定提示（配自动刷新）；409 detail 直出；422 固定提示。 */
function resolutionErrorText(error: ApiError): string {
  if (error.status === 404) {
    return "该记录已不存在，列表已刷新";
  }
  if (error.status === 422) {
    return "请求参数越界";
  }
  return error.message || "请求失败，请稍后重试";
}

/** suggestion 徽章文案：auto_merge = 可直并，review = 需人工。 */
function actionLabel(action: "auto_merge" | "review"): string {
  return action === "auto_merge" ? "可直并" : "需人工";
}

interface SuggestionsState {
  loading: boolean;
  error: ApiError | null;
  data: SuggestionsResult | null;
}

export function ResolutionPanel({
  mergedCount,
  onRefreshGraph,
}: ResolutionPanelProps) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [undoable, setUndoable] = useState<UndoableMerge | null>(null);
  const [reviewStates, setReviewStates] = useState<Record<string, ReviewUiState>>({});
  const setReviewState = (pk: string, next: ReviewUiState) =>
    setReviewStates((prev) => ({ ...prev, [pk]: next }));

  const pendingQuery = useQuery({
    queryKey: ["ontology", "resolution", "pending"],
    queryFn: () => fetchPending(),
    // 硬失败直接出错误+重试按钮（评审 Fix 2：默认 3× backoff 会转圈 10-15s）
    retry: false,
  });

  const suggestionsQuery = useQuery({
    queryKey: ["ontology", "resolution", "suggestions", expandedId],
    queryFn: () => fetchSuggestions(expandedId!),
    enabled: expandedId !== null,
    staleTime: 30_000,
  });

  // 展开行的实体已被他人合并/删除（suggestions 404）→ 收起 + 自动刷新列表
  useEffect(() => {
    const error = suggestionsQuery.error as ApiError | null;
    if (error?.status === 404) {
      setExpandedId(null);
      setNotice({ kind: "info", text: "该记录已不存在，列表已刷新" });
      void queryClient.invalidateQueries({
        queryKey: ["ontology"],
      });
    }
  }, [suggestionsQuery.error, queryClient]);

  const mergeMutation = useMutation({
    mutationFn: (vars: MergeVars) =>
      mergeEntities(vars.candidateId, vars.canonicalId),
    onSuccess: (data, vars) => {
      setExpandedId(null);
      setNotice(null);
      setUndoable({
        mergeId: data.merge_id,
        candidateName: vars.candidateName,
        canonicalName: vars.canonicalName,
      });
      void queryClient.invalidateQueries({
        queryKey: ["ontology"],
      });
      onRefreshGraph?.();
    },
    onError: (error) => {
      const apiError = error as ApiError;
      if (apiError.status === 404) {
        void queryClient.invalidateQueries({
          queryKey: ["ontology"],
        });
      }
      setNotice({ kind: "error", text: resolutionErrorText(apiError) });
    },
  });

  const unmergeMutation = useMutation({
    mutationFn: (mergeId: string) => unmergeEntities(mergeId),
    onSuccess: () => {
      setUndoable(null);
      setNotice({ kind: "info", text: "已撤销合并，实体已还原" });
      void queryClient.invalidateQueries({
        queryKey: ["ontology"],
      });
      onRefreshGraph?.();
    },
    onError: (error) => {
      const apiError = error as ApiError;
      if (apiError.status === 404) {
        setUndoable(null);
        void queryClient.invalidateQueries({ queryKey: ["ontology"] });
      }
      setNotice({ kind: "error", text: resolutionErrorText(apiError) });
    },
  });

  // 人审动作（确认/驳回）——人审闭环切片 T4。四态：成功绿勾 / degraded 黄警（自愈
  // 指引）/ 409 中性「状态已变更」（可能是已驳回/已合并，绝不渲染为已确认）/ 在途 spinner。
  const reviewMutation = useMutation({
    mutationFn: (vars: { pk: string; decision: ReviewDecision }) =>
      invokeReviewEntitySafe(vars.pk, vars.decision),
    onSuccess: (data: ActionInvokeResult, vars) => {
      if (data.projected) {
        setReviewState(vars.pk, {
          phase: "done",
          decision: vars.decision,
          outcome: "ok",
          message: vars.decision === "reject" ? "已驳回归档" : "已确认入图",
        });
        setNotice({
          kind: "info",
          text:
            vars.decision === "reject"
              ? "已驳回归档：状态翻转为 rejected，实体与提及保留"
              : "已确认入图：断言图已更新（projected）",
        });
      } else {
        setReviewState(vars.pk, {
          phase: "done",
          decision: vars.decision,
          outcome: "degraded",
          message: data.errors[0] ?? "投影未生效",
        });
        setNotice({
          kind: "error",
          text: "投影未生效（degraded）：业务状态已提交；管理员重跑全量装载即自动对账，数据无损失",
        });
      }
      // 让卡片上的按钮态被看见（1.2s）再刷新队列——成功/degraded 卡都会离开待审列表
      //（DB 状态已 active/rejected，前置条件不再匹配）。
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["ontology"] });
        onRefreshGraph?.();
      }, 1200);
    },
    onError: (error, vars) => {
      if (error instanceof ActionConflictError) {
        setReviewState(vars.pk, {
          phase: "done",
          decision: vars.decision,
          outcome: "conflict",
          message: "状态已变更，请刷新",
        });
        setNotice({ kind: "info", text: "该记录状态已变更（可能已驳回/已合并），列表已刷新" });
        void queryClient.invalidateQueries({ queryKey: ["ontology"] });
      } else {
        setReviewState(vars.pk, REVIEW_IDLE);
        setNotice({ kind: "error", text: resolutionErrorText(error as ApiError) });
      }
    },
  });

  const handleReview = (pk: string, decision: ReviewDecision) => {
    setReviewState(pk, { phase: "running", decision });
    reviewMutation.mutate({ pk, decision });
  };

  // 后端已按置信度升序返回；客户端再排一次保证契约可视（防御性，代价可忽略）
  const entities = useMemo(
    () =>
      [...(pendingQuery.data?.entities ?? [])].sort(
        (left, right) => left.confidence - right.confidence,
      ),
    [pendingQuery.data],
  );

  const handleToggleRow = (entityId: string) => {
    setExpandedId((current) => (current === entityId ? null : entityId));
  };

  const handleMerge = (
    candidateId: string,
    canonicalId: string,
    candidateName: string,
    canonicalName: string,
  ) => {
    mergeMutation.mutate({ candidateId, canonicalId, candidateName, canonicalName });
  };

  const pendingTotal = pendingQuery.data?.count;
  const selectedEntity = entities.find((e) => e.id === expandedId) ?? null;

  return (
    <div className="h-full overflow-y-auto" data-testid="ontology-resolution-panel">
      <div className="space-y-4 p-6" style={{ background: PAGE_BG, minHeight: "100%" }}>
        {/* 超管提示横幅（原型 warnb） */}
        <div
          className="flex items-start gap-2.5 rounded-[12px] px-3.5 py-2.5 text-xs"
          style={{ background: withAlpha(AMBER, 0.1), border: `1px solid ${withAlpha(AMBER, 0.45)}`, color: "#874d00" }}
          data-testid="resolution-superadmin-banner"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" style={{ color: AMBER }} />
          <div>
            <b>当前以 superadmin 操作（第一版仅超管可审）。</b>
            正式审阅角色授权为后续批次；观察日可用{" "}
            <span className="font-mono">roles_custom.yaml</span> overlay 临时授权真实审阅者。
          </div>
        </div>

        {/* 顶部通知（info/error） */}
        {notice ? (
          <div
            className={cn(
              "flex items-start gap-2.5 rounded-[12px] px-3.5 py-2.5 text-xs",
              notice.kind === "error" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
            )}
            data-testid="resolution-notice"
          >
            {notice.kind === "error" ? (
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 flex-none" />
            )}
            <span>{notice.text}</span>
          </div>
        ) : null}

        {/* 双列主区 */}
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
          {/* 左：待确认实体 */}
          <div className="rounded-[14px]" style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}>
            <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3" style={{ borderColor: CARD_BORDER }}>
              <b className="text-sm font-semibold" style={{ color: INK }}>
                待确认实体
              </b>
              {pendingTotal !== undefined && pendingTotal > 0 ? (
                <span
                  className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                  style={{ background: withAlpha(AMBER, 0.15), color: "#ad6800" }}
                >
                  {pendingTotal} 条待审
                  {pendingTotal >= PENDING_REVIEW_LIMIT ? `（已达拉取上限 ${PENDING_REVIEW_LIMIT}）` : ""}
                </span>
              ) : null}
              <span className="text-muted-foreground/80 ml-auto hidden font-mono text-[10px] sm:inline">
                POST /actions/invoke
              </span>
            </div>

            {pendingQuery.isError ? (
              <div className="flex items-center justify-between gap-3 px-4 py-4" data-testid="resolution-pending-error">
                <p className="text-[13px]" style={{ color: RED }}>
                  待复核列表加载失败：
                  {(pendingQuery.error as ApiError).message || "网络错误"}
                </p>
                <button
                  type="button"
                  onClick={() => void pendingQuery.refetch()}
                  className="shrink-0 rounded-md px-2.5 py-1 text-xs font-medium"
                  style={{ background: ACCENT_SOFT, color: BLUE }}
                >
                  重试
                </button>
              </div>
            ) : pendingQuery.isLoading ? (
              <div className="text-muted-foreground flex items-center justify-center gap-2 px-4 py-10 text-xs">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载待审列表…
              </div>
            ) : entities.length === 0 ? (
              <div className="text-muted-foreground px-4 py-10 text-center text-xs">
                暂无待复核实体 ✅
              </div>
            ) : (
              <div className="flex max-h-[640px] flex-col gap-2.5 overflow-y-auto p-3" data-testid="resolution-pending-list">
                {entities.map((entity) => {
                  const review = reviewStates[entity.id] ?? REVIEW_IDLE;
                  const selected = expandedId === entity.id;
                  return (
                    <div
                      key={entity.id}
                      className={cn(
                        "rounded-[12px] border transition-colors",
                        selected ? "bg-primary/5" : "bg-background hover:bg-muted/60",
                      )}
                      style={{ borderColor: selected ? withAlpha(BLUE, 0.4) : CARD_BORDER }}
                      data-testid="resolution-row"
                    >
                      {/* 卡头：点选 = 加载该实体相似建议 */}
                      <button
                        type="button"
                        onClick={() => handleToggleRow(entity.id)}
                        aria-pressed={selected}
                        className="flex w-full items-center gap-2 px-3.5 pt-3 text-left"
                      >
                        <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold" title={entity.canonical_name}>
                          {entity.canonical_name}
                        </span>
                        <span className="bg-secondary text-secondary-foreground shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10.5px]">
                          {entity.etype}
                        </span>
                        <span
                          className="w-10 shrink-0 text-right font-mono text-[11.5px] font-semibold tabular-nums"
                          style={{ color: entity.confidence < 0.8 ? "#ad6800" : INK_2 }}
                          title="抽取置信度"
                        >
                          {Number(entity.confidence).toFixed(2)}
                        </span>
                        <span
                          className="hidden w-[4.5rem] shrink-0 font-mono text-[10.5px] sm:inline"
                          style={{ color: INK_3 }}
                          title={entity.id}
                        >
                          {entity.id.slice(0, 8)}
                        </span>
                      </button>
                      <div className="text-muted-foreground px-3.5 pt-1 font-mono text-[10.5px]" style={{ color: INK_3 }}>
                        {entity.domain} · pending_review
                      </div>

                      {/* 动作行：确认/驳回 + 四态结果 */}
                      <div className="flex flex-wrap items-center gap-2 px-3.5 pb-3 pt-2.5">
                        {review.phase === "done" && review.outcome ? (
                          review.outcome === "ok" ? (
                            <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: GREEN }} data-testid="resolution-review-outcome">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              {review.decision === "reject" ? "已驳回归档（rejected，实体与提及保留）" : "已确认入图（断言图已更新）"}
                            </span>
                          ) : review.outcome === "degraded" ? (
                            <span className="flex items-center gap-1.5 text-xs" style={{ color: "#ad6800" }}>
                              <AlertTriangle className="h-3.5 w-3.5 flex-none" style={{ color: AMBER }} />
                              投影未生效（degraded）：已提交；管理员重跑全量装载即自动对账，数据无损失
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5 text-xs" style={{ color: INK_2 }}>
                              <RefreshCw className="h-3.5 w-3.5 flex-none" />
                              状态已变更（可能已驳回/已合并），请刷新
                            </span>
                          )
                        ) : (
                          <>
                            <button
                              type="button"
                              disabled={review.phase === "running"}
                              onClick={() => handleReview(entity.id, "confirm")}
                              data-testid="resolution-confirm"
                              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                              style={{ background: BLUE }}
                            >
                              {review.phase === "running" && review.decision === "confirm" ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Check className="h-3 w-3" />
                              )}
                              确认入图
                            </button>
                            <button
                              type="button"
                              disabled={review.phase === "running"}
                              onClick={() => handleReview(entity.id, "reject")}
                              data-testid="resolution-reject"
                              className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-black/[0.03] disabled:cursor-not-allowed disabled:opacity-50"
                              style={{ color: RED, borderColor: withAlpha(RED, 0.45) }}
                            >
                              {review.phase === "running" && review.decision === "reject" ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : null}
                              驳回
                            </button>
                            <span className="text-muted-foreground/80 text-[10.5px]">
                              确认 → status 强制翻转为 active，断言图即时生效
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2.5" style={{ borderColor: CARD_BORDER }}>
              <span className="text-muted-foreground text-[10.5px]">
                逐条确认即时落图；批量确认已入 TODOS「批量确认摊销」
              </span>
              <button
                type="button"
                disabled
                title="规划中（TODOS·批量摊销）"
                className="bg-primary text-primary-foreground rounded-md px-2.5 py-1 text-xs font-medium opacity-60"
              >
                批量确认（{pendingTotal ?? 0} 条）{" "}
                <span className="font-mono text-[10px] opacity-80">TODOS·批量摊销</span>
              </button>
            </div>
          </div>

          {/* 右列：相似合并建议 + 四态契约表 */}
          <div className="flex flex-col gap-4">
            <div className="rounded-[14px]" style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}>
              <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3" style={{ borderColor: CARD_BORDER }}>
                <b className="text-sm font-semibold" style={{ color: INK }}>
                  相似实体合并建议
                </b>
                {selectedEntity ? (
                  <span className="text-muted-foreground truncate text-[11px]" title={selectedEntity.canonical_name}>
                    · {selectedEntity.canonical_name}
                  </span>
                ) : null}
                <span className="text-muted-foreground/80 ml-auto hidden font-mono text-[10px] sm:inline">
                  GET /doc-graph/resolution/suggestions
                </span>
              </div>
              <div className="flex flex-col gap-2.5 p-3" data-testid="resolution-suggestions">
                {!expandedId ? (
                  <div className="text-muted-foreground px-2 py-8 text-center text-xs leading-loose">
                    ← 在左侧点选一张待审卡
                    <br />
                    查看它的 Top 5 相似建议
                  </div>
                ) : suggestionsQuery.isLoading ? (
                  <div className="text-muted-foreground flex items-center justify-center gap-2 px-2 py-6 text-xs">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: INK_3 }} />
                    计算相似建议…
                  </div>
                ) : suggestionsQuery.error ? (
                  <p className="text-destructive px-2 py-4 text-xs">
                    建议加载失败：{(suggestionsQuery.error as ApiError).message}
                  </p>
                ) : (suggestionsQuery.data?.suggestions ?? []).length === 0 ? (
                  <div className="text-muted-foreground px-2 py-6 text-center text-xs">
                    无相似建议（同类型相似度均低于阈值）
                  </div>
                ) : (
                  (suggestionsQuery.data?.suggestions ?? []).map((sug) => (
                    <div key={sug.id} className="rounded-[12px] border p-3" style={{ borderColor: CARD_BORDER }}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold" style={{ color: INK }}>
                          {sug.canonical_name}
                        </span>
                        <span
                          className="rounded-full px-2 py-0.5 text-[10.5px] font-medium"
                          style={{
                            background: withAlpha(sug.action === "auto_merge" ? GREEN : AMBER, 0.12),
                            color: sug.action === "auto_merge" ? "#389e0d" : "#ad6800",
                          }}
                        >
                          {actionLabel(sug.action)}
                        </span>
                        <span className="font-mono text-[11.5px] font-semibold tabular-nums" style={{ color: INK_2 }}>
                          {sug.similarity.toFixed(2)}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          disabled={mergeMutation.isPending}
                          onClick={() =>
                            handleMerge(sug.id, expandedId, sug.canonical_name, selectedEntity?.canonical_name ?? "")
                          }
                          className="bg-primary text-primary-foreground hover:opacity-90 flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium disabled:opacity-50"
                        >
                          {mergeMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <GitMerge className="h-3 w-3" />}
                          合并
                        </button>
                        <button
                          type="button"
                          onClick={() => setExpandedId(null)}
                          className="border-border bg-card text-foreground hover:bg-muted rounded-md border px-2.5 py-1 text-xs"
                        >
                          不合并
                        </button>
                        <span className="text-muted-foreground/80 text-[10px]">
                          POST /resolution/merge · undo 可回放
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
              {/* 撤销合并横幅 */}
              {undoable ? (
                <div
                  className="mx-3 mb-3 flex flex-wrap items-center gap-2 rounded-[10px] px-3 py-2.5 text-xs"
                  style={{ background: withAlpha(GREEN, 0.08), border: `1px solid ${withAlpha(GREEN, 0.35)}` }}
                  data-testid="resolution-undo"
                >
                  <Undo2 className="h-3.5 w-3.5 flex-none" style={{ color: GREEN }} />
                  <span style={{ color: INK }}>
                    已合并 <b>{undoable.candidateName}</b> → {undoable.canonicalName}
                  </span>
                  <button
                    type="button"
                    disabled={unmergeMutation.isPending}
                    onClick={() => unmergeMutation.mutate(undoable.mergeId)}
                    className="ml-auto flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium disabled:opacity-50"
                    style={{ color: BLUE, borderColor: withAlpha(BLUE, 0.4) }}
                  >
                    {unmergeMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                    撤销
                  </button>
                </div>
              ) : null}
              <div className="text-muted-foreground flex items-center justify-between border-t px-4 py-2 text-[10.5px]" style={{ borderColor: CARD_BORDER }}>
                <span>已合并实体（图快照）</span>
                <span className="font-mono tabular-nums">{mergedCount ?? "—"}</span>
              </div>
            </div>

            <div className="rounded-[14px]" style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}>
              <div className="border-b px-4 py-3" style={{ borderColor: CARD_BORDER }}>
                <b className="text-sm font-semibold" style={{ color: INK }}>
                  操作反馈四态（实现契约）
                </b>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-border bg-muted/60 border-b" style={{ borderColor: CARD_BORDER }}>
                    {["态", "触发", "呈现"].map((h) => (
                      <th key={h} className="text-muted-foreground px-4 py-2 text-left text-[11px] font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-border/60 border-b" style={{ borderColor: CARD_BORDER }}>
                    <td className="px-4 py-2"><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: GREEN }} />成功</td>
                    <td className="px-2 py-2 font-mono text-[10.5px]">projected:true</td>
                    <td className="px-2 py-2">绿勾 + 行内「已入图」；图浏览可立即看到</td>
                  </tr>
                  <tr className="border-border/60 border-b" style={{ borderColor: CARD_BORDER }}>
                    <td className="px-4 py-2"><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: AMBER }} />degraded</td>
                    <td className="px-2 py-2 font-mono text-[10.5px]">projected:false + errors</td>
                    <td className="px-2 py-2">黄警 + 明细 + 「重跑全量装载即自动对账（数据无损失）」</td>
                  </tr>
                  <tr className="border-border/60 border-b" style={{ borderColor: CARD_BORDER }}>
                    <td className="px-4 py-2"><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: INK_3 }} />冲突 409</td>
                    <td className="px-2 py-2 font-mono text-[10.5px]">前置条件不满足</td>
                    <td className="px-2 py-2">中性提示「状态已变更，请刷新」（不得渲染为已确认）</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2"><span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: BLUE }} />在途</td>
                    <td className="px-2 py-2 font-mono text-[10.5px]">invoke 进行中</td>
                    <td className="px-2 py-2">按钮 disabled + spinner（同步投影秒级等待）</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
