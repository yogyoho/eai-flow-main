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
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BrainCircuit,
  Database,
  FileInput,
  GitBranch,
  Layers,
  LayoutDashboard,
  Loader2,
  Network,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";

import {
  fetchAggregate,
  fetchObjectTypes,
  fetchPendingReviewCount,
  fetchRegistryMeta,
} from "@/api/ontology-graph-api";
import {
  fetchFormalValidate,
  runFormalInfer,
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
    queryFn: () => runFormalInfer(),
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
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) => setLoadResult(data),
  });

  // ── 待办主轴 + 管线健康（V4 信息架构增量，CEO 复审追加）──
  const todoFailed = activityFailed;
  const todoActive = activityActive;
  const attentionItems =
    (pending !== null && pending > 0 ? 1 : 0) + (todoFailed > 0 ? 1 : 0);
  // 管线各站状态：抽取=有进行中则琥珀；审核=有待审则琥珀；图=恒绿（对账见同步卡）；
  // 推理=未运行灰/已运行绿；校验=全过绿否则琥珀
  const stageExtract: "ok" | "warn" = todoActive > 0 ? "warn" : "ok";
  const stageReview: "ok" | "warn" = pending !== null && pending > 0 ? "warn" : "ok";
  const stageInfer: "ok" | "idle" = inferQuery.data ? "ok" : "idle";
  const stageValidate: "ok" | "warn" =
    validateQuery.data && conformance.length > 0 && passedCount === conformance.length && violationCount.length === 0
      ? "ok"
      : "warn";

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
          className="rounded-xl border p-3.5 text-left shadow-sm transition-all duration-200 hover:-translate-y-px cursor-pointer"
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
          <div className="text-muted-foreground mt-0.5 text-xs">五间房批次已入图待人工确认 · 支持批量勾选</div>
          <span className="bg-primary text-primary-foreground mt-2.5 inline-flex items-center gap-1 rounded-md px-3 py-1 text-xs font-medium">
            进入消解审核 →
          </span>
        </button>
        <div className="border-border rounded-xl border bg-card p-3.5">
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
            <span className={cn("inline-block h-2 w-2 rounded-full", todoFailed > 0 ? "bg-destructive" : "bg-success")} />
            失败任务
          </div>
          <div className={cn("mt-1.5 font-mono text-3xl font-bold tabular-nums", todoFailed > 0 ? "text-destructive" : "text-success")}>
            {todoFailed}
          </div>
          <div className="text-muted-foreground mt-0.5 text-xs">抽取队列 · 近 24h</div>
        </div>
        <div className="border-border rounded-xl border bg-card p-3.5">
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
            <span className={cn("inline-block h-2 w-2 rounded-full", todoActive > 0 ? "bg-warning" : "bg-success")} />
            进行中
          </div>
          <div className="mt-1.5 font-mono text-3xl font-bold tabular-nums">{todoActive}</div>
          <div className="text-muted-foreground mt-0.5 text-xs">队列 · 今日已完成 {activityDone}</div>
        </div>
        <div className="border-border rounded-xl border bg-card p-3.5">
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
            <span className={cn("inline-block h-2 w-2 rounded-full", attentionItems > 0 ? "bg-warning" : "bg-success")} />
            系统状态
          </div>
          <div className={cn("mt-1.5 font-bold", attentionItems > 0 ? "text-[22px] leading-relaxed" : "font-mono text-3xl", attentionItems > 0 ? "" : "text-success")}>
            {pending === null ? "…" : attentionItems > 0 ? `${attentionItems} 项需关注` : "全部正常"}
          </div>
          <div className="text-muted-foreground mt-0.5 text-xs">
            {pending === null ? "加载中" : attentionItems > 0 ? "待审积压 · 其余指标正常" : "管线各站健康"}
          </div>
        </div>
      </div>

      {/* 管线健康——五站站线（V4 信息架构） */}
      <Panel title="管线健康" subtitle="抽取 → 人工审核 → 知识图谱 → 推理 → 校验" icon={Network} className="mb-3.5">
        <div className="grid grid-cols-2 gap-3 px-4 pb-4 md:grid-cols-5">
          {[
            {
              nm: "抽取",
              dot: stageExtract,
              num: activityDone,
              unit: "已完成",
              sub: todoActive > 0 ? `进行中 ${todoActive} · 高置信 ${activityQuery.data?.confidence?.high ?? 0}` : `队列空闲 · 高置信 ${activityQuery.data?.confidence?.high ?? 0}`,
              onClick: () => go("ingest"),
            },
            {
              nm: "人工审核",
              dot: stageReview,
              num: pending ?? 0,
              unit: "待确认",
              sub: pending !== null && pending > 0 ? "积压 · 建议尽快清零" : "无积压",
              onClick: () => go("resolve"),
            },
            {
              nm: "知识图谱",
              dot: "ok" as const,
              num: entityTotal,
              unit: "实体行",
              sub: `关系 ${relationTotal} 条 · 对账见同步卡`,
              onClick: () => go("entities"),
            },
            {
              nm: "推理",
              dot: stageInfer,
              num: inferQuery.data ? inferQuery.data.entailment_triples : null,
              unit: inferQuery.data ? "物化" : "未运行",
              sub: inferQuery.data ? `闭包 ${formatDuration(inferQuery.data.duration_ms)}` : "全量重算约 30 秒 · 前往工作台",
              onClick: () => go("reasoning"),
            },
            {
              nm: "校验",
              dot: stageValidate,
              num: validateQuery.data ? passedCount : null,
              unit: validateQuery.data ? `/ ${conformance.length} 通过` : "—",
              sub: `SHACL 违规 ${violationCount.length}`,
              onClick: () => go("validation"),
            },
          ].map((st) => (
            <button
              key={st.nm}
              type="button"
              onClick={st.onClick}
              title={`前往${st.nm}页面`}
              className={cn(
                "border-border hover:bg-muted rounded-lg border p-3 text-left transition-colors",
                st.dot === "warn" && "border-warning/40",
              )}
              style={st.dot === "warn" ? { background: withAlpha(TONE_AMBER, 0.05) } : undefined}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-block h-2 w-2 flex-none rounded-full",
                    st.dot === "warn" && "bg-warning",
                    st.dot === "ok" && "bg-success",
                    st.dot === "idle" && "bg-muted-foreground/50",
                  )}
                />
                <span className="text-[13px] font-medium">{st.nm}</span>
              </div>
              <div className="mt-1 font-mono text-[22px] font-bold tabular-nums">
                {st.num === null ? "—" : st.num.toLocaleString()}
                <small className="text-muted-foreground ml-1 text-[11px] font-normal">{st.unit}</small>
              </div>
              <div className="text-muted-foreground mt-0.5 truncate text-[11px]">{st.sub}</div>
            </button>
          ))}
        </div>
      </Panel>

      {/* 瓦片行——三色标识：实体蓝 / 关系紫 / 推理青（待审已上移至首行待办主轴） */}
      <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-3">
        <Tile
          k="实体"
          v={entAggQuery.isLoading ? null : entityTotal}
          unit="行"
          d={topDomain ? `最大域 ${topDomain.group ?? "—"} · ${topDomain.value} 行` : "—"}
          tone={TONE_BLUE}
          icon={Database}
          title="dg_entities 表行数（跨域合计）"
          onClick={() => go("entities")}
        />
        <Tile
          k="关系"
          v={relAggQuery.isLoading ? null : relationTotal}
          unit="条"
          d="两端实体都存在的关系才计入"
          tone={TONE_PURPLE}
          icon={GitBranch}
          title="dg_relations 表行数"
        />
        <Tile
          k="推理物化三元组"
          v={inferQuery.data ? inferQuery.data.entailment_triples : null}
          unit=""
          d={
            inferQuery.data
              ? `闭包 ${formatDuration(inferQuery.data.duration_ms)} · 前往推理工作台查看规则明细`
              : "尚未运行 · 全量重算约 30 秒，前往推理工作台"
          }
          tone={TONE_CYAN}
          icon={BrainCircuit}
          onClick={() => go("reasoning")}
        />
      </div>

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
                    title="前往本体建模器查看该域模型"
                    onClick={() => go("modeler")}
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
              跨域链路 {disabledLinks.length} 条禁用——单域闭环优先，跨域待业务触发（已列入待办）
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
                推理尚未运行——全量重算（约 30 秒）后此处展示各治理合规链规则的真实派生计数。
              </p>
              <button
                type="button"
                onClick={() => go("reasoning")}
                className="border-border bg-card hover:bg-muted flex items-center gap-1 self-start rounded-lg border px-2.5 py-1.5 text-[13px] font-medium"
              >
                前往推理工作台 <ArrowRight className="h-3 w-3" />
              </button>
            </div>
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
            逐条物化下钻已列入待办——当前图面判据见导出互操作页。
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
                  任务=消费 kf_samples 已提取产物入图，force_review 全量进人审（消解审核）。
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

