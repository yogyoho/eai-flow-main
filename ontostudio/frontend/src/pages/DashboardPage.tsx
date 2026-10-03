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
import { useState, type ReactNode } from "react";

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

/** ms → 人话时长（<1s 显示毫秒，其余取整秒——F5：裸毫秒对操作者无感）。 */
function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `约 ${Math.round(ms / 1000)} 秒`;
}

/** 卡片头图标徽章（v4：圆点升级为贴切图标 + 软底色 chip，沿用 PageHeader 图标习语）。 */
function CardIcon({ bg, tone, children }: { bg: string; tone: string; children: ReactNode }) {
  return (
    <span
      className="grid h-7 w-7 flex-none place-items-center rounded-md"
      style={{ background: bg, color: tone }}
    >
      {children}
    </span>
  );
}

// ── 多色彩系统（EAI-CUSTOM 2026-09-27）──
// 与既有语义色同源的 Ant 家族色：蓝=主/实体 紫=关系 青=推理 琥珀=待审 绿=校验。
// 用法纪律：色只落在图标 chip / 边框 / 5% 色底 / 圆点上，数字保持 ink 深色（对比度）。
const TONE_BLUE = "#0746ff";
const TONE_PURPLE = "#722ed1";
const TONE_CYAN = "#13c2c2";
const TONE_AMBER = "#faad14";
const TONE_GREEN = "#52c41a";
const TONE_RED = "#ff4d4f";
/** 域行彩色圆点轮转（按 registry 文件序）。 */
const DOMAIN_DOTS = [TONE_BLUE, TONE_PURPLE, TONE_CYAN, TONE_GREEN, TONE_AMBER, TONE_RED];
/** 治理链左边框轮转。 */
const CHAIN_TONES = [TONE_BLUE, TONE_PURPLE, TONE_CYAN];
/** 小字号文本用深变体（WCAG 4.5:1）——色相不变、只提对比度（琥珀/青原值在白底不达标）。 */
const TONE_TEXT: Record<string, string> = {
  [TONE_BLUE]: "#0746ff",
  [TONE_PURPLE]: "#722ed1",
  [TONE_CYAN]: "#0e7490",
  [TONE_AMBER]: "#ad6800",
  [TONE_GREEN]: "#389e0d",
  [TONE_RED]: "#cf1322",
};
const toneText = (tone: string) => TONE_TEXT[tone] ?? tone;

/** 管线五站标识色（轨道分段与节点环同源）：抽取蓝 / 审核琥珀 / 图谱紫 / 推理青 / 校验绿 */
const PIPE_COLORS = ["#4d8dff", "#f5a623", "#7c5cd6", "#0e9488", "#1a7f4b"];

