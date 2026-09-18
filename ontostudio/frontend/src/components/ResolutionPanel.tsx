/* 复制自 frontend/src/extensions/ontology/components/ResolutionPanel.tsx（S2 Task 1）——仅 import 路径改本地，内容零改动。 */
"use client";

/**
 * 实体消解面板 (EAI-CUSTOM, plan semantic-map v2 Task 4 Step 4.2).
 *
 * bid-quote 白卡细边 + INK 三级文字（浅色定版，同概览 tab 口径；零死色值——
 * chartTheme 常量 + withAlpha 派生 + Tailwind 语义类）。数据全部走 doc-graph
 * resolution REST（api 层 extension-relative 路径，authFetch 自动补前缀）：
 * - 顶部计数卡 ×2：待复核总数（pending query 的 count）/ 已合并实体（页面从
 *   图快照统计 graph_entity status==='merged' 传入，null = 快照未就绪 → "—"）；
 * - pending 列表（置信度升序）→ 点选行展开 Top5 相似建议 → 每条"合并到此"；
 * - 合并成功 → 刷新列表 + 行内"已合并，可撤销"横幅（撤销调 unmerge 再刷新）；
 * - merge/unmerge 成功后调 onRefreshGraph（页面 invalidate ["graph","full-load"]
 *   全量图查询——useReloadGraph 已由 vendored 层暴露，地图与"已合并数"卡随之更新）；
 *   query 失效用 ["ontology"] 前缀——概览 KPI 的 ["ontology","pending-review-count"]
 *   同前缀联动（评审 Fix 1：仅 ["ontology","resolution"] 会让概览 30s 内显示旧值）。
 * 错误接住（后端 routers.py 契约，前端不重复校验）：404 → 提示 + 自动刷新列表；
 * 409 → detail 文案直出；422 → "请求参数越界"。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, GitMerge, Loader2, Undo2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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
import { StatCard } from "@/components/StatCard";
import {
  fetchPending,
  fetchSuggestions,
  mergeEntities,
  PENDING_REVIEW_LIMIT,
  unmergeEntities,
  type PendingPage,
  type SuggestionsResult,
} from "@/api/ontology-graph-api";
import { withAlpha } from "@/explorer/graphTheme";
import { cn } from "@/lib/utils";

type ApiError = Error & { status?: number };

interface Notice {
  kind: "error" | "info";
  text: string;
}

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

/** action 徽章配色：auto_merge = 绿（可直并），review = 琥珀（需人工）。 */
function actionColor(action: "auto_merge" | "review"): string {
  return action === "auto_merge" ? GREEN : AMBER;
}

function actionLabel(action: "auto_merge" | "review"): string {
  return action === "auto_merge" ? "自动可并" : "建议复核";
}

