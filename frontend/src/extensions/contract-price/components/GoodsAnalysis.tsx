"use client";

import { useState } from "react";
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
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { BoxPlot } from "@/extensions/contract-price/components/BoxPlot";
import { useGoodsAnalysis } from "@/extensions/contract-price/hooks";
import type { CpaCluster } from "@/extensions/contract-price/types";

// ── helpers ──

function ChartCard({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-muted-foreground">{title}</h3>
          {meta ? <span className="text-xs text-muted-foreground/60 font-mono">{meta}</span> : null}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

// ── main component ──

export function GoodsAnalysis({
  clusters,
}: {
  clusters: CpaCluster[];
}) {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);

  const params = applied
    ? { name: applied }
    : selectedCluster
      ? { cluster_id: selectedCluster }
      : {};
  const { data, isLoading } = useGoodsAnalysis(params);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setApplied(search.trim());
    setSelectedCluster(null);
  };

  return (
    <div className="space-y-4">
      {/* Search + cluster select */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="输入货物名称搜索(如:多孔砖墙、电缆、钢管)..."
          className="flex-1"
        />
        <Button type="submit" size="sm">
          搜索
        </Button>
        <select
          className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
          value={selectedCluster ?? ""}
          onChange={(e) => {
            setSelectedCluster(e.target.value || null);
            setApplied("");
            setSearch("");
          }}
        >
          <option value="">选择聚类组...</option>
          {clusters.slice(0, 30).map((c) => (
            <option key={c.id} value={c.id}>
              {c.representative_name} ({c.item_count}条)
            </option>
          ))}
        </select>
      </form>

      {/* Results */}
      {isLoading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">分析中...</div>
      ) : !data || data.total === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          {applied || selectedCluster ? "未找到匹配的货物数据" : "输入货物名称或选择聚类组开始分析"}
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
    | { min: number; q1: number; median: number; q3: number; max: number; outliers: { unit_price: number }[] }
    | null;
  const bySupplier = (data.by_supplier ?? []) as { name: string; count: number; avg_price: number }[];
  const byDate = (data.by_date ?? []) as { month: string; count: number; avg_price: number }[];
  const priceRanges = (data.price_ranges ?? []) as { range: string; count: number }[];
  const items = (data.items ?? []) as Record<string, unknown>[];

  const goodsName = data.goods_name as string;
  const total = data.total as number;
  const okCount = data.ok_count as number;
  const nrCount = data.needs_review_count as number;

  const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#f43f5e"];

  return (
    <div className="space-y-4">
      {/* Title bar */}
      <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <h2 className="text-lg font-bold">{goodsName}</h2>
        <span className="rounded-full bg-emerald-500/10 px-3 py-0.5 text-xs font-semibold text-emerald-600">
          已校验 {okCount} / {total}
        </span>
        {nrCount > 0 ? (
          <span className="rounded-full bg-amber-500/10 px-3 py-0.5 text-xs font-semibold text-amber-600">
            待核验 {nrCount}
          </span>
        ) : null}
        {boxplot ? (
          <span className="ml-auto text-sm text-muted-foreground">
            均值 <span className="font-bold text-primary">{`¥${boxplot.mean.toFixed(2)}`}</span>
            <span className="ml-3 text-xs text-muted-foreground/60">
              区间 [¥{boxplot.min.toFixed(0)} — ¥{boxplot.max.toFixed(0)}]
            </span>
          </span>
        ) : null}
      </div>

      {/* Charts 2x2 grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Box plot */}
        <ChartCard title="价格分布(箱线图)" meta={boxplot ? `IQR = ${boxplot.iqr?.toFixed(0)}` : ""}>
          <div className="h-[220px]">
            <BoxPlot data={boxplot} />
          </div>
        </ChartCard>

        {/* Trend curve */}
        <ChartCard title="价格趋势" meta={byDate.length > 0 ? `${byDate.length} 个月` : "无日期数据"}>
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
                  <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.06} />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.4} />
                  <YAxis tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.4} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--background, #020617)",
                      border: "1px solid var(--border, #1e293b)",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
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
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                合同缺少签订日期,无法生成趋势
              </div>
            )}
          </div>
        </ChartCard>

        {/* Histogram */}
        <ChartCard title="价格区间分布" meta={`${total} 条`}>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={priceRanges} margin={{ left: 0, right: 20, top: 5 }}>
                <defs>
                  <linearGradient id="hist-bar" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.7} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.15} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.06} />
                <XAxis dataKey="range" tick={{ fontSize: 10 }} stroke="currentColor" opacity={0.4} />
                <YAxis tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.4} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--background, #020617)",
                    border: "1px solid var(--border, #1e293b)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="count" fill="url(#hist-bar)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        {/* Supplier comparison */}
        <ChartCard title="供应商均价对比" meta={`${bySupplier.length} 家`}>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bySupplier} layout="vertical" margin={{ left: 80, right: 20, top: 5 }}>
                <defs>
                  <linearGradient id="sup-bar" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.25} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.06} />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="currentColor" opacity={0.4} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  opacity={0.4}
                  width={80}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--background, #020617)",
                    border: "1px solid var(--border, #1e293b)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
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
      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold text-muted-foreground">价格明细(跨合同)</h3>
            <span className="text-xs text-muted-foreground/60 font-mono">{total} 条</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground/50">
                  <th className="px-5 py-2 text-left font-medium">合同编号</th>
                  <th className="px-5 py-2 text-left font-medium">供应商</th>
                  <th className="px-5 py-2 text-right font-medium">含税单价</th>
                  <th className="px-5 py-2 text-right font-medium">数量</th>
                  <th className="px-5 py-2 text-left font-medium">单位</th>
                  <th className="px-5 py-2 text-left font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const price = it.unit_price as number | null;
                  const isOutlier = it.is_outlier as boolean;
                  return (
                    <tr key={i} className="border-b border-border/40 hover:bg-primary/5">
                      <td className="px-5 py-2.5 font-mono text-xs text-muted-foreground">
                        {(it.contract_no as string) || "—"}
                      </td>
                      <td className="px-5 py-2.5 font-medium">{it.supplier as string}</td>
                      <td
                        className={`px-5 py-2.5 text-right font-mono font-semibold ${
                          isOutlier ? "text-rose-500" : "text-primary"
                        }`}
                      >
                        {price != null ? `¥${price.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-5 py-2.5 text-right font-mono text-muted-foreground">
                        {(it.quantity as number)?.toFixed(2) ?? "—"}
                      </td>
                      <td className="px-5 py-2.5">{(it.unit as string) || "—"}</td>
                      <td className="px-5 py-2.5 whitespace-nowrap">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            it.validation_status === "ok"
                              ? "bg-emerald-500/10 text-emerald-600"
                              : "bg-amber-500/10 text-amber-600"
                          }`}
                        >
                          {it.validation_status === "ok" ? "已校验" : "待核验"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
