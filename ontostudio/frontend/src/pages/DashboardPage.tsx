/**
 * 01 工作台总览（EAI-CUSTOM, 2026-09-27 原型重构）——运营仪表盘。
 *
 * 布局对照 docs/designs/ontostudio-frontend-redesign-20260926.html#dashboard，
 * 数据面全部接真端点：
 * - 瓦片：dg 实体/关系计数（POST /ontology/aggregate group_by domain|predicate）；
 *   待审（doc-graph resolution pending，与侧栏红点同 key 共享缓存）；推理物化
 *   （订阅 ["formal","infer"] 缓存，ReasoningPage 运行后出现——不自动跑全量推理）
 * - 域健康：registry 文件 × summary（类/谓词数）× aggregate 域计数 + cross_module
 *   链路禁用真信号（object-types link_types enabled:false）
 * - 三小卡：校验状态（GET /formal/validate，与校验中心同 key 共享）；数据面
 *   （registry 版本 + 全量装载按钮，二次确认 + 失败可见）；抽取活动（任务统计真数据）
 * - 治理合规链：CONSTRUCT 规则真实派生计数（与推理工作台同源 rule_counts，零硬编码；
 *   逐条物化下钻已列入待办）
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Database,
  FileInput,
  GitBranch,
  Layers,
  UserCheck,
  LayoutDashboard,
  Loader2,
  Network,
  PlayCircle,
  RefreshCw,
  Share2,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import {
  fetchAggregate,
  fetchObjectTypes,
  fetchPendingReviewCount,
  fetchRegistryMeta,
} from "@/api/ontology-graph-api";
import {
  fetchFormalValidate,
  fetchInferLast,
  runFormalLoad,
  type FormalLoadResult,
} from "@/api/formal-api";
import { fetchRegistryContent, fetchRegistryFiles } from "@/api/registry-api";
import { fetchTaskStats } from "@/api/ingest-tasks-api";
import { ruleRows } from "@/pages/ReasoningPage";
import { domainAlias } from "@/lib/terms";
import { PageHeader, Panel } from "@/pages/shared";
import { withAlpha } from "@/explorer/graphTheme";
import { cn } from "@/lib/utils";

/** ms → human duration (<1s in ms, otherwise rounded seconds). */
function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `约 ${Math.round(ms / 1000)} 秒`;
}

// ── Multi-color system (EAI-CUSTOM 2026-10-20): prototype indigo / orange / zinc palette ──
// indigo = primary/entities, orange = pending, purple = relations, teal = inference, green = validation.
// Discipline: color only on icon chips / borders / 5% fills / dots; numbers stay ink for contrast.
const TONE_BLUE = "#4f46e5";
const TONE_PURPLE = "#7c3aed";
const TONE_CYAN = "#0e9488";
const TONE_AMBER = "#ea580c";
const TONE_GREEN = "#2f8f3e";
const TONE_RED = "#cf1322";
/** Domain row dot rotation (registry file order). */
const DOMAIN_DOTS = [TONE_BLUE, TONE_AMBER, TONE_CYAN, TONE_PURPLE, TONE_GREEN, TONE_RED];
/** Governance chain left-border rotation. */
const CHAIN_TONES = [TONE_BLUE, TONE_PURPLE, TONE_CYAN];
/** Deep variants for small text (WCAG 4.5:1): same hue, higher contrast. */
const TONE_TEXT: Record<string, string> = {
  [TONE_BLUE]: "#4338ca",
  [TONE_PURPLE]: "#6d28d9",
  [TONE_CYAN]: "#0f766e",
  [TONE_AMBER]: "#c2410c",
  [TONE_GREEN]: "#2f8f3e",
  [TONE_RED]: "#cf1322",
};
const toneText = (tone: string) => TONE_TEXT[tone] ?? tone;

/** Pipeline station colors (rail + node rings share the same source). */
const PIPE_COLORS = ["#4f46e5", "#ea580c", "#7c3aed", "#0e9488", "#2f8f3e"];

function go(route: string) {
  window.location.hash = route;
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("os-skeleton rounded", className)} />;
}

