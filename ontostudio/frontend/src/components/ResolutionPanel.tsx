/* 复制自 frontend/src/extensions/ontology/components/ResolutionPanel.tsx（S2 Task 1）——
 * 2026-10-20 按 docs/designs/ontostudio-platform.html#s-resolve 重排：
 * 布局 = 页头 + 待审队列（300px）/ 候选对比 / 右侧反馈与质量约束（286px）。
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
  ChevronLeft,
  ChevronRight,
  GitMerge,
  Info,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchPending,
  fetchSuggestions,
  mergeEntities,
  PENDING_REVIEW_LIMIT,
  unmergeEntities,
  type ResolutionSuggestion,
  type SuggestionsResult,
} from "@/api/ontology-graph-api";
import {
  ActionConflictError,
  invokeReviewEntityBatch,
  invokeReviewEntitySafe,
  type ActionInvokeResult,
  type ReviewDecision,
} from "@/api/actions-api";
import { fetchEiaEtypeLabels } from "@/explorerDataSource";
import { domainAlias } from "@/lib/terms";
import { cn } from "@/lib/utils";
import { PERM, usePermission } from "@/lib/permissions";
import { Chip, PageHeader, Panel } from "@/pages/shared";

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
  /**
   * 页头检索框透传（EAI-CUSTOM 2026-09-29 检索修复）：对已拉取的待审卡做
   * canonical_name 客户端过滤（resolution 通道 snake_case 契约；大小写不敏感
   * contains；空 = 全量）。后端 /resolution/pending 只有 etype/limit 无 search
   * 参数，拉取上限 PENDING_REVIEW_LIMIT 内过滤即任务口径。
   */
  searchQuery?: string;
  /** 检索框受控回写（2026-10-20 页头重构：搜索框移入待审队列工具栏）。 */
  onSearchChange?: (value: string) => void;
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

/** 待审优先级：置信度越低越优先（队列按置信度升序）。 */
function reviewSeverity(confidence: number): {
  label: string;
  dot: string;
  tone: "danger" | "warning" | "gray";
} {
  if (confidence < 0.8) return { label: "高", dot: "is-high", tone: "danger" };
  if (confidence < 0.9) return { label: "中", dot: "is-mid", tone: "warning" };
  return { label: "低", dot: "is-low", tone: "gray" };
}

