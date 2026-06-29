"use client";

import { AlertTriangle, Boxes, FileText, ListChecks, PackageSearch, Play, RefreshCw } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatCard } from "@/extensions/contract-price/components/StatCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { useDashboard, useRunPipeline } from "@/extensions/contract-price/hooks";

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

const statusTone: Record<string, string> = {
  completed: "text-success",
  running: "text-primary",
  failed: "text-destructive",
};

export function DashboardView() {
  const { data, isLoading, refetch, isFetching } = useDashboard();
  const runPipeline = useRunPipeline();

  const d = data;
  const runCount = d?.recent_runs.length ?? 0;

  return (
    <div className="space-y-6 p-8">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-1 border rounded-sm bg-blue-50 border-blue-200 text-blue-600 shrink-0">
            <PackageSearch className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">合同价格分析总览</h1>
            <p className="text-sm text-muted-foreground">
              OCR 提取合同分项价格，按货物名称聚类归并并统计含税单价。
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
          <Button
            size="sm"
            onClick={() => runPipeline.mutate({ mode: "table", trigger: "manual" })}
            disabled={runPipeline.isPending}
          >
            <Play className="h-4 w-4" />
            {runPipeline.isPending ? "启动中…" : "立即分析"}
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCardLazy
          label="合同数"
          value={d?.contract_count ?? 0}
          icon={FileText}
          isLoading={isLoading}
        />
        <StatCardLazy
          label="货物条目"
          value={d?.item_count ?? 0}
          icon={ListChecks}
          isLoading={isLoading}
        />
        <StatCardLazy
          label="聚类组数"
          value={d?.cluster_count ?? 0}
          hint={`已确认 ${d?.confirmed_cluster_count ?? 0}`}
          icon={Boxes}
          isLoading={isLoading}
        />
        <StatCardLazy
          label="待审核组数"
          value={d?.pending_cluster_count ?? 0}
          icon={AlertTriangle}
          tone={d && d.pending_cluster_count > 0 ? "warning" : "default"}
          isLoading={isLoading}
        />
      </div>

      {/* Charts (T7) */}
      {d?.charts ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard title="货物均价 Top10" subtitle="按条目数排序的聚类组">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={d.charts.top_goods} layout="vertical" margin={{ left: 8, right: 24, top: 8 }}>
                <CartesianGrid horizontal={false} stroke="#e5e7eb" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="avg_price" name="均价" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="价格区间分布" subtitle="含税单价分桶的条目数">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={d.charts.price_ranges} margin={{ top: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="range" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" name="条目数" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="校验状态分布" subtitle="ok / 待核验 / 已修正">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={d.charts.validation}
                  dataKey="count"
                  nameKey="status"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  labelLine={false}
                >
                  {d.charts.validation.map((v) => (
                    <Cell
                      key={v.status}
                      fill={v.status === "ok" ? "#10b981" : v.status === "needs_review" ? "#f59e0b" : "#6b7280"}
                    />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="聚类规模分布" subtitle="每簇条目数分桶">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={d.charts.cluster_sizes} margin={{ top: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="range" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" name="聚类数" fill="#06b6d4" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      ) : null}

      {runPipeline.isError ? (
        <p className="text-sm text-destructive">
          流水线启动失败：{(runPipeline.error).message}
        </p>
      ) : null}
      {runPipeline.isSuccess ? (
        <p className="text-sm text-success">
          已启动分析任务 {runPipeline.data.run_id}，稍后在「任务历史」查看进度。
        </p>
      ) : null}

      {/* Recent runs */}
      <Card>
        <CardHeader>
          <CardTitle>最近任务</CardTitle>
          <CardDescription>手动与定时的分析运行记录</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
          ) : runCount === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无运行记录。点击「立即分析」开始首次提取。
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>开始时间</TableHead>
                  <TableHead>触发</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">合同</TableHead>
                  <TableHead className="text-right">条目</TableHead>
                  <TableHead className="text-right">聚类</TableHead>
                  <TableHead className="text-right">耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d!.recent_runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="whitespace-nowrap">{formatDate(run.started_at)}</TableCell>
                    <TableCell>{run.trigger_type === "scheduled" ? "定时" : "手动"}</TableCell>
                    <TableCell className={statusTone[run.status] ?? ""}>{run.status}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.docs_processed}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.items_extracted}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.clusters_formed}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCardLazy(props: {
  label: string;
  value: number;
  icon: LucideIcon;
  hint?: string;
  tone?: "default" | "warning" | "success" | "destructive";
  isLoading: boolean;
}) {
  if (props.isLoading) {
    return (
      <Card>
        <CardContent className="p-5">
          <div className="h-12 animate-pulse rounded-xl bg-muted" />
        </CardContent>
      </Card>
    );
  }
  return <StatCard {...props} />;
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {subtitle ? <CardDescription>{subtitle}</CardDescription> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