/** 统计瓦片（多色版）：tone 决定图标 chip/色底/边框色相，数字保持 ink 深色保证对比度。
 *  k 指标名 / v 大数字（null→"—"）/ d 注脚；onClick 整卡可点；onAction 右上小动作。 */
function Tile({
  k,
  v,
  unit,
  d,
  tone,
  icon: Icon,
  accent,
  title,
  onClick,
  onAction,
  actionLabel,
}: {
  k: string;
  v: number | null;
  unit: string;
  d: string;
  tone: string;
  icon: LucideIcon;
  accent?: boolean;
  title?: string;
  onClick?: () => void;
  onAction?: () => void;
  actionLabel?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      title={title}
      className={cn(
        "rounded-xl border p-3.5 text-left shadow-sm transition-all duration-200",
        onClick && "hover:-translate-y-px cursor-pointer",
        !onClick && "cursor-default",
      )}
      style={{
        background: withAlpha(tone, 0.05),
        borderColor: withAlpha(tone, 0.28),
      }}
    >
      <div className="flex items-center gap-2.5">
        <span
          className="grid h-9 w-9 flex-none place-items-center rounded-lg"
          style={{ background: withAlpha(tone, 0.14) }}
        >
          <Icon className="h-[18px] w-[18px]" style={{ color: tone }} />
        </span>
        <span className="text-muted-foreground text-sm font-medium">{k}</span>
      </div>
      <div
        className="mt-2 text-2xl font-semibold tracking-tight tabular-nums"
        style={{ color: accent && v !== null && v > 0 ? toneText(tone) : undefined }}
      >
        {v === null ? "—" : v.toLocaleString()}
        {unit ? <small className="text-muted-foreground ml-1.5 text-sm font-normal">{unit}</small> : null}
      </div>
      <div className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
        <span
          className="h-1.5 w-1.5 flex-none rounded-full"
          style={{ background: withAlpha(tone, 0.55) }}
        />
        <span className="truncate">{d}</span>
        {onAction ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onAction();
            }}
            onKeyDown={(e) => e.key === "Enter" && onAction()}
            className="ml-auto flex-none font-medium underline-offset-2 hover:underline"
            style={{ color: toneText(tone) }}
          >
            {actionLabel}
          </span>
        ) : null}
      </div>
    </button>
  );
}
