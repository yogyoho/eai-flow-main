"use client";

import {
  Activity,
  BarChart3,
  Building2,
  CalendarX,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Crosshair,
  LayoutGrid,
  Table2,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { BoxPlot } from "@/extensions/contract-price/components/BoxPlot";
import { TracebackDrawer } from "@/extensions/contract-price/components/TracebackDrawer";
import { useClusters, useGoodsAnalysis } from "@/extensions/contract-price/hooks";
import {
  baselineShiftDocIds,
  buildBaselineTooltips,
  rowOutlierTier,
  type OutlierStatRow,
} from "@/extensions/contract-price/outlier-semantics";

// ── chart card matching prototype style ──

type BadgeColor = "blue" | "cyan" | "violet" | "amber" | "emerald";

const badgeColors: Record<BadgeColor, string> = {
  blue: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  cyan: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  violet: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  emerald: "bg-success/10 text-success",
};

function ChartCard({
  title,
  meta,
  icon,
  badgeColor = "blue",
  children,
}: {
  title: string;
  meta?: string;
  icon?: React.ReactNode;
  badgeColor?: BadgeColor;
  children: React.ReactNode;
}) {
  return (
    <div className="border-border bg-card rounded-lg border p-4 transition-all hover:border-primary/20 hover:shadow-md">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-muted-foreground flex items-center gap-2 text-sm font-semibold">
          {icon}
          {title}
        </h3>
        {meta ? (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${badgeColors[badgeColor]}`}
          >
            {meta}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

// ── tooltip style for recharts ──

const tooltipStyle = {
  backgroundColor: "var(--background)",
  border: "1px solid var(--border)",
  borderRadius: "8px",
  fontSize: "12px",
} as const;

const COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#06b6d4",
  "#f59e0b",
  "#10b981",
  "#f43f5e",
];

// ── main component ──

const PAGE_SIZE = 10;

export function GoodsAnalysis() {
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  // 懒加载: 仅在下拉展开时拉取全量分组(60s 缓存, 收合再开不重复请求)
  const {
    data: clustersData,
    isLoading: clustersLoading,
  } = useClusters({ limit: 1000 }, { enabled: open, staleTime: 60_000 });
  const clusters = clustersData?.items ?? [];

  const params = selectedCluster
    ? { cluster_id: selectedCluster, skip: page * PAGE_SIZE, limit: PAGE_SIZE }
    : {};
  const { data, isLoading } = useGoodsAnalysis(params);

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4">
      {/* Cluster select */}
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground shrink-0 text-sm font-medium">
          选择货物：
        </span>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={open}
              className="h-[42px] min-w-[260px] justify-between rounded-lg font-normal"
            >
              {selectedCluster
                ? (clusters.find((c) => c.id === selectedCluster)
                    ?.representative_name ?? "选择货物分组...")
                : "选择货物分组..."}
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[400px] p-0" align="start">
            <Command>
              <CommandInput placeholder="输入名称模糊检索..." />
              <CommandList>
                <CommandEmpty>未找到匹配的货物</CommandEmpty>
                <CommandGroup>
                  {clustersLoading ? (
                    <div className="text-muted-foreground p-3 text-sm">
                      加载分组中...
                    </div>
                  ) : null}
                  {clusters.map((c) => (
                    <CommandItem
                      key={c.id}
                      value={c.representative_name}
                      onSelect={() => {
                        setSelectedCluster(c.id);
                        setPage(0);
                        setOpen(false);
                      }}
                      className="items-start py-2"
                    >
                      <Check
                        className={`h-4 w-4 shrink-0 ${selectedCluster === c.id ? "opacity-100" : "opacity-0"}`}
                      />
                      <div className="flex min-w-0 flex-1 flex-col">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate">
                            {c.representative_name}
                          </span>
                          <span className="text-muted-foreground font-mono text-xs">
                            {c.item_count}条
                          </span>
                        </div>
                        {(c.spec_summary ?? c.category_summary) && (
                          <span className="text-muted-foreground truncate text-xs">
                            {[c.spec_summary, c.category_summary]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        )}
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="text-muted-foreground flex flex-1 items-center justify-center py-20 text-sm">
          分析中...
        </div>
      ) : !data || data.total === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center py-20 text-center">
          <img
            src="/contract-price/data-tip.svg"
            alt=""
            className="mb-3 max-h-32 w-auto"
          />
          <p className="text-muted-foreground text-sm">
            {selectedCluster
              ? "未找到匹配的货物数据"
              : "选择货物聚类分组，查看货物价格的分析图表和明细"}
          </p>
        </div>
      ) : (
        <AnalysisResult
          data={data}
          page={page}
          setPage={setPage}
          pageSize={PAGE_SIZE}
        />
      )}
    </div>
  );
}

// ── result renderer ──

function AnalysisResult({
  data,
  page,
  setPage,
  pageSize,
}: {
  data: Record<string, unknown>;
  page: number;
  setPage: (fn: (p: number) => number) => void;
  pageSize: number;
}) {
  const [trace, setTrace] = useState<Record<string, unknown> | null>(null);
  const boxplot = data.boxplot as {
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
    mean: number;
    iqr?: number;
    outliers: { unit_price: number }[];
  } | null;
  const bySupplier = (data.by_supplier ?? []) as {
    name: string;
    count: number;
    avg_price: number;
  }[];
  const byDate = (data.by_date ?? []) as {
    month: string;
    count: number;
    avg_price: number;
  }[];
  const priceRanges = (data.price_ranges ?? []) as {
    range: string;
    count: number;
  }[];
  const items = (data.items ?? []) as Record<string, unknown>[];
  const goodsName = data.goods_name as string;
  const total = data.total as number;
  const okCount = data.ok_count as number;
  const nrCount = data.needs_review_count as number;

  // EAI-CUSTOM F3a 离群语义分层: 明细行 → 判定行,成片文档判定 + 降级说明 tooltip。
  const statRows: OutlierStatRow[] = useMemo(
    () =>
      items.map((it) => ({
        id: it.id as string,
        documentId: it.document_id as string,
        isOutlier: it.is_outlier as boolean,
        unitPrice: (it.unit_price as number | null) ?? null,
        clusterMedian: (it.cluster_median as number | null) ?? null,
        deviationPct: (it.deviation_pct as number | null) ?? null,
        clusterId: (it.cluster_id as string | null) ?? null,
        contractNo: (it.contract_no as string | null) ?? null,
        clusterDocCount: (it.cluster_doc_count as number | null) ?? null,
      })),
    [items],
  );
  const baselineDocs = useMemo(() => baselineShiftDocIds(statRows), [statRows]);
  const baselineTooltips = useMemo(() => buildBaselineTooltips(statRows), [statRows]);

  return (
    <div className="space-y-4">
      {/* Title bar */}
      <div className="border-border bg-card flex items-center gap-3 rounded-lg border px-4 py-3 shadow-sm">
        <h2 className="text-lg font-bold tracking-tight">{goodsName}</h2>
        <span className="bg-success/10 text-success rounded-full px-2.5 py-0.5 text-xs font-semibold">
          已校验 {okCount} / {total}
        </span>
        {nrCount > 0 ? (
          <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            待核验 {nrCount}
          </span>
        ) : null}
        {boxplot ? (
          <div className="text-muted-foreground ml-auto flex items-center gap-4 text-sm">
            <span>
              均值{" "}
              <span className="text-primary font-bold">{`¥${boxplot.mean.toFixed(2)}`}</span>
            </span>
            <span className="text-muted-foreground text-xs font-bold">
              区间 [¥{boxplot.min.toFixed(0)} — ¥{boxplot.max.toFixed(0)}]
            </span>
          </div>
        ) : null}
      </div>

      {/* Charts 2x2 grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Box plot */}
        <ChartCard
          title="价格分布(箱线图)"
          meta={boxplot ? `IQR = ${boxplot.iqr?.toFixed(0)}` : ""}
          badgeColor="blue"
          icon={
            <LayoutGrid className="text-muted-foreground/50 h-[15px] w-[15px]" />
          }
        >
          <div className="h-[220px]">
            <BoxPlot data={boxplot} />
          </div>
        </ChartCard>

        {/* Trend curve */}
        <ChartCard
          title="价格趋势"
          meta={byDate.length > 0 ? `${byDate.length} 个月` : "无日期数据"}
          badgeColor="cyan"
          icon={
            <Activity className="text-muted-foreground/50 h-[15px] w-[15px]" />
          }
        >
          <div className="h-[220px]">
            {byDate.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={byDate}
                  margin={{ left: 0, right: 20, top: 5 }}
                >
                  <defs>
                    <linearGradient id="trend-line" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="2 4"
                    stroke="rgba(100,116,139,0.22)"
                  />
                  <XAxis
                    dataKey="month"
                    tick={{
                      fontSize: 12,
                      fontFamily: "monospace",
                      fill: "rgba(71,85,105,0.85)",
                    }}
                    stroke="rgba(100,116,139,0.5)"
                  />
                  <YAxis
                    tick={{
                      fontSize: 12,
                      fontFamily: "monospace",
                      fill: "rgba(71,85,105,0.85)",
                    }}
                    stroke="rgba(100,116,139,0.5)"
                  />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="avg_price"
                    stroke="url(#trend-line)"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#3b82f6", strokeWidth: 0 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-2 text-sm">
                <CalendarX className="text-muted-foreground/30 h-8 w-8" />
                合同缺少签订日期,无法生成趋势
              </div>
            )}
          </div>
        </ChartCard>

        {/* Histogram */}
        <ChartCard
          title="价格区间分布"
          meta={`${total} 条`}
          badgeColor="violet"
          icon={
            <BarChart3 className="text-muted-foreground/50 h-[15px] w-[15px]" />
          }
        >
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={priceRanges}
                margin={{ left: 0, right: 20, top: 5 }}
              >
                <defs>
                  <linearGradient id="hist-bar" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.7} />
                    <stop
                      offset="100%"
                      stopColor="#3b82f6"
                      stopOpacity={0.15}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="2 4"
                  stroke="rgba(100,116,139,0.22)"
                />
                <XAxis
                  dataKey="range"
                  tick={{
                    fontSize: 12,
                    fontFamily: "monospace",
                    fill: "rgba(71,85,105,0.85)",
                  }}
                  stroke="rgba(100,116,139,0.5)"
                />
                <YAxis
                  tick={{
                    fontSize: 12,
                    fontFamily: "monospace",
                    fill: "rgba(71,85,105,0.85)",
                  }}
                  stroke="rgba(100,116,139,0.5)"
                  allowDecimals={false}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar
                  dataKey="count"
                  fill="url(#hist-bar)"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        {/* Supplier comparison */}
        <ChartCard
          title="供应商均价对比"
          meta={`${bySupplier.length} 家`}
          badgeColor="amber"
          icon={
            <Building2 className="text-muted-foreground/50 h-[15px] w-[15px]" />
          }
        >
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={bySupplier}
                layout="vertical"
                margin={{ left: 80, right: 20, top: 5 }}
              >
                <defs>
                  <linearGradient id="sup-bar" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.6} />
                    <stop
                      offset="100%"
                      stopColor="#3b82f6"
                      stopOpacity={0.25}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="2 4"
                  stroke="rgba(100,116,139,0.22)"
                />
                <XAxis
                  type="number"
                  tick={{
                    fontSize: 12,
                    fontFamily: "monospace",
                    fill: "rgba(71,85,105,0.85)",
                  }}
                  stroke="rgba(100,116,139,0.5)"
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "rgba(51,65,85,0.9)" }}
                  stroke="rgba(100,116,139,0.5)"
                  width={80}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar
                  dataKey="avg_price"
                  fill="url(#sup-bar)"
                  radius={[0, 4, 4, 0]}
                >
                  {bySupplier.map((_, i) => (
                    <Cell
                      key={i}
                      fill={COLORS[i % COLORS.length]}
                      fillOpacity={0.5}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      {/* Detail table */}
      <div className="border-border bg-card overflow-hidden rounded-lg border shadow-sm">
        <div className="border-border flex items-center justify-between border-b px-5 py-3">
          <h3 className="text-muted-foreground flex items-center gap-2 text-sm font-semibold">
            <Table2 className="text-muted-foreground/50 h-[15px] w-[15px]" />
            价格明细(跨合同)
          </h3>
          <span className="bg-success/10 text-success rounded-full px-2.5 py-0.5 text-xs font-bold">
            {total} 条
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-border text-muted-foreground/50 border-b text-xs tracking-wide uppercase">
                <th className="px-5 py-2.5 text-left font-semibold">
                  货物名称
                </th>
                <th className="px-5 py-2.5 text-left font-semibold">规格</th>
                <th className="px-5 py-2.5 text-left font-semibold">
                  合同编号
                </th>
                <th className="px-5 py-2.5 text-left font-semibold">供应商</th>
                <th className="px-5 py-2.5 text-right font-semibold">
                  含税单价
                </th>
                <th className="px-5 py-2.5 text-right font-semibold">数量</th>
                <th className="px-5 py-2.5 text-left font-semibold">单位</th>
                <th className="px-5 py-2.5 text-left font-semibold whitespace-nowrap">
                  状态
                </th>
                <th className="px-5 py-2.5 text-center font-semibold">溯源</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => {
                const price = it.unit_price as number | null;
                const isOutlier = it.is_outlier as boolean;
                // EAI-CUSTOM F3a: 成片文档的离群行降级为琥珀「跨合同基线差异」,
                // 真散点行保持红色异常(title 悬挂基线说明)。
                const tier = rowOutlierTier(
                  { documentId: it.document_id as string, isOutlier },
                  baselineDocs,
                );
                const tierTip =
                  tier === "baseline-shift"
                    ? baselineTooltips.get(it.id as string)
                    : undefined;
                return (
                  <tr
                    key={i}
                    className="border-border/40 hover:bg-primary/5 border-b transition-colors"
                  >
                    <td className="px-5 py-2.5 font-medium">
                      {it.goods_name as string}
                    </td>
                    <td className="text-muted-foreground px-5 py-2.5 text-xs">
                      {(it.spec_model as string) || "—"}
                    </td>
                    <td className="text-muted-foreground px-5 py-2.5 font-mono text-xs">
                      {(it.contract_no as string) || "—"}
                    </td>
                    <td className="px-5 py-2.5 font-medium">
                      {it.supplier as string}
                    </td>
                    <td
                      className={`px-5 py-2.5 text-right font-mono font-semibold ${tier === "outlier" ? "text-rose-600 dark:text-rose-400" : tier === "baseline-shift" ? "text-amber-600 dark:text-amber-400" : "text-primary"}`}
                      title={tierTip}
                    >
                      {price != null ? `¥${price.toFixed(2)}` : "—"}
                    </td>
                    <td className="text-muted-foreground px-5 py-2.5 text-right font-mono">
                      {(it.quantity as number)?.toFixed(2) ?? "—"}
                    </td>
                    <td className="px-5 py-2.5">
                      {(it.unit as string) || "—"}
                    </td>
                    <td className="px-5 py-2.5">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${it.validation_status === "ok" ? "bg-success/10 text-success" : "bg-amber-500/10 text-amber-600 dark:text-amber-400"}`}
                      >
                        {it.validation_status === "ok" ? "已校验" : "待核验"}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-center">
                      {it.source_page != null ? (
                        <button
                          type="button"
                          className="text-rose-600 transition-colors hover:text-rose-600 dark:text-rose-400"
                          title="溯源到原文"
                          onClick={() => setTrace(it)}
                        >
                          <Crosshair className="inline-block h-4 w-4" />
                        </button>
                      ) : (
                        <span className="text-muted-foreground/30">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        {total > pageSize ? (
          <div className="border-border flex items-center justify-between border-t px-5 py-2.5">
            <span className="text-muted-foreground text-xs">
              第 {page * pageSize + 1} —{" "}
              {Math.min((page + 1) * pageSize, total)} 条 / 共 {total} 条
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="default"
                size="sm"
                className="h-7 px-2"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                上一页
              </Button>
              <span className="text-muted-foreground text-xs font-medium">
                {page + 1} / {Math.ceil(total / pageSize)}
              </span>
              <Button
                variant="default"
                size="sm"
                className="h-7 px-2"
                disabled={(page + 1) * pageSize >= total}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      {/* Traceback drawer */}
      <TracebackDrawer
        docId={(trace?.document_id as string) ?? null}
        page={(trace?.source_page as number) ?? null}
        bbox={(trace?.source_bbox as number[]) ?? null}
        onClose={() => setTrace(null)}
      />
    </div>
  );
}
