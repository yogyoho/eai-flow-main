"use client";

import { useState } from "react";
import { Activity, BarChart3, Building2, Check, ChevronsUpDown, LayoutGrid, PackageSearch, Table2 } from "lucide-react";
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
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BoxPlot } from "@/extensions/contract-price/components/BoxPlot";
import { useGoodsAnalysis } from "@/extensions/contract-price/hooks";
import type { CpaCluster } from "@/extensions/contract-price/types";

// ── chart card matching prototype style ──

function ChartCard({ title, meta, icon, children }: { title: string; meta?: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08),0_1px_3px_rgba(0,0,0,0.05)] p-5 transition-shadow hover:shadow-[0_10px_30px_-10px_rgba(15,23,42,0.12),0_2px_6px_rgba(0,0,0,0.06)]">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
          {icon}
          {title}
        </h3>
        {meta ? <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-bold text-muted-foreground">{meta}</span> : null}
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

const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#f43f5e"];

// ── main component ──

export function GoodsAnalysis({ clusters }: { clusters: CpaCluster[] }) {
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const params = selectedCluster ? { cluster_id: selectedCluster } : {};
  const { data, isLoading } = useGoodsAnalysis(params);

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4">
      {/* Cluster select */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-muted-foreground shrink-0">选择货物：</span>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={open}
              className="h-[42px] min-w-[260px] justify-between rounded-lg font-normal"
            >
              {selectedCluster
                ? clusters.find((c) => c.id === selectedCluster)?.representative_name ?? "选择货物聚类组..."
                : "选择货物聚类组..."}
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[400px] p-0" align="start">
            <Command>
              <CommandInput placeholder="输入名称模糊检索..." />
              <CommandList>
                <CommandEmpty>未找到匹配的货物</CommandEmpty>
                <CommandGroup>
                  {clusters.slice(0, 30).map((c) => (
                    <CommandItem
                      key={c.id}
                      value={c.representative_name}
                      onSelect={() => {
                        setSelectedCluster(c.id);
                        setOpen(false);
                      }}
                    >
                      <Check
                        className={`h-4 w-4 shrink-0 ${selectedCluster === c.id ? "opacity-100" : "opacity-0"}`}
                      />
                      <span className="truncate">{c.representative_name}</span>
                      <span className="ml-auto font-mono text-xs text-muted-foreground">
                        {c.item_count}条
                      </span>
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
        <div className="flex flex-1 items-center justify-center py-20 text-sm text-muted-foreground">分析中...</div>
      ) : !data || data.total === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center py-20 text-center">
          <PackageSearch className="mb-3 h-12 w-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">
            {selectedCluster ? "未找到匹配的货物数据" : "选择货物聚类组开始分析"}
          </p>
        </div>
      ) : (
        <AnalysisResult data={data} />
      )}
    </div>
  );
}

// ── result renderer ──

function AnalysisResult({ data }: { data: Record<string, unknown> }) {
  const boxplot = data.boxplot as
    | { min: number; q1: number; median: number; q3: number; max: number; mean: number; iqr?: number; outliers: { unit_price: number }[] }
    | null;
  const bySupplier = (data.by_supplier ?? []) as { name: string; count: number; avg_price: number }[];
  const byDate = (data.by_date ?? []) as { month: string; count: number; avg_price: number }[];
  const priceRanges = (data.price_ranges ?? []) as { range: string; count: number }[];
  const items = (data.items ?? []) as Record<string, unknown>[];
  const goodsName = data.goods_name as string;
  const total = data.total as number;
  const okCount = data.ok_count as number;
  const nrCount = data.needs_review_count as number;

  return (
    <div className="space-y-4">
      {/* Title bar */}
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-5 py-3.5 shadow-sm">
        <h2 className="text-lg font-bold tracking-tight">{goodsName}</h2>
        <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-600">
          已校验 {okCount} / {total}
        </span>
        {nrCount > 0 ? (
          <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-600">
            待核验 {nrCount}
          </span>
        ) : null}
        {boxplot ? (
          <div className="ml-auto flex items-center gap-4 text-sm text-muted-foreground">
            <span>
              均值 <span className="font-bold text-primary">{`¥${boxplot.mean.toFixed(2)}`}</span>
            </span>
            <span className="text-xs text-muted-foreground/60">
              区间 [¥{boxplot.min.toFixed(0)} — ¥{boxplot.max.toFixed(0)}]
            </span>
          </div>
        ) : null}
      </div>

      {/* Charts 2x2 grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Box plot */}
        <ChartCard title="价格分布(箱线图)" meta={boxplot ? `IQR = ${boxplot.iqr?.toFixed(0)}` : ""} icon={<LayoutGrid className="h-[15px] w-[15px] text-muted-foreground/50" />}>
          <div className="h-[220px]">
            <BoxPlot data={boxplot} />
          </div>
        </ChartCard>

        {/* Trend curve */}
        <ChartCard title="价格趋势" meta={byDate.length > 0 ? `${byDate.length} 个月` : "无日期数据"} icon={<Activity className="h-[15px] w-[15px] text-muted-foreground/50" />}>
          <div className="h-[220px]">
            {byDate.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={byDate} margin={{ left: 0, right: 20, top: 5 }}>
                  <defs>
                    <linearGradient id="trend-line" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(100,116,139,0.22)" />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fontFamily: "monospace", fill: "rgba(71,85,105,0.85)" }} stroke="rgba(100,116,139,0.5)" />
                  <YAxis tick={{ fontSize: 12, fontFamily: "monospace", fill: "rgba(71,85,105,0.85)" }} stroke="rgba(100,116,139,0.5)" />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line type="monotone" dataKey="avg_price" stroke="url(#trend-line)" strokeWidth={2.5} dot={{ r: 4, fill: "#3b82f6", strokeWidth: 0 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                合同缺少签订日期,无法生成趋势
              </div>
            )}
          </div>
        </ChartCard>

        {/* Histogram */}
        <ChartCard title="价格区间分布" meta={`${total} 条`} icon={<BarChart3 className="h-[15px] w-[15px] text-muted-foreground/50" />}>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={priceRanges} margin={{ left: 0, right: 20, top: 5 }}>
                <defs>
                  <linearGradient id="hist-bar" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.7} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.15} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(100,116,139,0.22)" />
                <XAxis dataKey="range" tick={{ fontSize: 12, fontFamily: "monospace", fill: "rgba(71,85,105,0.85)" }} stroke="rgba(100,116,139,0.5)" />
                <YAxis tick={{ fontSize: 12, fontFamily: "monospace", fill: "rgba(71,85,105,0.85)" }} stroke="rgba(100,116,139,0.5)" allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" fill="url(#hist-bar)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        {/* Supplier comparison */}
        <ChartCard title="供应商均价对比" meta={`${bySupplier.length} 家`} icon={<Building2 className="h-[15px] w-[15px] text-muted-foreground/50" />}>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bySupplier} layout="vertical" margin={{ left: 80, right: 20, top: 5 }}>
                <defs>
                  <linearGradient id="sup-bar" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.25} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(100,116,139,0.22)" />
                <XAxis type="number" tick={{ fontSize: 12, fontFamily: "monospace", fill: "rgba(71,85,105,0.85)" }} stroke="rgba(100,116,139,0.5)" />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="rgba(148,163,184,0.4)" width={80} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="avg_price" fill="url(#sup-bar)" radius={[0, 4, 4, 0]}>
                  {bySupplier.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.5} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      {/* Detail table */}
      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <Table2 className="h-[15px] w-[15px] text-muted-foreground/50" />
            价格明细(跨合同)
          </h3>
          <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-bold text-muted-foreground">{total} 条</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground/50">
                <th className="px-5 py-2.5 text-left font-semibold">合同编号</th>
                <th className="px-5 py-2.5 text-left font-semibold">供应商</th>
                <th className="px-5 py-2.5 text-right font-semibold">含税单价</th>
                <th className="px-5 py-2.5 text-right font-semibold">数量</th>
                <th className="px-5 py-2.5 text-left font-semibold">单位</th>
                <th className="px-5 py-2.5 text-left font-semibold whitespace-nowrap">状态</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => {
                const price = it.unit_price as number | null;
                const isOutlier = it.is_outlier as boolean;
                return (
                  <tr key={i} className="border-b border-border/40 transition-colors hover:bg-primary/5">
                    <td className="px-5 py-2.5 font-mono text-[11px] text-muted-foreground">{(it.contract_no as string) || "—"}</td>
                    <td className="px-5 py-2.5 font-medium">{it.supplier as string}</td>
                    <td className={`px-5 py-2.5 text-right font-mono font-semibold ${isOutlier ? "text-rose-500" : "text-primary"}`}>
                      {price != null ? `¥${price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-5 py-2.5 text-right font-mono text-muted-foreground">{(it.quantity as number)?.toFixed(2) ?? "—"}</td>
                    <td className="px-5 py-2.5">{(it.unit as string) || "—"}</td>
                    <td className="px-5 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-[11px] font-medium ${it.validation_status === "ok" ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600"}`}>
                        {it.validation_status === "ok" ? "已校验" : "待核验"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