function CandidateCard({
  role,
  tone,
  name,
  etype,
  domain,
  confidence,
  suggestion,
  etypeLabel,
}: {
  role: "A" | "B";
  tone: "primary" | "warning";
  name: string;
  etype: string;
  domain?: string;
  confidence?: number;
  suggestion?: ResolutionSuggestion;
  etypeLabel: string;
}) {
  const severity = confidence !== undefined ? reviewSeverity(confidence) : null;
  return (
    <div className="os-resolve-cand">
      <div className="os-resolve-cand-hd">
        <Chip tone={tone}>候选 {role}</Chip>
        <b title={name}>{name}</b>
        {suggestion ? (
          <span className="os-resolve-sim" title="相似度">
            {suggestion.similarity.toFixed(2)}
          </span>
        ) : null}
      </div>
      <div className="os-resolve-cand-bd">
        <div className="os-kv">
          <span className="os-kv-k">名称</span>
          <span className="os-kv-v" title={name}>
            {name}
          </span>
        </div>
        <div className="os-kv">
          <span className="os-kv-k">类型</span>
          <span className="os-kv-v" title={etype}>
            {etypeLabel}
          </span>
        </div>
        {domain ? (
          <div className="os-kv">
            <span className="os-kv-k">域</span>
            <span className="os-kv-v">{domainAlias(domain) ?? domain}</span>
          </div>
        ) : null}
        {confidence !== undefined && severity ? (
          <div className="os-kv">
            <span className="os-kv-k">置信度</span>
            <span className={cn("os-kv-v os-resolve-conf", severity.dot)}>
              {confidence.toFixed(2)}
            </span>
          </div>
        ) : null}
        {suggestion ? (
          <>
            <div className="os-kv">
              <span className="os-kv-k">相似度</span>
              <span className="os-kv-v os-resolve-conf">{suggestion.similarity.toFixed(2)}</span>
            </div>
            <div className="os-kv">
              <span className="os-kv-k">建议</span>
              <span className="os-kv-v">
                <Chip tone={suggestion.action === "auto_merge" ? "primary" : "warning"}>
                  {actionLabel(suggestion.action)}
                </Chip>
              </span>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

interface SuggestionsState {
  loading: boolean;
  error: ApiError | null;
  data: SuggestionsResult | null;
}

export function ResolutionPanel({
  mergedCount,
  onRefreshGraph,
  searchQuery = "",
  onSearchChange,
}: ResolutionPanelProps) {
  const queryClient = useQueryClient();
  const { can: canReview } = usePermission();
  const canReviewActions = canReview(PERM.REVIEW);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [undoable, setUndoable] = useState<UndoableMerge | null>(null);
  const [reviewStates, setReviewStates] = useState<Record<string, ReviewUiState>>({});
  // 批量确认（EAI-CUSTOM 2026-09-29 批量确认摊销）：勾选集合 + 批次失败行（pk → detail）
  // + 在途批次行数（进度文案用）。失败行标红可重试（重试走单条管线）。
  const [selectedPks, setSelectedPks] = useState<Set<string>>(new Set());
  const [batchFailed, setBatchFailed] = useState<Map<string, string>>(new Map());
  const [batchSize, setBatchSize] = useState(0);
  const [batchDecision, setBatchDecision] = useState<"confirm" | "reject">("confirm");
  const setReviewState = (pk: string, next: ReviewUiState) =>
    setReviewStates((prev) => ({ ...prev, [pk]: next }));

  // 翻页游标（v2 B2/N1：230+ 待审时 200 上限页翻完全量）；检索词变化时归零
  const [pageIndex, setPageIndex] = useState(0);
  const trimmedSearch = searchQuery.trim();
  useEffect(() => {
    setPageIndex(0);
  }, [trimmedSearch]);

  // EAI-CUSTOM(2026-10-01 v4 文案包 R1): etype 中文标注（eia.yaml etype 注释块，
  // 与 DetailPanel 规律卡同源）——待审卡 etype 芯片显示中文+英文次注。
  const etypeLabels = useQuery({
    queryKey: ["ontology", "eia-etype-labels"],
    queryFn: fetchEiaEtypeLabels,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const pendingQuery = useQuery({
    queryKey: ["ontology", "resolution", "pending", trimmedSearch, pageIndex],
    queryFn: () =>
      fetchPending(null, trimmedSearch || undefined, pageIndex * PENDING_REVIEW_LIMIT),
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
      // 单条重试成功 → 摘掉该行的批量失败标记（行即将离开待审列表）
      setBatchFailed((prev) => {
        if (!prev.has(vars.pk)) return prev;
        const next = new Map(prev);
        next.delete(vars.pk);
        return next;
      });
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

  // ── 批量确认（EAI-CUSTOM 2026-09-29 批量确认摊销）────────────────────────
  // POST /actions/invoke_batch：行级写逐条提交（审计逐条留痕），全批一次投影装载 +
  // 一次 refresh。部分成功是正常形态（HTTP 200 + 逐行结果）；失败行留在待审列表，
  // 标红并给单条重试入口。
  const batchMutation = useMutation({
    mutationFn: ({ pks, decision }: { pks: string[]; decision: "confirm" | "reject" }) => {
      setBatchSize(pks.length);
      setBatchDecision(decision);
      return invokeReviewEntityBatch(pks, decision);
    },
    onSuccess: (data) => {
      setBatchFailed((prev) => {
        const next = new Map(prev);
        for (const f of data.failed) next.set(f.pk, f.detail);
        for (const pk of data.succeeded) next.delete(pk); // 成功行摘掉陈旧失败标
        return next;
      });
      const failedCount = data.failed.length;
      const degradedSuffix =
        data.succeeded.length > 0 && !data.projected
          ? "；投影 degraded：重跑全量装载即自动对账，数据无损失"
          : "";
      if (failedCount > 0) {
        setNotice({
          kind: failedCount === data.requested ? "error" : "info",
          text: `批量${batchDecision === "reject" ? "驳回" : "确认"}完成：成功 ${data.succeeded.length} 条，失败 ${failedCount} 条（行已标红，可逐条重试）${degradedSuffix}`,
        });
      } else {
        setNotice({
          kind: data.projected ? "info" : "error",
          text: data.projected
            ? `批量${batchDecision === "reject" ? "驳回" : "确认"} ${data.succeeded.length} 条完成：已提交并投影入图（全批一次 refresh）`
            : `批量${batchDecision === "reject" ? "驳回" : "确认"} ${data.succeeded.length} 条已提交，但投影 degraded：重跑全量装载即自动对账，数据无损失`,
        });
      }
      // 成功行离开选择集合（列表刷新后它们也不再出现在待审里）
      setSelectedPks((prev) => {
        const next = new Set(prev);
        for (const pk of data.succeeded) next.delete(pk);
        return next;
      });
      // 与单条一致：让批次结果被看见片刻再刷新队列
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["ontology"] });
        onRefreshGraph?.();
      }, 1200);
    },
    onError: (error) => {
      setNotice({ kind: "error", text: resolutionErrorText(error as ApiError) });
    },
  });

  const toggleSelected = (pk: string) => {
    setSelectedPks((prev) => {
      const next = new Set(prev);
      if (next.has(pk)) {
        next.delete(pk);
      } else {
        next.add(pk);
      }
      return next;
    });
  };

  // 后端已按置信度升序返回；客户端再排一次保证契约可视（防御性，代价可忽略）
  const entities = useMemo(
    () =>
      [...(pendingQuery.data?.entities ?? [])].sort(
        (left, right) => left.confidence - right.confidence,
      ),
    [pendingQuery.data],
  );

  // 检索过滤（EAI-CUSTOM 2026-09-29）：只裁剪左列卡片流，不动 entities 全集——
  // 右侧 selectedEntity 相似建议面板不因过滤丢选中。canonical_name 是 resolution
  // 通道的 snake_case 契约字段（图投影属性才是 camelCase canonicalName）。
  const search = searchQuery.trim().toLowerCase();
  const visibleEntities = useMemo(() => {
    if (!search) {
      return entities;
    }
    return entities.filter((entity) =>
      entity.canonical_name.toLowerCase().includes(search),
    );
  }, [entities, search]);

  // 首屏自动选中第一条待审实体（原型：队列首行高亮 + 中间对比区直接有内容）。
  // 只自动触发一次；用户主动收起后不再强制重选。
  const autoSelectedRef = useRef(false);
  useEffect(() => {
    if (expandedId) {
      autoSelectedRef.current = true;
      return;
    }
    if (autoSelectedRef.current) return;
    const first = visibleEntities[0];
    if (first) {
      autoSelectedRef.current = true;
      setExpandedId(first.id);
    }
  }, [expandedId, visibleEntities]);

  // 列表刷新后剪枝选中集合：已离开待审列表的行不再保留勾选
  useEffect(() => {
    setSelectedPks((prev) => {
      if (prev.size === 0) return prev;
      const alive = new Set(entities.map((entity) => entity.id));
      const next = new Set([...prev].filter((id) => alive.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [entities]);

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
  const selectedReview = selectedEntity
    ? reviewStates[selectedEntity.id] ?? REVIEW_IDLE
    : REVIEW_IDLE;
  const suggestions = suggestionsQuery.data?.suggestions ?? [];
  const topSuggestion = suggestions[0] ?? null;
  const restSuggestions = suggestions.slice(1);
  const totalPages =
    pendingTotal && pendingTotal > 0
      ? Math.max(1, Math.ceil(pendingTotal / PENDING_REVIEW_LIMIT))
      : 1;
  const lowConfidenceCount = visibleEntities.filter(
    (entity) => entity.confidence < 0.8,
  ).length;
  const etypeLabelOf = (etype: string) => etypeLabels.data?.get(etype) ?? etype;
  const candidateA = selectedEntity ? (
    <CandidateCard
      role="A"
      tone="primary"
      name={selectedEntity.canonical_name}
      etype={selectedEntity.etype}
      etypeLabel={etypeLabelOf(selectedEntity.etype)}
      domain={selectedEntity.domain}
      confidence={selectedEntity.confidence}
    />
  ) : null;

  // 批量选择派生值：可见集 = 检索过滤后的卡流（全选只作用于看得见的行）
  const selectedCount = selectedPks.size;
  const allVisibleSelected =
    visibleEntities.length > 0 && visibleEntities.every((entity) => selectedPks.has(entity.id));
  const toggleSelectAllVisible = () => {
    setSelectedPks((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        for (const entity of visibleEntities) next.delete(entity.id);
      } else {
        for (const entity of visibleEntities) next.add(entity.id);
      }
      return next;
    });
  };

  return (
    <div className="h-full overflow-y-auto" data-testid="ontology-resolution-panel">
      <div className="os-page">
        <PageHeader
          clause="04 · 知识层"
          icon={GitMerge}
          title="消解审核"
          description="候选实体两两比对，确认合并入图或驳回归档 · 确认后即时生效 · 驳回保留证据不删数据"
          actions={
            <>
              <button
                type="button"
                disabled={selectedCount === 0 || batchMutation.isPending || !canReviewActions}
                onClick={() => batchMutation.mutate({ pks: [...selectedPks], decision: "reject" })}
                title={`批量驳回选中 ${selectedCount} 条（归档保留，不删数据）`}
                className="os-btn os-btn-secondary"
                data-testid="resolution-batch-reject"
              >
                <X />
                批量驳回{selectedCount > 0 ? ` (${selectedCount})` : ""}
              </button>
              <button
                type="button"
                disabled={selectedCount === 0 || batchMutation.isPending || !canReviewActions}
                onClick={() => batchMutation.mutate({ pks: [...selectedPks], decision: "confirm" })}
                title={`批量确认选中 ${selectedCount} 条（入图并即时生效）`}
                className="os-btn os-btn-primary"
                data-testid="resolution-batch-confirm"
              >
                {batchMutation.isPending && batchDecision === "confirm" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Check />
                )}
                批量确认{selectedCount > 0 ? ` (${selectedCount})` : ""}
              </button>
            </>
          }
        />

        {!canReviewActions ? (
          <div className="os-resolve-banner is-warn" data-testid="resolution-no-review-perm">
            <AlertTriangle />
            <div>
              <b>当前账号无审核权限。</b>需要权限点 <code>ontology:review</code>——请在 EAI
              系统管理·策略中心授权后刷新本页。
            </div>
          </div>
        ) : (
          <div className="os-resolve-banner is-warn" data-testid="resolution-superadmin-banner">
            <AlertTriangle />
            <div>
              <b>
                {pendingTotal !== undefined
                  ? `${pendingTotal} 条实体待复核`
                  : "正在读取待复核实体"}
              </b>
              {pendingTotal !== undefined ? (
                <>
                  ，当前视图 {visibleEntities.length} 条
                  {lowConfidenceCount > 0
                    ? `，其中 ${lowConfidenceCount} 条低置信度（<0.80）`
                    : ""}
                  ；队列按置信度升序排列。
                </>
              ) : null}
              <span className="os-resolve-banner-sep"> · </span>
              当前以 superadmin 操作；审阅授权已迁移 EAI 策略中心（权限点
              ontology:review）。
            </div>
          </div>
        )}

        {notice ? (
          <div
            className={cn("os-resolve-banner", notice.kind === "error" ? "is-error" : "is-info")}
            data-testid="resolution-notice"
          >
            {notice.kind === "error" ? <AlertTriangle /> : <CheckCircle2 />}
            <span>{notice.text}</span>
          </div>
        ) : null}

        <div className="os-resolve-grid">
          <Panel
            title="待审队列"
            subtitle={
              pendingTotal !== undefined
                ? search
                  ? `${visibleEntities.length} / ${pendingTotal} 条`
                  : `${pendingTotal} 条`
                : undefined
            }
            actions={<Chip tone="warning">低置信优先</Chip>}
            className="os-resolve-panel os-resolve-queue"
          >
            <div className="os-resolve-search">
              <Search />
              <input
                type="search"
                value={searchQuery}
                onChange={(event) => onSearchChange?.(event.target.value)}
                placeholder="搜索候选项…"
                aria-label="检索实体"
                autoComplete="off"
              />
              {searchQuery ? (
                <button
                  type="button"
                  className="os-resolve-search-clear"
                  onClick={() => onSearchChange?.("")}
                  aria-label="清除检索"
                >
                  <X />
                </button>
              ) : null}
            </div>

            {pendingQuery.isError ? (
              <div className="os-resolve-state is-error" data-testid="resolution-pending-error">
                <span>
                  待复核列表加载失败：
                  {(pendingQuery.error as ApiError).message || "网络错误"}
                </span>
                <button
                  type="button"
                  onClick={() => void pendingQuery.refetch()}
                  className="os-btn os-btn-secondary os-btn-sm"
                >
                  重试
                </button>
              </div>
            ) : pendingQuery.isLoading ? (
              <div className="os-resolve-state">
                <Loader2 className="animate-spin" />
                加载待审列表…
              </div>
            ) : entities.length === 0 ? (
              <div className="os-resolve-state">
                <CheckCircle2 />
                暂无待复核实体
              </div>
            ) : visibleEntities.length === 0 ? (
              <div className="os-resolve-state">
                未找到匹配「{searchQuery.trim()}」的待审实体
              </div>
            ) : (
              <div className="os-resolve-list" data-testid="resolution-pending-list">
                {visibleEntities.map((entity) => {
                  const review = reviewStates[entity.id] ?? REVIEW_IDLE;
                  const selected = expandedId === entity.id;
                  const checked = selectedPks.has(entity.id);
                  const failedDetail = batchFailed.get(entity.id);
                  const severity = reviewSeverity(entity.confidence);
                  return (
                    <div
                      key={entity.id}
                      className={cn("os-resolve-row", selected && "is-on")}
                      data-testid="resolution-row"
                      onClick={() => handleToggleRow(entity.id)}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelected(entity.id)}
                        onClick={(event) => event.stopPropagation()}
                        aria-label={`选择 ${entity.canonical_name}`}
                        className="os-resolve-check"
                        data-testid="resolution-row-checkbox"
                      />
                      <span
                        className={cn("os-resolve-sev", severity.dot)}
                        title={`待审优先级：${severity.label}`}
                      />
                      <div className="os-resolve-main">
                        <div className="os-resolve-name">
                          <b title={entity.canonical_name}>{entity.canonical_name}</b>
                        </div>
                        <div className="os-resolve-meta">
                          <span title={entity.etype}>{etypeLabelOf(entity.etype)}</span>
                          <span className="os-resolve-meta-sep">·</span>
                          <span>{domainAlias(entity.domain) ?? entity.domain}</span>
                          <span className="os-resolve-meta-sep">·</span>
                          <span>待审</span>
                        </div>

                        {failedDetail && review.phase === "idle" ? (
                          <div className="os-resolve-row-fail" data-testid="resolution-batch-failed">
                            <AlertTriangle />
                            <span title={failedDetail}>批量确认失败：{failedDetail}</span>
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                handleReview(entity.id, "confirm");
                              }}
                              className="os-resolve-link-danger"
                              data-testid="resolution-batch-retry"
                            >
                              重试
                            </button>
                          </div>
                        ) : null}

                        {review.phase === "running" ? (
                          <div className="os-resolve-row-state is-info">
                            <Loader2 className="animate-spin" />
                            正在同步投影入图…
                          </div>
                        ) : review.phase === "done" && review.outcome ? (
                          <div
                            className={cn(
                              "os-resolve-row-state",
                              review.outcome === "ok"
                                ? "is-ok"
                                : review.outcome === "degraded"
                                  ? "is-warn"
                                  : "is-muted",
                            )}
                          >
                            {review.outcome === "ok" ? <CheckCircle2 /> : null}
                            {review.outcome === "degraded" ? <AlertTriangle /> : null}
                            {review.outcome === "conflict" ? <RefreshCw /> : null}
                            {review.outcome === "ok"
                              ? review.decision === "reject"
                                ? "已驳回归档"
                                : "已确认入图"
                              : review.outcome === "degraded"
                                ? "投影降级，已提交"
                                : "状态已变更，请刷新"}
                          </div>
                        ) : null}

                        <div
                          className="os-resolve-row-actions"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <button
                            type="button"
                            disabled={
                              batchMutation.isPending ||
                              !canReviewActions ||
                              review.phase !== "idle"
                            }
                            onClick={() => handleReview(entity.id, "confirm")}
                            className="os-btn os-btn-ghost os-btn-sm"
                          >
                            <Check />
                            确认
                          </button>
                          <button
                            type="button"
                            disabled={
                              batchMutation.isPending ||
                              !canReviewActions ||
                              review.phase !== "idle"
                            }
                            onClick={() => handleReview(entity.id, "reject")}
                            className="os-btn os-btn-ghost os-btn-sm is-danger"
                          >
                            <X />
                            驳回
                          </button>
                        </div>
                      </div>
                      <div className="os-resolve-conf-wrap">
                        <span
                          className={cn("os-resolve-conf", severity.dot)}
                          title="抽取置信度"
                        >
                          {Number(entity.confidence).toFixed(2)}
                        </span>
                        <span title={`待审优先级：${severity.label}`}>
                          <Chip tone={severity.tone}>{severity.label}</Chip>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="os-resolve-foot">
              <div className="os-resolve-foot-row">
                {visibleEntities.length > 0 ? (
                  <label className="os-resolve-selectall">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      className="os-resolve-check"
                      data-testid="resolution-select-all"
                    />
                    全选本页
                  </label>
                ) : (
                  <span>勾选后可批量处理</span>
                )}
                {selectedCount > 0 ? (
                  <span className="os-resolve-selected-count">已选 {selectedCount}</span>
                ) : null}
                {totalPages > 1 ? (
                  <div className="os-resolve-pager">
                    <button
                      type="button"
                      disabled={pageIndex === 0}
                      onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                      aria-label="上一页"
                      title="上一页"
                      data-testid="resolution-prev-page"
                    >
                      <ChevronLeft />
                    </button>
                    <span>
                      {pageIndex + 1} / {totalPages}
                    </span>
                    <button
                      type="button"
                      disabled={(pageIndex + 1) * PENDING_REVIEW_LIMIT >= (pendingTotal ?? 0)}
                      onClick={() => setPageIndex((p) => p + 1)}
                      aria-label="下一页"
                      title="下一页"
                      data-testid="resolution-next-page"
                    >
                      <ChevronRight />
                    </button>
                  </div>
                ) : null}
              </div>
              {batchMutation.isPending ? (
                <div className="os-resolve-batch-status" data-testid="resolution-batch-running">
                  <Loader2 className="animate-spin" />
                  批量{batchDecision === "reject" ? "驳回" : "确认"} {batchSize} 条，投影入图约需
                  10–60 秒（全批仅刷新一次断言图）——请勿刷新或离开本页
                </div>
              ) : (
                <div className="os-resolve-foot-note">行级写逐条留痕；全批一次投影入图</div>
              )}
            </div>
          </Panel>

          <Panel
            title="候选对比"
            subtitle={selectedEntity ? selectedEntity.canonical_name : "选择左侧待审实体"}
            actions={selectedEntity ? <Chip tone="primary">候选 A</Chip> : undefined}
            className="os-resolve-panel os-resolve-compare"
          >
            <div className="os-resolve-compare-bd" data-testid="resolution-suggestions">
              {!selectedEntity ? (
                <div className="os-resolve-empty">
                  <GitMerge />
                  <b>从左侧选择一条待审实体</b>
                  <span>查看同类型相似建议，确认合并入图或驳回。</span>
                </div>
              ) : (
                <>
                  {suggestionsQuery.isLoading ? (
                    <>
                      <div className="os-resolve-cand-grid is-single">{candidateA}</div>
                      <div className="os-resolve-state">
                        <Loader2 className="animate-spin" />
                        计算相似建议…
                      </div>
                    </>
                  ) : suggestionsQuery.error ? (
                    <>
                      <div className="os-resolve-cand-grid is-single">{candidateA}</div>
                      <div className="os-resolve-note is-error">
                        <AlertTriangle />
                        <span>
                          建议加载失败：
                          {(suggestionsQuery.error as ApiError).message || "网络错误"}
                        </span>
                      </div>
                    </>
                  ) : !topSuggestion ? (
                    <>
                      <div className="os-resolve-cand-grid is-single">{candidateA}</div>
                      <div className="os-resolve-note">
                        <Info />
                        <span>
                          无相似建议（同类型相似度均低于阈值）。可直接确认入图或驳回归档。
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="os-resolve-cand-grid">
                        {candidateA}
                        <CandidateCard
                          role="B"
                          tone="warning"
                          name={topSuggestion.canonical_name}
                          etype={topSuggestion.etype}
                          etypeLabel={etypeLabelOf(topSuggestion.etype)}
                          suggestion={topSuggestion}
                        />
                      </div>
                      <div className="os-resolve-note">
                        <Info />
                        <span>
                          合并后 <b>{topSuggestion.canonical_name}</b> 作为别名并入{" "}
                          <b>{selectedEntity.canonical_name}</b>；关系与证据保留并改挂主实体，操作写入审计日志。
                        </span>
                      </div>
                      <div className="os-resolve-merge-actions">
                        <button
                          type="button"
                          disabled={
                            mergeMutation.isPending ||
                            !canReviewActions ||
                            selectedReview.phase !== "idle"
                          }
                          onClick={() =>
                            handleMerge(
                              topSuggestion.id,
                              selectedEntity.id,
                              topSuggestion.canonical_name,
                              selectedEntity.canonical_name,
                            )
                          }
                          className="os-btn os-btn-primary"
                        >
                          {mergeMutation.isPending ? (
                            <Loader2 className="animate-spin" />
                          ) : (
                            <GitMerge />
                          )}
                          确认合并
                        </button>
                        <button
                          type="button"
                          onClick={() => setExpandedId(null)}
                          className="os-btn os-btn-secondary"
                        >
                          跳过
                        </button>
                        <span className="os-resolve-api">POST /resolution/merge</span>
                      </div>
                    </>
                  )}

                  {restSuggestions.length > 0 ? (
                    <>
                      <div className="os-resolve-section-title">
                        其他相似建议
                        <Chip tone="gray">{restSuggestions.length}</Chip>
                      </div>
                      <div className="os-resolve-suggest-list">
                        {restSuggestions.map((sug) => (
                          <div key={sug.id} className="os-resolve-suggest">
                            <div className="os-resolve-suggest-hd">
                              <b title={sug.canonical_name}>{sug.canonical_name}</b>
                              <Chip tone={sug.action === "auto_merge" ? "primary" : "warning"}>
                                {actionLabel(sug.action)}
                              </Chip>
                              <span className="os-resolve-sim">{sug.similarity.toFixed(2)}</span>
                            </div>
                            <div className="os-resolve-suggest-meta">
                              {etypeLabelOf(sug.etype)}
                              <span className="os-resolve-meta-sep">·</span>
                              相似度 {sug.similarity.toFixed(2)}
                            </div>
                            <div className="os-resolve-suggest-actions">
                              <button
                                type="button"
                                disabled={
                                  mergeMutation.isPending ||
                                  !canReviewActions ||
                                  selectedReview.phase !== "idle"
                                }
                                onClick={() =>
                                  handleMerge(
                                    sug.id,
                                    selectedEntity.id,
                                    sug.canonical_name,
                                    selectedEntity.canonical_name,
                                  )
                                }
                                className="os-btn os-btn-secondary os-btn-sm"
                              >
                                {mergeMutation.isPending ? (
                                  <Loader2 className="animate-spin" />
                                ) : (
                                  <GitMerge />
                                )}
                                合并到 A
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : null}

                  <div className="os-resolve-review">
                    <div className="os-resolve-section-title">本条审核</div>
                    {selectedReview.phase === "running" ? (
                      <div
                        className="os-resolve-review-state is-info"
                        data-testid="resolution-review-running"
                      >
                        <Loader2 className="animate-spin" />
                        正在同步投影入图（提交后全局刷新断言图，实测约需 10–60
                        秒）——请勿刷新或离开本页
                      </div>
                    ) : selectedReview.phase === "done" && selectedReview.outcome ? (
                      selectedReview.outcome === "ok" ? (
                        <div
                          className="os-resolve-review-state is-ok"
                          data-testid="resolution-review-outcome"
                        >
                          <CheckCircle2 />
                          {selectedReview.decision === "reject"
                            ? "已驳回归档（rejected，实体与提及保留）"
                            : "已确认入图（断言图已更新）"}
                        </div>
                      ) : selectedReview.outcome === "degraded" ? (
                        <div
                          className="os-resolve-review-state is-warn"
                          data-testid="resolution-review-outcome"
                        >
                          <AlertTriangle />
                          投影未生效（degraded）：已提交；管理员重跑全量装载即自动对账，数据无损失
                        </div>
                      ) : (
                        <div
                          className="os-resolve-review-state is-muted"
                          data-testid="resolution-review-outcome"
                        >
                          <RefreshCw />
                          状态已变更（可能已驳回/已合并），请刷新
                        </div>
                      )
                    ) : (
                      <div className="os-resolve-review-actions">
                        <button
                          type="button"
                          disabled={batchMutation.isPending || !canReviewActions}
                          onClick={() => handleReview(selectedEntity.id, "confirm")}
                          data-testid="resolution-confirm"
                          className="os-btn os-btn-primary"
                        >
                          <Check />
                          确认入图
                        </button>
                        <button
                          type="button"
                          disabled={batchMutation.isPending || !canReviewActions}
                          onClick={() => handleReview(selectedEntity.id, "reject")}
                          data-testid="resolution-reject"
                          className="os-btn os-btn-secondary is-danger"
                        >
                          <X />
                          驳回
                        </button>
                        <span className="os-resolve-review-note">
                          确认后实体入图并即时生效；驳回保留实体与提及。
                        </span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </Panel>

          <div className="os-resolve-side">
            <Panel title="操作反馈四态" subtitle="确认后即时回显" className="os-resolve-panel">
              <div className="os-resolve-feedback">
                <div className="os-resolve-feedback-row">
                  <span className="os-resolve-dot is-ok" />
                  <div>
                    <b>成功</b>
                    <span>projected:true · 行内绿勾「已入图」</span>
                  </div>
                </div>
                <div className="os-resolve-feedback-row">
                  <span className="os-resolve-dot is-warn" />
                  <div>
                    <b>降级</b>
                    <span>projected:false · 黄警 + 重跑全量装载自动对账</span>
                  </div>
                </div>
                <div className="os-resolve-feedback-row">
                  <span className="os-resolve-dot is-muted" />
                  <div>
                    <b>冲突 409</b>
                    <span>状态已变更 · 中性提示，不渲染为已确认</span>
                  </div>
                </div>
                <div className="os-resolve-feedback-row">
                  <span className="os-resolve-dot is-info" />
                  <div>
                    <b>在途</b>
                    <span>按钮禁用 + spinner · 同步投影约 10–60 秒</span>
                  </div>
                </div>
              </div>
            </Panel>

            <Panel
              title="合并状态"
              subtitle="可回放"
              icon={GitMerge}
              className="os-resolve-panel"
            >
              <div className="os-resolve-merge-state">
                <div className="os-kv">
                  <span className="os-kv-k">已合并实体</span>
                  <span className="os-kv-v os-resolve-conf">{mergedCount ?? "—"}</span>
                </div>
                <div className="os-kv">
                  <span className="os-kv-k">最近合并</span>
                  <span
                    className="os-kv-v"
                    title={
                      undoable
                        ? `${undoable.candidateName} → ${undoable.canonicalName}`
                        : undefined
                    }
                  >
                    {undoable ? `${undoable.candidateName} → ${undoable.canonicalName}` : "—"}
                  </span>
                </div>
              </div>
              {undoable ? (
                <div className="os-resolve-undo" data-testid="resolution-undo">
                  <Undo2 />
                  <div>
                    <b>可撤销</b>
                    <span>撤销后实体与别名关系还原</span>
                  </div>
                  <button
                    type="button"
                    disabled={unmergeMutation.isPending}
                    onClick={() => unmergeMutation.mutate(undoable.mergeId)}
                    className="os-btn os-btn-secondary os-btn-sm"
                  >
                    {unmergeMutation.isPending ? <Loader2 className="animate-spin" /> : null}
                    撤销
                  </button>
                </div>
              ) : (
                <div className="os-resolve-empty-sm">暂无合并记录</div>
              )}
            </Panel>

            <Panel
              title="质量约束"
              subtitle="合并前置校验"
              icon={ShieldCheck}
              className="os-resolve-panel"
            >
              <div className="os-resolve-check-list">
                <div className="os-resolve-check-item">
                  <span className="os-resolve-check-ic is-err">
                    <AlertTriangle />
                  </span>
                  <div>
                    <b>主键唯一</b>
                    <span>合并后 uri 必须唯一，冲突则失败</span>
                  </div>
                </div>
                <div className="os-resolve-check-item">
                  <span className="os-resolve-check-ic is-warn">
                    <AlertTriangle />
                  </span>
                  <div>
                    <b>类型相容</b>
                    <span>仅同 etype 可合并，跨类型需人工判定</span>
                  </div>
                </div>
                <div className="os-resolve-check-item">
                  <span className="os-resolve-check-ic is-ok">
                    <Check />
                  </span>
                  <div>
                    <b>证据留存</b>
                    <span>驳回不删数据，mention 永久保留</span>
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