/** 首次进入总览时的整页骨架，避免先闪出一屏 0 / 空表。 */
function DashboardSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="工作台总览加载中">
      <span className="sr-only">工作台总览加载中…</span>

      {/* 页头 */}
      <div className="os-page-head">
        <SkeletonBlock className="h-[38px] w-[38px] flex-none rounded-[9px]" />
        <div className="os-ph-main min-w-0 flex-1 space-y-2">
          <SkeletonBlock className="h-2.5 w-16" />
          <SkeletonBlock className="h-5 w-32" />
          <SkeletonBlock className="h-3 w-80 max-w-full" />
        </div>
        <div className="os-ph-actions">
          <SkeletonBlock className="h-5 w-20 rounded-full" />
          <SkeletonBlock className="h-[30px] w-24" />
          <SkeletonBlock className="h-[30px] w-24" />
        </div>
      </div>

      {/* 指标条 */}
      <div className="os-metric-strip">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="os-metric">
            <div className="flex items-center gap-1.5">
              <SkeletonBlock className="h-3 w-3 flex-none" />
              <SkeletonBlock className="h-3 w-14" />
            </div>
            <SkeletonBlock className="mt-2 h-6 w-16" />
            <SkeletonBlock className="mt-2 h-3 w-28" />
          </div>
        ))}
      </div>

      {/* 管线 */}
      <section className="os-card os-pipeline-panel mb-3.5">
        <div className="os-card-hd">
          <SkeletonBlock className="h-4 w-4 flex-none" />
          <SkeletonBlock className="h-4 w-20 flex-none" />
          <SkeletonBlock className="h-3 w-48 max-w-full" />
          <div className="os-card-right">
            <SkeletonBlock className="h-3 w-32" />
          </div>
        </div>
        <div className="os-step-rail">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="os-step pointer-events-none">
              <SkeletonBlock className="h-[22px] w-[22px] flex-none rounded-full" />
              <div className="min-w-0 flex-1 space-y-1.5">
                <SkeletonBlock className="h-3.5 w-12" />
                <SkeletonBlock className="h-3 w-24 max-w-full" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 业务域 + 治理链 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <section key={i} className="os-card flex min-h-[260px] flex-col">
            <div className="os-card-hd">
              <SkeletonBlock className="h-4 w-4 flex-none" />
              <SkeletonBlock className="h-4 w-24 flex-none" />
              <SkeletonBlock className="h-3 w-32 max-w-full" />
            </div>
            <div className="os-card-bd flex-1 space-y-3.5">
              {Array.from({ length: 5 }).map((__, j) => (
                <div key={j} className="flex items-center gap-3">
                  <SkeletonBlock className="h-3 w-3 flex-none" />
                  <SkeletonBlock className="h-3 flex-1" />
                  <SkeletonBlock className="h-3 w-10 flex-none" />
                  <SkeletonBlock className="h-3 w-10 flex-none" />
                  <SkeletonBlock className="h-3 w-14 flex-none" />
                </div>
              ))}
            </div>
            <div className="os-card-foot">
              <SkeletonBlock className="h-3 w-3 flex-none" />
              <SkeletonBlock className="h-3 w-64 max-w-full" />
            </div>
          </section>
        ))}
      </div>

      {/* 校验 / 同步 / 抽取活动 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <section key={i} className="os-card flex min-h-[220px] flex-col">
            <div className="os-card-hd">
              <SkeletonBlock className="h-4 w-4 flex-none" />
              <SkeletonBlock className="h-4 w-20 flex-none" />
            </div>
            <div className="os-card-bd flex flex-1 flex-col gap-3">
              <SkeletonBlock className="h-4 w-2/3" />
              <SkeletonBlock className="h-3 w-1/2" />
              <SkeletonBlock className="h-14 w-full" />
              <SkeletonBlock className="mt-auto h-[30px] w-24" />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

export function DashboardPage() {
  // ── 真数据源 ──
  const entAggQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_entity", "domain"],
    queryFn: ({ signal }) => fetchAggregate("graph_entity", "domain", { signal }),
    staleTime: 60_000,
  });
  const relAggQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_relation", "predicate"],
    queryFn: ({ signal }) => fetchAggregate("graph_relation", "predicate", { signal }),
    staleTime: 60_000,
  });
  const pendingQuery = useQuery({
    queryKey: ["ontology", "pending-review-count"],
    queryFn: fetchPendingReviewCount,
    staleTime: 30_000,
    retry: false,
  });
  // 推理物化：只订阅缓存（ReasoningPage 运行后出现），不自动跑全量推理（worker 秒级占用）
  const inferQuery = useQuery({
    queryKey: ["formal", "infer"],
    queryFn: fetchInferLast,
    enabled: false,
    staleTime: 5 * 60_000,
  });
  const validateQuery = useQuery({
    queryKey: ["formal", "validate"],
    queryFn: fetchFormalValidate,
    staleTime: 30_000,
  });
  // 抽取活动（真数据，T6）：任务计数 + 置信度分布——仪表盘非操作位，30s 轮询足够
  const activityQuery = useQuery({
    queryKey: ["ingest", "task-stats"],
    queryFn: ({ signal }) => fetchTaskStats(signal),
    refetchInterval: 30_000,
  });
  const activityActive = Object.entries(activityQuery.data?.tasks_by_status ?? {})
    .filter(([s]) => s === "queued" || s === "extracting" || s === "loading")
    .reduce((acc, [, v]) => acc + v, 0);
  const activityDone = activityQuery.data?.tasks_by_status?.done ?? 0;
  const activityFailed =
    (activityQuery.data?.tasks_by_status?.failed ?? 0) + (activityQuery.data?.tasks_by_status?.aborted ?? 0);
  const typesQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
    staleTime: 60_000,
  });
  const registryMetaQuery = useQuery({
    queryKey: ["ontology", "registry"],
    queryFn: fetchRegistryMeta,
    staleTime: 60_000,
  });
  const filesQuery = useQuery({
    queryKey: ["ontology", "registry-files"],
    queryFn: fetchRegistryFiles,
    staleTime: 5 * 60_000,
  });
  const files = filesQuery.data?.files ?? [];
  // 每个域文件的 summary（类/谓词数）——并行小请求
  const contentQueries = useQueries({
    queries: files.map((file) => ({
      queryKey: ["registry-content", file],
      queryFn: () => fetchRegistryContent(file),
      staleTime: 5 * 60_000,
    })),
  });

  // ── 派生 ──
  const entRows = entAggQuery.data ?? [];
  const entityTotal = entRows.reduce((sum, r) => sum + r.value, 0);
  const topDomain = entRows[0];
  const relationTotal = (relAggQuery.data ?? []).reduce((sum, r) => sum + r.value, 0);
  const pending = pendingQuery.data ?? null;
  const conformance = validateQuery.data?.conformance ?? [];
  const passedCount = conformance.filter((c) => c.passed).length;
  const violationCount = validateQuery.data?.shacl.violations ?? [];
  const disabledLinks = (typesQuery.data?.link_types ?? []).filter((lt) => !lt.enabled);

  // 域健康行：registry 文件 × summary × aggregate 计数
  const domainRows = files.map((file, i) => {
    const domain = file.replace(/\.yaml$/, "");
    const domainSummary = contentQueries[i]?.data?.summary?.domains?.[domain];
    const predicates = domainSummary?.predicates?.length ?? 0;
    const count = entRows.find((r) => r.group === domain)?.value ?? 0;
    const disabledHere = domain === "cross_module" && disabledLinks.length > 0;
    return {
      domain,
      classes: domainSummary?.classes?.length ?? 0,
      predicates,
      count,
      disabledHere,
    };
  });

  // ── 装载对账 ──
  const [loadResult, setLoadResult] = useState<FormalLoadResult | null>(null);
  const qc = useQueryClient();
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) => {
      setLoadResult(data);
      // 装载重写内核图 → 校验中心缓存失效（校验口径：装载后可重跑）
      void qc.invalidateQueries({ queryKey: ["formal", "validate"] });
    },
  });

  // ── 待办主轴 + 管线健康（V4 信息架构增量，CEO 复审追加）──
  const todoFailed = activityFailed;
  const todoActive = activityActive;
  // 「需关注」口径与管线健康轨道一致：待审积压 / 失败任务 / 校验未全过（F7）
  const validationWarn =
    validateQuery.data && conformance.length > 0 && (passedCount < conformance.length || violationCount.length > 0)
      ? 1
      : 0;
  const attentionItems =
    (pending !== null && pending > 0 ? 1 : 0) + (todoFailed > 0 ? 1 : 0) + validationWarn;
  // 管线各站状态：抽取=有进行中则琥珀；审核=有待审则琥珀；图=恒绿（对账见同步卡）；
  // 推理=未运行灰/已运行绿；校验=全过绿否则琥珀
  const stageExtract: "ok" | "warn" = todoActive > 0 ? "warn" : "ok";
  const stageReview: "ok" | "warn" = pending !== null && pending > 0 ? "warn" : "ok";
  const stageInfer: "ok" | "idle" = inferQuery.data ? "ok" : "idle";
  const stageValidate: "ok" | "warn" =
    validateQuery.data && conformance.length > 0 && passedCount === conformance.length && violationCount.length === 0
      ? "ok"
      : "warn";

  // Pipeline health rail: node value/state + click-through per station.
  const pipeNodes = [
    { nm: "抽取", color: PIPE_COLORS[0], icon: FileInput, state: stageExtract, legendNum: activityDone as number | null, legendUnit: "完成", sub: todoActive > 0 ? `进行中 ${todoActive}` : "队列空闲", onClick: () => go("ingest") },
    { nm: "人工审核", color: PIPE_COLORS[1], icon: UserCheck, state: stageReview, legendNum: pending, legendUnit: "待确认", sub: pending !== null && pending > 0 ? "积压 · 建议尽快清零" : "无积压", onClick: () => go("resolve") },
    { nm: "知识图谱", color: PIPE_COLORS[2], icon: Network, state: "ok" as const, legendNum: entityTotal, legendUnit: "节点", sub: `关系 ${relationTotal.toLocaleString()} 条`, onClick: () => go("entities") },
    { nm: "推理", color: PIPE_COLORS[3], icon: BrainCircuit, state: stageInfer, legendNum: null as number | null, legendUnit: "未运行", sub: inferQuery.data ? `闭包 ${formatDuration(inferQuery.data.duration_ms)}` : "前往推理工作台运行", onClick: () => go("reasoning") },
    { nm: "校验", color: PIPE_COLORS[4], icon: ShieldCheck, state: stageValidate, legendNum: validateQuery.data ? passedCount : null, legendUnit: `/ ${conformance.length} 通过`, sub: `SHACL 违规 ${violationCount.length}`, onClick: () => go("validation") },
  ];


  // 治理合规链（G5/H1 接真）：与推理工作台同源 rule_counts，派生数降序取前 4——零硬编码
  const derivedRules = inferQuery.data
    ? [...ruleRows(inferQuery.data.rule_counts)].sort((a, b) => b.count - a.count).slice(0, 4)
    : null;

  // 首次进入：等待核心计数、管线、域明细和治理数据，避免先闪出 0 / 空表。
  const dashboardInitialLoading =
    entAggQuery.isLoading ||
    relAggQuery.isLoading ||
    pendingQuery.isLoading ||
    validateQuery.isLoading ||
    activityQuery.isLoading ||
    typesQuery.isLoading ||
    registryMetaQuery.isLoading ||
    filesQuery.isLoading ||
    (files.length > 0 && contentQueries.some((query) => query.isLoading));

  if (dashboardInitialLoading) {
    return (
      <div className="h-full overflow-x-auto overflow-y-auto">
        <div className="os-page">
          <DashboardSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="os-page">
        <PageHeader
          clause="01 · 总览"
          icon={LayoutDashboard}
          title="工作台总览"
          description="知识层运营一览：数据沉淀、待审压力、域健康、校验与数据面状态。"
          actions={
            <>
              {pending === null ? (
                <span className="os-pill os-pill-gray">加载中</span>
              ) : attentionItems > 0 ? (
                <span className="os-pill os-pill-warn">
                  <Activity className="h-3 w-3" />
                  {attentionItems} 项需关注
                </span>
              ) : (
                <span className="os-pill os-pill-ok">
                  <ShieldCheck className="h-3 w-3" />
                  管线健康
                </span>
              )}
              {entAggQuery.isFetching || relAggQuery.isFetching ? (
                <Loader2 className="text-primary h-4 w-4 animate-spin" />
              ) : null}
              <button
                type="button"
                className="os-btn os-btn-secondary os-btn-sm"
                onClick={() => go("ingest")}
              >
                <FileInput />
                抽取管线
              </button>
              <button
                type="button"
                className="os-btn os-btn-primary os-btn-sm"
                onClick={() => go("resolve")}
              >
                <UserCheck />
                处理待审
              </button>
            </>
          }
        />

        {/* 指标条：六个真实计数，均可下钻 */}
        <div className="os-metric-strip">
          <button
            type="button"
            className="os-metric"
            onClick={() => go("resolve")}
            title="进入消解审核"
          >
            <span className="os-metric-label">
              <UserCheck className="h-3 w-3" style={{ color: TONE_AMBER }} />
              待审实体
            </span>
            <span className="os-metric-value" style={{ color: toneText(TONE_AMBER) }}>
              {pending ?? "—"}
              <small>条</small>
            </span>
            <span className="os-metric-foot">
              {pending === null ? "加载中…" : pending > 0 ? "待人工确认 · 支持批量处理" : "已清零"}
            </span>
          </button>

          <button
            type="button"
            className="os-metric"
            onClick={() => go("ingest")}
            title="进入抽取导入"
          >
            <span className="os-metric-label">
              <AlertTriangle className="h-3 w-3" style={{ color: TONE_RED }} />
              失败任务
            </span>
            <span
              className="os-metric-value"
              style={todoFailed > 0 ? { color: toneText(TONE_RED) } : undefined}
            >
              {activityQuery.isLoading ? "…" : todoFailed}
              <small>条</small>
            </span>
            <span className="os-metric-foot">抽取队列 · 含中断任务</span>
          </button>

          <button
            type="button"
            className="os-metric"
            onClick={() => go("ingest")}
            title="进入抽取导入"
          >
            <span className="os-metric-label">
              <RefreshCw
                className={cn("h-3 w-3", todoActive > 0 && "animate-spin")}
                style={{ color: TONE_CYAN }}
              />
              进行中
            </span>
            <span className="os-metric-value">
              {activityQuery.isLoading ? "…" : todoActive}
              <small>个</small>
            </span>
            <span className="os-metric-foot">今日已完成 {activityDone}</span>
          </button>

          <button
            type="button"
            className="os-metric"
            onClick={() => go("entities")}
            title="进入实体库"
          >
            <span className="os-metric-label">
              <Database className="h-3 w-3" style={{ color: TONE_BLUE }} />
              实体
            </span>
            <span className="os-metric-value">
              {entAggQuery.isLoading ? "…" : entityTotal.toLocaleString()}
              <small>行</small>
            </span>
            <span className="os-metric-foot">
              {topDomain?.group
                ? `最大域 ${domainAlias(topDomain.group) ?? topDomain.group} · ${topDomain.value.toLocaleString()}`
                : "跨域合计 · dg_entities"}
            </span>
          </button>

          <button
            type="button"
            className="os-metric"
            onClick={() => go("graph")}
            title="进入图谱浏览"
          >
            <span className="os-metric-label">
              <Share2 className="h-3 w-3" style={{ color: TONE_PURPLE }} />
              关系
            </span>
            <span className="os-metric-value">
              {relAggQuery.isLoading ? "…" : relationTotal.toLocaleString()}
              <small>条</small>
            </span>
            <span className="os-metric-foot">两端实体都存在的关系</span>
          </button>

          <button
            type="button"
            className="os-metric"
            onClick={() => go("reasoning")}
            title="前往推理工作台"
          >
            <span className="os-metric-label">
              <BrainCircuit className="h-3 w-3" style={{ color: TONE_CYAN }} />
              推理物化
            </span>
            <span className="os-metric-value">
              {inferQuery.isLoading
                ? "…"
                : inferQuery.data
                  ? inferQuery.data.entailment_triples.toLocaleString()
                  : "—"}
              {inferQuery.data ? <small>条</small> : null}
            </span>
            <span className="os-metric-foot">
              {inferQuery.data
                ? `闭包 ${formatDuration(inferQuery.data.duration_ms)}`
                : "未运行 · 前往推理工作台"}
            </span>
          </button>
        </div>

        {/* 管线健康：五站轨道，站内数字全部真数据 */}
        <Panel
          title="管线健康"
          subtitle="抽取 → 人工审核 → 知识图谱 → 推理 → 校验"
          tone={TONE_BLUE}
          icon={Network}
          className="os-pipeline-panel mb-3.5"
          actions={
            <span className="os-card-hd-hint text-muted-foreground text-[12px]">
              点击任一站点进入对应页面
            </span>
          }
        >
          <div className="os-step-rail">
            {pipeNodes.map((nd) => (
              <button
                key={nd.nm}
                type="button"
                onClick={nd.onClick}
                title={`前往${nd.nm}页面 · ${nd.sub}`}
                className={cn("os-step", nd.state)}
              >
                <span className="os-step-dot">
                  <nd.icon />
                </span>
                <span className="min-w-0">
                  <span className="os-step-name">{nd.nm}</span>
                  <span className="os-step-state">
                    <b className="tabular-nums" style={{ color: toneText(nd.color ?? TONE_BLUE) }}>
                      {nd.legendNum === null ? "—" : nd.legendNum.toLocaleString()}
                    </b>{" "}
                    {nd.legendUnit} · {nd.sub}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </Panel>

        {/* 域健康 + 治理链 */}
        <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          <Panel
            title="业务域概况"
            subtitle="各域模型与数据量"
            tone={TONE_BLUE}
            icon={Layers}
            className="os-domain-panel flex max-h-[420px] flex-col overflow-hidden"
            actions={
              <span className="os-pill os-pill-gray">{domainRows.length} 个域</span>
            }
          >
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="os-table os-domain-table">
                <thead>
                  <tr>
                    {["域", "类", "谓词", "实体行", "状态"].map((h, i) => (
                      <th key={h} className={i === 0 ? "text-left" : "text-center"}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {domainRows.map((row, i) => {
                    const dot = DOMAIN_DOTS[i % DOMAIN_DOTS.length] ?? TONE_BLUE;
                    return (
                      <tr
                        key={row.domain}
                        className="cursor-pointer"
                        title={`前往本体建模器查看「${domainAlias(row.domain) ?? row.domain}」域模型`}
                        onClick={() => go(`modeler:${row.domain}`)}
                      >
                        <td>
                          <span className="flex items-center gap-2">
                            <span
                              className="h-2 w-2 flex-none rounded-full"
                              style={{ background: dot }}
                            />
                            <span className="min-w-0">
                              <span className="os-cell-main block truncate">
                                {domainAlias(row.domain) ?? row.domain}
                              </span>
                              <span className="os-cell-sub block truncate">
                                {row.domain}.yaml
                              </span>
                            </span>
                          </span>
                        </td>
                        <td className="num text-center">{row.classes}</td>
                        <td className="num text-center">{row.predicates}</td>
                        <td className="num text-center">{row.count.toLocaleString()}</td>
                        <td className="text-center">
                          {row.disabledHere ? (
                            <span
                              className="os-pill os-pill-err"
                              title={`${disabledLinks.length} 条跨域链路禁用`}
                            >
                              链路禁用
                            </span>
                          ) : row.count > 0 ? (
                            <span className="os-pill os-pill-ok">活跃</span>
                          ) : (
                            <span className="text-muted-foreground text-[12px]">暂无实体</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {domainRows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="text-muted-foreground py-8 text-center text-[11px]"
                      >
                        {filesQuery.isLoading ? "加载 registry…" : "registry 为空"}
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <div className="os-card-foot flex-none">
              <GitBranch className="h-3 w-3 flex-none" />
              <span title="cross_module" className="text-[12px]">
                跨域链路 {disabledLinks.length} 条禁用——单域闭环优先，跨域待业务触发。
              </span>
            </div>
          </Panel>

          <Panel
            title="治理合规链 · 规则派生"
            subtitle="CONSTRUCT 真实派生计数（与推理工作台同源）"
            tone={TONE_PURPLE}
            icon={Network}
            className="os-governance-panel flex flex-col"
            actions={
              <button
                type="button"
                onClick={() => go("reasoning")}
                className="os-btn os-btn-ghost os-btn-sm"
              >
                推理工作台 <ArrowRight />
              </button>
            }
          >
            {derivedRules === null ? (
              <div className="os-card-bd flex flex-1 flex-col justify-center gap-3">
                <div className="os-note">
                  <BrainCircuit />
                  <span>推理尚未运行——运行后此处展示各治理合规链规则的真实派生计数。</span>
                </div>
                <button
                  type="button"
                  onClick={() => go("reasoning")}
                  className="os-btn os-btn-secondary os-btn-sm self-start"
                >
                  前往推理工作台 <ArrowRight />
                </button>
              </div>
            ) : derivedRules.length === 0 ? (
              <p className="os-card-bd text-muted-foreground flex-1 text-[12px]">
                推理已运行，当前规则集暂无派生记录。
              </p>
            ) : (
              <ol className="flex flex-1 flex-col">
                {derivedRules.map((rule, i) => {
                  const tone = CHAIN_TONES[i % CHAIN_TONES.length] ?? TONE_BLUE;
                  return (
                    <li
                      key={rule.name}
                      className="border-border flex items-start gap-2 border-b px-4 py-2.5 last:border-0"
                    >
                      <span
                        className="mt-1.5 h-2 w-2 flex-none rounded-full"
                        style={{ background: tone }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <b className="truncate text-[13px]">{rule.desc}</b>
                          <span
                            className="os-pill ml-auto flex-none"
                            style={{
                              background: withAlpha(tone, 0.1),
                              color: toneText(tone),
                            }}
                            title={`派生三元组数（named graph: ${rule.graph}）`}
                          >
                            {rule.count} 条
                          </span>
                        </div>
                        <div
                          className="os-cell-sub truncate"
                          title={`规则 ${rule.name} · 谓词 ${rule.pred}`}
                        >
                          {rule.name} · {rule.pred}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
            <p className="os-card-foot flex-none">
              逐条派生明细与图面判据见导出互操作页。
            </p>
          </Panel>
        </div>

        {/* 三小卡：绿=校验 蓝=数据面 青=抽取 */}
        <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-3">
          <Panel
            title="校验状态"
            tone={TONE_GREEN}
            icon={ShieldCheck}
            className="os-validation-panel flex flex-col"
          >
            <div className="os-card-bd flex flex-1 flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold">GB/T 48000.3—2026</div>
                  <div className="text-muted-foreground text-[12px]">
                    本体建模符合性 · C1–C5 部分条款
                  </div>
                </div>
                <span
                  className={cn(
                    "os-pill flex-none",
                    validateQuery.isError
                      ? "os-pill-err"
                      : validateQuery.data &&
                          conformance.length > 0 &&
                          passedCount === conformance.length
                        ? "os-pill-ok"
                        : "os-pill-warn",
                  )}
                >
                  {validateQuery.isError
                    ? "获取失败"
                    : validateQuery.data
                      ? `${passedCount} / ${conformance.length} 通过`
                      : "加载中…"}
                </span>
              </div>
              <div className="os-kv">
                <span className="os-kv-k">SHACL 违规</span>
                <span className="os-kv-v">
                  <b className={violationCount.length > 0 ? "text-destructive" : ""}>
                    {violationCount.length}
                  </b>{" "}
                  项
                </span>
              </div>
              <div className="os-kv">
                <span className="os-kv-k">判定口径</span>
                <span className="os-kv-v">C1–C5 · 附录 A</span>
              </div>
              <button
                type="button"
                onClick={() => go("validation")}
                className="os-btn os-btn-secondary os-btn-sm mt-auto self-start"
              >
                进入校验中心 <ArrowRight />
              </button>
            </div>
          </Panel>

          <Panel
            title="图数据同步"
            subtitle="本体库与图保持一致"
            tone={TONE_BLUE}
            icon={Database}
            className="os-sync-panel flex flex-col"
          >
            <div className="os-card-bd flex flex-1 flex-col gap-1">
              <div className="os-kv">
                <span className="os-kv-k">registry 版本</span>
                <span className="os-kv-v">
                  <b className="font-mono">
                    v{registryMetaQuery.data?.registry_version ?? "—"}
                  </b>
                </span>
              </div>
              <div className="os-kv">
                <span className="os-kv-k">对象 / 链接类型</span>
                <span className="os-kv-v font-mono tabular-nums">
                  {registryMetaQuery.data
                    ? `${registryMetaQuery.data.object_type_count} / ${registryMetaQuery.data.link_type_count}`
                    : "—"}
                </span>
              </div>
              <div className="os-kv">
                <span className="os-kv-k">指纹</span>
                <span
                  className="os-kv-v truncate font-mono text-[13px]"
                  title={registryMetaQuery.data?.fingerprint}
                >
                  {registryMetaQuery.data?.fingerprint
                    ? registryMetaQuery.data.fingerprint.slice(0, 14)
                    : "—"}
                </span>
              </div>
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
                <button
                  type="button"
                  disabled={loadMutation.isPending}
                  onClick={() => {
                    // G4: full load rewrites dg_* tables (tens of seconds) — confirm + surface failures.
                    if (window.confirm("全量装载将重写图数据全表（耗时数十秒），确认执行？")) {
                      loadMutation.mutate();
                    }
                  }}
                  className="os-btn os-btn-secondary os-btn-sm"
                >
                  {loadMutation.isPending ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <PlayCircle />
                  )}
                  全量装载（对账）
                </button>
                {loadMutation.isError ? (
                  <span
                    className="text-destructive max-w-[16rem] truncate text-[12px]"
                    title={
                      loadMutation.error instanceof Error
                        ? loadMutation.error.message
                        : String(loadMutation.error)
                    }
                  >
                    装载失败：
                    {loadMutation.error instanceof Error
                      ? loadMutation.error.message
                      : String(loadMutation.error)}
                  </span>
                ) : loadResult ? (
                  <span className="text-muted-foreground font-mono text-[12px]">
                    {loadResult.entities} 实体 / {loadResult.relations} 关系已装载
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => go("export")}
                    className="os-btn os-btn-ghost os-btn-sm"
                  >
                    装载 / 导出 <ArrowRight />
                  </button>
                )}
              </div>
            </div>
          </Panel>

          <Panel
            title="抽取活动"
            subtitle="任务队列 · 实时"
            tone={TONE_CYAN}
            icon={FileInput}
            className="os-activity-panel flex flex-col"
          >
            <div className="os-card-bd flex flex-1 flex-col gap-2.5">
              {activityQuery.isLoading ? (
                <p className="text-muted-foreground flex items-center gap-1.5 text-[12px]">
                  <Loader2 className="h-3 w-3 animate-spin" /> 加载任务统计…
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: "进行中", value: activityActive, tone: TONE_CYAN },
                      { label: "已完成", value: activityDone, tone: TONE_GREEN },
                      {
                        label: "失败",
                        value: activityFailed,
                        tone: activityFailed > 0 ? TONE_RED : undefined,
                      },
                    ].map((stat) => (
                      <div
                        key={stat.label}
                        className="border-border rounded-md border px-2 py-1.5"
                      >
                        <div className="text-muted-foreground text-[13px]">{stat.label}</div>
                        <div
                          className="text-[17px] font-bold tabular-nums"
                          style={stat.tone ? { color: stat.tone } : undefined}
                        >
                          {stat.value}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
                    <span>置信度 高 {activityQuery.data?.confidence?.high ?? 0}</span>
                    <span>中 {activityQuery.data?.confidence?.mid ?? 0}</span>
                    <span>低 {activityQuery.data?.confidence?.low ?? 0}</span>
                  </div>
                  <p className="text-muted-foreground text-[12px] leading-relaxed">
                    任务=把样例库已提取产物批量写入图谱；开启强制人审的任务会全部进入消解审核。
                  </p>
                </>
              )}
              <button
                type="button"
                onClick={() => go("ingest")}
                className="os-btn os-btn-secondary os-btn-sm mt-auto self-start"
              >
                进入抽取导入 <ArrowRight />
              </button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