function go(route: string) {
  window.location.hash = route;
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

  // 管线健康轨道（A 轨道节点式）：节点值/状态 + 蓝线填充到首个非健康站
  const pipeValidateOk = !!(validateQuery.data && conformance.length > 0 && passedCount === conformance.length && violationCount.length === 0);
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

  return (
    /* 横向滚动（样式=全站 6px 细条，同合同价格分析页）：min-w 保四瓦片/双列布局
       不被窄视口压扁裁切，超出部分横向滚动查看 */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1100px] p-6">
      <PageHeader
        icon={LayoutDashboard}
        title="工作台总览"
        description="知识层运营一览：数据沉淀、待审压力、域健康、校验与数据面状态。"
        actions={
          entAggQuery.isFetching || relAggQuery.isFetching ? (
            <Loader2 className="text-primary h-4 w-4 animate-spin" />
          ) : null
        }
      />

      {/* 待办主轴——今天需要你处理（V4 信息架构） */}
      <div className="mb-3.5 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        <button
          type="button"
          onClick={() => go("resolve")}
          className="col-span-2 flex flex-col rounded-xl border p-3.5 text-left shadow-sm transition-all duration-200 hover:-translate-y-px cursor-pointer lg:col-span-1 lg:row-span-2"
          style={{
            background: `linear-gradient(135deg, ${withAlpha(TONE_AMBER, 0.08)}, ${withAlpha(TONE_AMBER, 0.02)} 60%), var(--card, #fff)`,
            borderColor: withAlpha(TONE_AMBER, 0.45),
          }}
        >
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
            <span className="bg-warning inline-block h-2 w-2 rounded-full" />
            现在需要你处理
            <span className="text-muted-foreground/70 text-xs">· 按批处理优先级</span>
          </div>
          <div className="mt-1.5 font-mono text-[40px] font-bold leading-tight tabular-nums" style={{ color: toneText(TONE_AMBER) }}>
            {pending ?? "—"}
            <small className="text-muted-foreground ml-2 text-sm font-normal">条实体待审</small>
          </div>
          <div className="text-muted-foreground mt-0.5 text-xs">已提取实体入图待人工确认 · 支持批量勾选</div>
          <span className="bg-primary text-primary-foreground mt-auto inline-flex items-center gap-1 self-start rounded-md px-3 py-1 text-xs font-medium">
            进入消解审核 →
          </span>
        </button>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon bg="var(--red-bg)" tone="var(--red)">
                <AlertTriangle className="h-3.5 w-3.5" />
              </CardIcon>
              <span className="min-w-0">
                失败任务
                <span className="text-muted-foreground block text-[10.5px] leading-tight">抽取队列 · 累计</span>
              </span>
            </span>
            <span className="flex-none font-mono text-2xl font-bold leading-none tabular-nums text-destructive">
              {todoFailed}
              <small className="text-muted-foreground block text-right text-[10px] font-normal">条</small>
            </span>
          </div>
        </div>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon
                bg={todoActive > 0 ? "var(--amber-soft)" : "var(--muted)"}
                tone={todoActive > 0 ? "var(--amber)" : "var(--ink-3)"}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", todoActive > 0 && "animate-spin")} />
              </CardIcon>
              <span className="min-w-0">
                进行中
                <span className="text-muted-foreground block text-[10.5px] leading-tight">今日已完成 {activityDone}</span>
              </span>
            </span>
            <span className="flex-none font-mono text-2xl font-bold leading-none tabular-nums text-success">
              {todoActive}
              <small className="text-muted-foreground block text-right text-[10px] font-normal">个</small>
            </span>
          </div>
        </div>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon
                bg={pending === null ? "var(--muted)" : attentionItems > 0 ? "var(--amber-soft)" : "var(--green-soft)"}
                tone={pending === null ? "var(--ink-3)" : attentionItems > 0 ? "var(--amber)" : "var(--green)"}
              >
                <Activity className={cn("h-3.5 w-3.5", pending !== null && todoActive > 0 && "animate-pulse")} />
              </CardIcon>
              <span className="min-w-0">
                系统状态
                <span className="text-muted-foreground block text-[10.5px] leading-tight">
                  {pending === null ? "加载中" : attentionItems > 0 ? "存在需处理项" : "管线各站健康"}
                </span>
              </span>
            </span>
            <span className={cn("flex-none font-mono text-2xl font-bold leading-none tabular-nums", pending !== null && attentionItems > 0 ? "text-[17px] text-warning" : "text-success")}>
              {pending === null ? "…" : attentionItems}
              <small className="block text-right text-[10px] font-normal">
                {pending === null ? "加载中" : attentionItems > 0 ? "项需关注" : "项待办"}
              </small>
            </span>
          </div>
        </div>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5" title="dg_entities 表行数（跨域合计）">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon bg="var(--blue-soft)" tone="var(--blue)">
                <Database className="h-3.5 w-3.5" />
              </CardIcon>
              <span className="min-w-0">
                实体
                <span className="text-muted-foreground block text-[10.5px] leading-tight">
                  {topDomain ? `最大域 ${topDomain.group ?? "—"} · ${topDomain.value} 行` : "—"}
                </span>
              </span>
            </span>
            <span className="flex-none font-mono text-2xl font-bold leading-none tabular-nums">
              {entAggQuery.isLoading ? "…" : entityTotal.toLocaleString()}
              <small className="text-muted-foreground block text-right text-[10px] font-normal">行</small>
            </span>
          </div>
        </div>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5" title="dg_relations 表行数">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon bg="var(--purple-soft)" tone="var(--purple)">
                <Share2 className="h-3.5 w-3.5" />
              </CardIcon>
              <span className="min-w-0">
                关系
                <span className="text-muted-foreground block text-[10.5px] leading-tight">两端实体都存在的关系才计入</span>
              </span>
            </span>
            <span className="flex-none font-mono text-2xl font-bold leading-none tabular-nums">
              {relAggQuery.isLoading ? "…" : relationTotal.toLocaleString()}
              <small className="text-muted-foreground block text-right text-[10px] font-normal">条</small>
            </span>
          </div>
        </div>
        <div className="border-border rounded-lg border bg-card px-3.5 py-2.5" onClick={() => go("reasoning")} style={{ cursor: "pointer" }} title="前往推理工作台">
          <div className="flex items-center justify-between gap-2.5">
            <span className="flex min-w-0 items-center gap-2.5 text-[12.5px]">
              <CardIcon bg="var(--cyan-soft)" tone="var(--cyan)">
                <BrainCircuit className="h-3.5 w-3.5" />
              </CardIcon>
              <span className="min-w-0">
                推理物化三元组
                <span className="text-muted-foreground block text-[10.5px] leading-tight">
                  {inferQuery.data ? `闭包 ${formatDuration(inferQuery.data.duration_ms)}` : "未运行 · 前往推理工作台运行"}
                </span>
              </span>
            </span>
            <span className="flex-none font-mono text-2xl font-bold leading-none tabular-nums">
              {inferQuery.isLoading ? "…" : inferQuery.data ? inferQuery.data.entailment_triples.toLocaleString() : "—"}
              <small className="text-muted-foreground block text-right text-[10px] font-normal">{inferQuery.data ? "条" : " "}</small>
            </span>
          </div>
        </div>
      </div>

      {/* 管线健康——轨道节点式（A 变体：一条轨道串五站，蓝线填充到首个非健康站） */}
      <Panel title="管线健康" subtitle="抽取 → 人工审核 → 知识图谱 → 推理 → 校验" tone={TONE_BLUE} icon={Network} className="mb-3.5">
        <div className="px-9 pt-6 pb-2">
          <div className="relative mx-2 h-7">
            <div className="border-border absolute left-0 right-0 top-[13px] h-0.5 bg-border" />
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="absolute top-[13px] h-0.5"
                style={{
                  left: `${[10, 30, 50, 70][i]}%`,
                  width: "20%",
                  background: `linear-gradient(90deg, ${PIPE_COLORS[i]}, ${PIPE_COLORS[i + 1]})`,
                }}
              />
            ))}
            {pipeNodes.map((nd, i) => (
              <button
                key={nd.nm}
                type="button"
                onClick={nd.onClick}
                title={`前往${nd.nm}页面`}
                className={cn(
                  "bg-card absolute top-0 z-10 h-7 w-7 -translate-x-1/2 place-items-center rounded-full border-2 font-mono text-[10px] font-bold grid transition-shadow hover:shadow-md",
                  nd.state === "idle" && "border-dashed",
                )}
                style={{
                  left: `${[10, 30, 50, 70, 90][i]}%`,
                  borderColor: nd.color,
                  color: nd.color,
                  ...(nd.state === "warn" ? { boxShadow: "0 0 0 4px rgba(245, 166, 35, 0.15)" } : {}),
                }}
              >
                <nd.icon className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>
          <div className="mx-2 mt-2 grid grid-cols-5">
            {pipeNodes.map((nd) => (
              <button
                key={nd.nm}
                type="button"
                onClick={nd.onClick}
                className="hover:bg-muted rounded py-1 text-center text-xs transition-colors"
                style={{ color: nd.color }}
              >
                <span className="block font-medium">{nd.nm}</span>
                <span className="mono block font-mono text-[19px] font-bold tabular-nums">
                  {nd.legendNum === null ? "—" : nd.legendNum.toLocaleString()}
                  <small className="ml-1 text-[10px] font-normal opacity-70">{nd.legendUnit}</small>
                </span>
                <span className="text-muted-foreground block text-[10.5px]">{nd.sub}</span>
              </button>
            ))}
          </div>
        </div>
      </Panel>

      {/* 域健康 + 治理链抽样 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel title="业务域概况" subtitle="各域模型与数据量" tone={TONE_BLUE} icon={Layers} className="flex max-h-[420px] flex-col overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border bg-muted/60 border-b">
                  {["域", "类", "谓词", "实体行", "状态"].map((h, i) => (
                    <th
                      key={h}
                      className={cn(
                        "text-muted-foreground px-4 py-2 text-xs font-medium",
                        i === 0 ? "text-left" : "text-center",
                      )}
                    >
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
                    className="border-border cursor-pointer border-b transition-colors last:border-b-0 hover:bg-muted"
                    title={`前往本体建模器查看「${domainAlias(row.domain) ?? row.domain}」域模型`}
                    onClick={() => go(`modeler:${row.domain}`)}
                  >
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 font-mono text-sm">
                        <span
                          className="h-2 w-2 flex-none rounded-full"
                          style={{ background: dot }}
                        />
                        {domainAlias(row.domain) ?? row.domain}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-center text-sm tabular-nums">{row.classes}</td>
                    <td className="px-4 py-2.5 text-center text-sm tabular-nums">{row.predicates}</td>
                    <td className="px-4 py-2.5 text-center text-sm tabular-nums">{row.count}</td>
                    <td className="px-4 py-2.5 text-center">
                      {row.disabledHere ? (
                        <span className="bg-destructive/10 text-destructive rounded-full px-2 py-0.5 text-xs">
                          链路禁用（{disabledLinks.length} 条）
                        </span>
                      ) : row.count > 0 ? (
                        <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs">活跃</span>
                      ) : (
                        <span className="text-muted-foreground text-xs">暂无实体</span>
                      )}
                    </td>
                  </tr>
                  );
                })}
                {domainRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-muted-foreground px-4 py-8 text-center text-sm">
                      {filesQuery.isLoading ? "加载 registry…" : "registry 为空"}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="border-border text-muted-foreground flex flex-none items-center gap-2 border-t px-4 py-2.5 text-xs">
            <GitBranch className="h-3 w-3" />
            <span title="cross_module">
              跨域链路 {disabledLinks.length} 条禁用——单域闭环优先，跨域待业务触发。
            </span>
          </div>
        </Panel>

        <Panel
          title="治理合规链 · 规则派生"
          subtitle="CONSTRUCT 真实派生计数（与推理工作台同源）"
          tone={TONE_PURPLE}
          icon={Network}
          actions={
            <button
              type="button"
              onClick={() => go("reasoning")}
              className="text-primary flex items-center gap-1 text-xs font-medium"
            >
              推理工作台 <ArrowRight className="h-3 w-3" />
            </button>
          }
        >
          {derivedRules === null ? (
            <div className="text-muted-foreground flex flex-col gap-2 p-4 text-xs">
              <p className="leading-relaxed">
                推理尚未运行——运行后此处展示各治理合规链规则的真实派生计数。
              </p>
              <button
                type="button"
                onClick={() => go("reasoning")}
                className="border-border bg-card hover:bg-muted flex items-center gap-1 self-start rounded-lg border px-2.5 py-1.5 text-[13px] font-medium"
              >
                前往推理工作台 <ArrowRight className="h-3 w-3" />
              </button>
            </div>
          ) : derivedRules.length === 0 ? (
            <p className="text-muted-foreground p-4 text-xs">推理已运行，当前规则集暂无派生记录。</p>
          ) : (
            <ol className="flex flex-col gap-3 p-4 text-[13px]">
              {derivedRules.map((rule, i) => {
                const tone = CHAIN_TONES[i % CHAIN_TONES.length] ?? TONE_BLUE;
                return (
                  <li
                    key={rule.name}
                    className="border-l-2 pl-3"
                    style={{ borderColor: withAlpha(tone, 0.45) }}
                  >
                    <div className="flex items-center gap-2">
                      <b className="text-[13px]">{rule.desc}</b>
                      <span
                        className="ml-auto flex-none rounded px-1.5 py-0.5 font-mono text-xs tabular-nums"
                        style={{ background: withAlpha(tone, 0.1), color: toneText(tone) }}
                        title={`派生三元组数（named graph: ${rule.graph}）`}
                      >
                        {rule.count} 条
                      </span>
                    </div>
                    <div className="text-muted-foreground mt-0.5 font-mono text-xs" title={`规则 ${rule.name} · 谓词 ${rule.pred}`}>
                      {rule.name}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          <p className="text-muted-foreground border-border border-t px-4 py-2.5 text-xs">
            逐条派生明细与图面判据见导出互操作页。
          </p>
        </Panel>
      </div>

      {/* 三小卡——绿=校验 蓝=数据面 琥珀=抽取 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-3">
        <Panel title="校验状态" tone={TONE_GREEN} icon={ShieldCheck} className="flex flex-col">
          <div className="flex flex-1 flex-col gap-2.5 p-4 text-xs">
            <div className="flex items-center justify-between">
              <span>国标符合性</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  validateQuery.isError
                    ? "bg-destructive/10 text-destructive"
                    : conformance.length > 0 && passedCount === conformance.length
                      ? "bg-success/10 text-success"
                      : "bg-warning/15 text-warning",
                )}
              >
                {validateQuery.isError
                  ? "获取失败"
                  : validateQuery.data
                    ? `${passedCount} / ${conformance.length} 通过`
                    : "加载中…"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span>SHACL 违规</span>
              <span className="tabular-nums">
                <b>{violationCount.length}</b> 项
              </span>
            </div>
            <button
              type="button"
              onClick={() => go("validation")}
              className="border-border bg-card hover:bg-muted mt-auto flex items-center gap-1 self-start rounded-lg border px-2.5 py-1.5 text-[13px] font-medium"
            >
              进入校验中心 <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        </Panel>

        <Panel title="图数据同步" subtitle="本体库与图保持一致" tone={TONE_BLUE} icon={Database} className="flex flex-col">
          <div className="flex flex-1 flex-col gap-2.5 p-4 text-xs">
            <div className="flex items-center justify-between">
              <span>registry 版本</span>
              <span className="font-mono">v{registryMetaQuery.data?.registry_version ?? "—"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>对象 / 链接类型</span>
              <span className="font-mono tabular-nums">
                {registryMetaQuery.data
                  ? `${registryMetaQuery.data.object_type_count} / ${registryMetaQuery.data.link_type_count}`
                  : "—"}
              </span>
            </div>
            <div className="mt-auto flex items-center gap-2">
              <button
                type="button"
                disabled={loadMutation.isPending}
                onClick={() => {
                  // G4：全量装载=重写 dg_* 全表的重操作（数十秒级），二次确认 + 失败可见
                  if (window.confirm("全量装载将重写图数据全表（耗时数十秒），确认执行？")) {
                    loadMutation.mutate();
                  }
                }}
                className="border-border bg-card hover:bg-muted flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[13px] font-medium disabled:opacity-50"
              >
                {loadMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <PlayCircle className="h-3 w-3" />
                )}
                全量装载（对账）
              </button>
              {loadMutation.isError ? (
                <span
                  className="text-destructive max-w-[16rem] truncate text-xs"
                  title={loadMutation.error instanceof Error ? loadMutation.error.message : String(loadMutation.error)}
                >
                  装载失败：{loadMutation.error instanceof Error ? loadMutation.error.message : String(loadMutation.error)}
                </span>
              ) : loadResult ? (
                <span className="text-muted-foreground font-mono text-xs">
                  {loadResult.entities} 实体 / {loadResult.relations} 关系已装载
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => go("export")}
                  className="text-primary flex items-center gap-1 text-xs font-medium"
                >
                  装载 / 导出 <ArrowRight className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        </Panel>

        <Panel
          title="抽取活动"
          subtitle="任务队列 · 实时"
          tone={TONE_BLUE}
          icon={FileInput}
        >
          <div className="flex flex-1 flex-col gap-2.5 p-4 text-xs">
            {activityQuery.isLoading ? (
              <p className="text-muted-foreground flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" /> 加载任务统计…
              </p>
            ) : (
              <>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    进行中 <b className="text-foreground tabular-nums">{activityActive}</b>
                  </span>
                  <span>
                    已完成 <b className="text-foreground tabular-nums">{activityDone}</b>
                  </span>
                  <span>
                    失败 <b className={activityFailed > 0 ? "text-destructive tabular-nums" : "text-foreground tabular-nums"}>{activityFailed}</b>
                  </span>
                  <span className="text-muted-foreground">
                    置信度 高 {activityQuery.data?.confidence?.high ?? 0} / 中 {activityQuery.data?.confidence?.mid ?? 0} / 低 {activityQuery.data?.confidence?.low ?? 0}
                  </span>
                </div>
                <p className="text-muted-foreground leading-relaxed">
                  任务=把样例库已提取产物批量写入图谱；开启强制人审的任务会全部进入消解审核。
                </p>
              </>
            )}
            <button
              type="button"
              onClick={() => go("ingest")}
              className="border-border bg-card hover:bg-muted mt-auto flex items-center gap-1 self-start rounded-lg border px-2.5 py-1.5 text-[13px] font-medium"
            >
              进入抽取导入 <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        </Panel>
      </div>
      </div>
    </div>
  );
}