export function ResolutionPanel({
  mergedCount,
  onRefreshGraph,
}: ResolutionPanelProps) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [undoable, setUndoable] = useState<UndoableMerge | null>(null);

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
      setNotice({ kind: "info", text: "已撤销合并，实体已还原为正式实体" });
      void queryClient.invalidateQueries({
        queryKey: ["ontology"],
      });
      onRefreshGraph?.();
    },
    onError: (error) => {
      const apiError = error as ApiError;
      if (apiError.status === 404) {
        setUndoable(null);
        void queryClient.invalidateQueries({
          queryKey: ["ontology"],
        });
      }
      setNotice({ kind: "error", text: resolutionErrorText(apiError) });
    },
  });

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

  return (
    <div
      className="h-full overflow-y-auto"
      data-testid="ontology-resolution-panel"
    >
      <div
        className="space-y-5 p-6"
        style={{ background: PAGE_BG, minHeight: "100%" }}
      >
        {/* 页头 */}
        <div className="flex items-center gap-3">
          <GitMerge className="h-5 w-5" style={{ color: BLUE }} />
          <h1 className="text-[22px] font-bold" style={{ color: INK }}>
            实体消解
          </h1>
        </div>

        {/* KPI 行：待复核总数（REST count）/ 已合并数（图快照统计，页面传入） */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div data-testid="kpi-resolution-pending">
            <StatCard
              label="待复核实体"
              value={
                pendingQuery.isError
                  ? "—"
                  : (pendingTotal ?? "…")
              }
              delta={
                pendingTotal !== undefined &&
                pendingTotal >= PENDING_REVIEW_LIMIT
                  ? `已达拉取上限 ${PENDING_REVIEW_LIMIT}`
                  : undefined
              }
            />
          </div>
          <div data-testid="kpi-resolution-merged">
            <StatCard
              label="已合并实体"
              value={mergedCount ?? "—"}
              delta="来自已加载图快照"
            />
          </div>
        </div>

        {/* 待复核列表加载失败：错误 + 重试 */}
        {pendingQuery.isError ? (
          <div
            className="flex items-center justify-between gap-3 rounded-[14px] px-4 py-3"
            style={{
              background: CARD,
              border: `1px solid ${withAlpha(RED, 0.3)}`,
            }}
            data-testid="resolution-pending-error"
          >
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
        ) : null}

        {/* 操作结果横幅：可撤销合并 / 错误与提示 */}
        {undoable ? (
          <div
            className="flex items-center justify-between gap-3 rounded-[10px] px-3.5 py-2.5"
            style={{
              background: ACCENT_SOFT,
              border: `1px solid ${withAlpha(BLUE, 0.25)}`,
            }}
            data-testid="resolution-undo-banner"
          >
            <p className="text-[13px]" style={{ color: BLUE }}>
              已合并「{undoable.candidateName}」→「
              {undoable.canonicalName}」，可撤销
            </p>
            <span className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                disabled={unmergeMutation.isPending}
                onClick={() => unmergeMutation.mutate(undoable.mergeId)}
                className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium disabled:opacity-50"
                style={{ background: CARD, color: BLUE, border: `1px solid ${withAlpha(BLUE, 0.35)}` }}
              >
                {unmergeMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Undo2 className="h-3 w-3" />
                )}
                撤销
              </button>
              <button
                type="button"
                aria-label="关闭提示"
                onClick={() => setUndoable(null)}
                style={{ color: INK_3 }}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          </div>
        ) : null}
        {notice ? (
          <div
            className="flex items-center justify-between gap-3 rounded-[10px] px-3.5 py-2.5"
            style={{
              background: notice.kind === "error" ? withAlpha(RED, 0.08) : ACCENT_SOFT,
              border: `1px solid ${notice.kind === "error" ? withAlpha(RED, 0.3) : withAlpha(BLUE, 0.25)}`,
            }}
            data-testid="resolution-notice"
          >
            <p
              className="text-[13px]"
              style={{ color: notice.kind === "error" ? RED : BLUE }}
            >
              {notice.text}
            </p>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => setNotice(null)}
              style={{ color: notice.kind === "error" ? RED : BLUE }}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : null}

        {/* pending 列表（置信度升序行卡） */}
        {pendingQuery.isLoading ? (
          <div
            className="flex flex-col items-center gap-2 py-16"
            data-testid="resolution-loading"
          >
            <Loader2 className="h-5 w-5 animate-spin" style={{ color: INK_3 }} />
            <p className="text-sm" style={{ color: INK_3 }}>
              加载待复核实体…
            </p>
          </div>
        ) : !pendingQuery.isError && entities.length === 0 ? (
          <div
            className="rounded-[14px] px-4 py-16 text-center"
            style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
            data-testid="resolution-empty"
          >
            <p className="text-sm" style={{ color: INK_2 }}>
              暂无待复核实体 ✅
            </p>
          </div>
        ) : (
          <div className="space-y-2" data-testid="resolution-pending-list">
            {entities.map((entity) => (
              <PendingRow
                key={entity.id}
                entity={entity}
                expanded={expandedId === entity.id}
                suggestions={{
                  loading: suggestionsQuery.isLoading,
                  error: (suggestionsQuery.error as ApiError | null) ?? null,
                  data: suggestionsQuery.data ?? null,
                }}
                mergePending={mergeMutation.isPending}
                onToggle={() => handleToggleRow(entity.id)}
                onMerge={handleMerge}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** 相似建议查询的展开态投影（单一展开行共用面板级 query 结果）。 */
interface SuggestionsState {
  loading: boolean;
  error: ApiError | null;
  data: SuggestionsResult | null;
}

/** 单行待复核实体卡：头部行（名称/etype/置信度/id 短码）+ 展开时相似建议区。 */
function PendingRow(props: {
  entity: PendingPage["entities"][number];
  expanded: boolean;
  mergePending: boolean;
  suggestions: SuggestionsState;
  onToggle: () => void;
  onMerge: (
    candidateId: string,
    canonicalId: string,
    candidateName: string,
    canonicalName: string,
  ) => void;
}) {
  const { entity, expanded, mergePending, suggestions, onToggle, onMerge } =
    props;

  return (
    <div
      className="rounded-[14px]"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
      data-testid="resolution-row"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span
          className="min-w-0 flex-1 truncate text-[13.5px] font-medium"
          style={{ color: INK }}
          title={entity.canonical_name}
        >
          {entity.canonical_name}
        </span>
        <span
          className="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
          style={{ background: ACCENT_SOFT, color: BLUE }}
        >
          {entity.etype}
        </span>
        <span
          className="w-10 shrink-0 text-right text-xs [font-variant-numeric:tabular-nums]"
          style={{ color: INK_2 }}
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
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform",
            expanded && "rotate-180",
          )}
          style={{ color: INK_3 }}
        />
      </button>

      {expanded ? (
        <div
          className="space-y-2 px-4 pt-1 pb-3.5"
          data-testid="resolution-suggestions"
        >
          <p className="text-xs" style={{ color: INK_3 }}>
            相似建议（同类型 Top 5）
          </p>
          {suggestions.loading ? (
            <div className="flex items-center gap-2 py-3">
              <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: INK_3 }} />
              <span className="text-xs" style={{ color: INK_3 }}>
                计算相似建议…
              </span>
            </div>
          ) : suggestions.error ? (
            <p className="py-2 text-xs" style={{ color: RED }}>
              相似建议加载失败：
              {suggestions.error.message || "网络错误"}
            </p>
          ) : (suggestions.data?.suggestions.length ?? 0) === 0 ? (
            <p className="py-2 text-xs" style={{ color: INK_3 }}>
              未发现达到阈值的相近实体
            </p>
          ) : (
            suggestions.data?.suggestions.map((suggestion) => {
              const color = actionColor(suggestion.action);
              const candidateName =
                suggestions.data?.entity.canonical_name ??
                entity.canonical_name;
              return (
                <div
                  key={suggestion.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[10px] px-3 py-2"
                  style={{ background: PAGE_BG, border: `1px solid ${CARD_BORDER}` }}
                  data-testid="resolution-suggestion"
                >
                  <span
                    className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold [font-variant-numeric:tabular-nums]"
                    style={{ background: withAlpha(color, 0.12), color }}
                    title="名称相似度"
                  >
                    {(suggestion.similarity * 100).toFixed(1)}%
                  </span>
                  <span
                    className="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px]"
                    style={{ background: withAlpha(color, 0.12), color }}
                  >
                    {actionLabel(suggestion.action)}
                  </span>
                  <span className="min-w-0 flex-1 text-xs leading-snug">
                    <span style={{ color: INK_2 }} title={candidateName}>
                      {candidateName}
                    </span>
                    <span className="mx-1.5" style={{ color: INK_3 }}>
                      →
                    </span>
                    <span
                      className="font-medium"
                      style={{ color: INK }}
                      title={suggestion.canonical_name}
                    >
                      {suggestion.canonical_name}
                    </span>
                  </span>
                  <button
                    type="button"
                    disabled={mergePending}
                    onClick={() =>
                      onMerge(
                        entity.id,
                        suggestion.id,
                        candidateName,
                        suggestion.canonical_name,
                      )
                    }
                    className="shrink-0 rounded-md px-2.5 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    style={{ background: BLUE }}
                  >
                    合并到此
                  </button>
                </div>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
