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
 *   （registry 版本 + 全量装载按钮）；抽取活动（任务队列规划态）
 * - 治理链抽样：规划态示例（逐条物化溯源已入 TODOS「推理白盒化」）
 */
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BrainCircuit,
  Database,
  FileInput,
  GitBranch,
  GitMerge,
  Layers,
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
  PENDING_REVIEW_LIMIT,
} from "@/api/ontology-graph-api";
import {
  fetchFormalValidate,
  runFormalInfer,
  runFormalLoad,
  type FormalLoadResult,
} from "@/api/formal-api";
import { fetchRegistryContent, fetchRegistryFiles } from "@/api/registry-api";
import { PageHeader, Panel } from "@/pages/shared";
import { withAlpha } from "@/explorer/graphTheme";
import { cn } from "@/lib/utils";

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

  return (
    /* 横向滚动（样式=全站 6px 细条，同合同价格分析页）：min-w 保四瓦片/双列布局
       不被窄视口压扁裁切，超出部分横向滚动查看 */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1100px] p-6">
      <PageHeader
        clause="01"
        icon={Database}
        title="工作台总览"
        description="知识层运营一览：数据沉淀、待审压力、校验与数据面状态。全部数字来自真端点（dg_* 聚合 / registry / formal）。"
        actions={
          entAggQuery.isFetching || relAggQuery.isFetching ? (
            <Loader2 className="text-primary h-4 w-4 animate-spin" />
          ) : null
        }
      />

      {/* 瓦片行——四色标识：实体蓝 / 关系紫 / 推理青 / 待审琥珀 */}
      <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        <Tile
          k="实体（dg_entities）"
          v={entAggQuery.isLoading ? null : entityTotal}
          unit="行"
          d={topDomain ? `最大域 ${topDomain.group ?? "—"} · ${topDomain.value} 行` : "—"}
          tone={TONE_BLUE}
          icon={Database}
          onClick={() => go("entities")}
        />
        <Tile
          k="关系（dg_relations）"
          v={relAggQuery.isLoading ? null : relationTotal}
          unit="条"
          d="双端点齐备才入图"
          tone={TONE_PURPLE}
          icon={GitBranch}
        />
        <Tile
          k="推理物化三元组"
          v={inferQuery.data ? inferQuery.data.entailment_triples : null}
          unit=""
          d={
            inferQuery.data
              ? `闭包 ${inferQuery.data.duration_ms}ms`
              : "尚未运行 · 点击运行全量推理"
          }
          tone={TONE_CYAN}
          icon={BrainCircuit}
          onAction={inferQuery.isFetching ? undefined : () => inferQuery.refetch()}
          actionLabel={inferQuery.isFetching ? undefined : "运行推理"}
        />
        <Tile
          k="待审实体"
          v={pending ?? null}
          unit=""
          d={pending !== null && pending >= PENDING_REVIEW_LIMIT ? `已达拉取上限 ${PENDING_REVIEW_LIMIT}` : "点击进入消解审核 →"}
          tone={TONE_AMBER}
          icon={GitMerge}
          accent
          onClick={() => go("resolve")}
        />
      </div>

      {/* 域健康 + 治理链抽样 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel title="域健康" subtitle="registry × dg_* 聚合" tone={TONE_BLUE} icon={Layers} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border bg-muted/60 border-b">
                  {["域", "类", "谓词", "实体行", "状态"].map((h) => (
                    <th key={h} className="text-muted-foreground px-4 py-2 text-left text-[11.5px] font-medium">
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
                    onClick={() => go("modeler")}
                  >
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 font-mono text-xs">
                        <span
                          className="h-2 w-2 flex-none rounded-full"
                          style={{ background: dot }}
                        />
                        {row.domain}
                      </span>
                    </td>
                    <td className="num px-4 py-2.5 text-right tabular-nums">{row.classes}</td>
                    <td className="num px-4 py-2.5 text-right tabular-nums">{row.predicates}</td>
                    <td className="num px-4 py-2.5 text-right tabular-nums">{row.count}</td>
                    <td className="px-4 py-2.5">
                      {row.disabledHere ? (
                        <span className="bg-destructive/10 text-destructive rounded-full px-2 py-0.5 text-[11px]">
                          链路禁用（{disabledLinks.length} 条）
                        </span>
                      ) : row.count > 0 ? (
                        <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[11px]">活跃</span>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">暂无实体</span>
                      )}
                    </td>
                  </tr>
                  );
                })}
                {domainRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-muted-foreground px-4 py-8 text-center text-xs">
                      {filesQuery.isLoading ? "加载 registry…" : "registry 为空"}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="border-border text-muted-foreground flex items-center gap-2 border-t px-4 py-2.5 text-[11px]">
            <GitBranch className="h-3 w-3" />
            跨域链路（cross_module）四条全禁用——单域闭环优先，跨域待业务触发（TODOS）
          </div>
        </Panel>

        <Panel
          title="治理链抽样"
          subtitle="covered_by_standard 推导"
          tone={TONE_PURPLE}
          icon={Network}
          actions={
            <span className="text-muted-foreground/70 border-border/70 rounded border border-dashed px-1.5 py-px font-mono text-[10px]">
              规划 · 示例数据
            </span>
          }
        >
          <ol className="flex flex-col gap-3 p-4 text-[13px]">
            {CHAIN_SAMPLES.map((chain, i) => {
              const tone = CHAIN_TONES[i % CHAIN_TONES.length] ?? TONE_BLUE;
              return (
              <li
                key={chain.ttl}
                className="border-l-2 pl-3"
                style={{ borderColor: withAlpha(tone, 0.45) }}
              >
                <b className="text-[12.5px]">{chain.title}</b>
                <span
                  className="ml-2 rounded px-1.5 py-0.5 font-mono text-[10px]"
                  style={{ background: withAlpha(tone, 0.1), color: toneText(tone) }}
                >
                  {chain.rule}
                </span>
                <div className="text-muted-foreground mt-0.5 font-mono text-[11px]">{chain.ttl}</div>
              </li>
              );
            })}
          </ol>
          <p className="text-muted-foreground border-border border-t px-4 py-2.5 text-[11px]">
            逐条物化可下钻（named graph 归属即触发轨迹）已入 TODOS「推理白盒化」——当前图面判据见导出互操作页。
          </p>
        </Panel>
      </div>

      {/* 三小卡——绿=校验 蓝=数据面 琥珀=抽取 */}
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-3">
        <Panel title="校验状态" tone={TONE_GREEN} icon={ShieldCheck}>
          <div className="space-y-2.5 p-4 text-xs">
            <div className="flex items-center justify-between">
              <span>国标符合性（5.3/5.4/附录A/§9）</span>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[11px] font-medium",
                  conformance.length > 0 && passedCount === conformance.length
                    ? "bg-success/10 text-success"
                    : "bg-warning/15 text-warning",
                )}
              >
                {validateQuery.data ? `${passedCount} / ${conformance.length} 通过` : "加载中…"}
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
              className="border-border bg-card hover:bg-muted mt-1 flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium"
            >
              进入校验中心 <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        </Panel>

        <Panel title="数据面" subtitle="registry 与图对账" tone={TONE_BLUE} icon={Database}>
          <div className="space-y-2.5 p-4 text-xs">
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
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={loadMutation.isPending}
                onClick={() => loadMutation.mutate()}
                className="border-border bg-card hover:bg-muted flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium disabled:opacity-50"
              >
                {loadMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <PlayCircle className="h-3 w-3" />
                )}
                全量装载（对账）
              </button>
              {loadResult ? (
                <span className="text-muted-foreground font-mono text-[11px]">
                  {loadResult.entities} 实体 / {loadResult.relations} 关系已装载
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => go("export")}
                  className="text-primary flex items-center gap-1 text-[11.5px] font-medium"
                >
                  装载 / 导出 <ArrowRight className="h-3 w-3" />
                </button>
              )}
            </div>
          </div>
        </Panel>

        <Panel
          title="抽取活动"
          subtitle="任务队列 · 规划中"
          tone={TONE_AMBER}
          icon={FileInput}
          actions={
            <span className="text-muted-foreground/70 border-border/70 rounded border border-dashed px-1.5 py-px font-mono text-[10px]">
              规划
            </span>
          }
        >
          <div className="space-y-2.5 p-4 text-xs">
            <p className="text-muted-foreground leading-relaxed">
              抽取任务概念（队列/进度/置信度分布）待后端任务 API——当前生产线
              <span className="text-foreground font-mono"> regex/v1</span>，
              抽取结果直接落 <span className="font-mono">dg_*</span>，待审进消解审核。
            </p>
            <button
              type="button"
              onClick={() => go("ingest")}
              className="border-border bg-card hover:bg-muted flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium"
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
  onClick?: () => void;
  onAction?: () => void;
  actionLabel?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
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
        <span className="text-muted-foreground text-xs font-medium">{k}</span>
      </div>
      <div
        className="mt-2 text-2xl font-semibold tracking-tight tabular-nums"
        style={{ color: accent && v !== null && v > 0 ? toneText(tone) : undefined }}
      >
        {v === null ? "—" : v.toLocaleString()}
        {unit ? <small className="text-muted-foreground ml-1.5 text-xs font-normal">{unit}</small> : null}
      </div>
      <div className="text-muted-foreground mt-1 flex items-center gap-1 text-[11px]">
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

/** 治理链示例（示例数据——真实逐条溯源待推理白盒化）。 */
const CHAIN_SAMPLES = [
  {
    title: "矿井水处理站 → GB 50383-2010",
    rule: "prp-spo2×2",
    ttl: "monitored_by(矿井水处理站, 悬浮物浓度) ∧ has_limit(悬浮物浓度, …) ⇒ covered_by_standard",
  },
  {
    title: "锅炉烟气排放 → GB 13223-2011",
    rule: "prp-spo2×2",
    ttl: "双碱法脱硫 + 45m 烟囱 · 阈值约束来自条款抽取",
  },
  {
    title: "矸石山 → GB 50383-2010 第 6 章",
    rule: "sameas",
    ttl: "实体消解后由 sameas 传播继承治理关系",
  },
];
