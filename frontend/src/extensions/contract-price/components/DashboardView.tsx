"use client";

import { AlertTriangle, Boxes, FileText, ListChecks, PackageSearch, Play, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GoodsAnalysis } from "@/extensions/contract-price/components/GoodsAnalysis";
import { StatCard } from "@/extensions/contract-price/components/StatCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { useClusters, useDashboard, useRunPipeline } from "@/extensions/contract-price/hooks";

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

const statusTone: Record<string, string> = {
  completed: "text-emerald-500",
  running: "text-primary",
  failed: "text-destructive",
};

export function DashboardView() {
  const { data, isLoading, refetch, isFetching } = useDashboard();
  const runPipeline = useRunPipeline();
  const { data: clustersData } = useClusters({ limit: 30 });

  const d = data;
  const runCount = d?.recent_runs.length ?? 0;
  const clusters = clustersData?.items ?? [];

  return (
    <div className="space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 shrink-0">
            <PackageSearch className="h-[18px] w-[18px] text-blue-500" />
          </div>
          <div>
            <h1 className="text-[22px] font-bold tracking-tight">合同价格分析总览</h1>
            <p className="text-[13px] text-muted-foreground">跨合同货物价格基准 · 箱线图 / 趋势 / 供应商对比</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
          <Button size="sm" onClick={() => runPipeline.mutate({ mode: "table", trigger: "manual" })} disabled={runPipeline.isPending}>
            <Play className="h-4 w-4" />
            {runPipeline.isPending ? "启动中…" : "立即分析"}
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {isLoading ? (
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[88px] animate-pulse rounded-xl border border-border bg-card" />
          ))
        ) : (
          <>
            <StatCard label="合同数" value={d?.contract_count ?? 0} icon={FileText} hint={`已解析 ${d?.contract_count ?? 0} 份`} color="blue" />
            <StatCard label="分项条目" value={d?.item_count ?? 0} icon={ListChecks} color="violet" />
            <StatCard label="聚类组数" value={d?.cluster_count ?? 0} hint={`已确认 ${d?.confirmed_cluster_count ?? 0}`} icon={Boxes} color="amber" />
            <StatCard label="异常价格" value={d?.pending_cluster_count ?? 0} hint="离群 >1.5×IQR" icon={AlertTriangle} color="rose" />
          </>
        )}
      </div>

      {/* Cross-contract goods analysis */}
      <GoodsAnalysis clusters={clusters} />

      {runPipeline.isError ? (
        <p className="text-sm text-destructive">流水线启动失败：{(runPipeline.error).message}</p>
      ) : null}
      {runPipeline.isSuccess ? (
        <p className="text-sm text-emerald-500">已启动分析任务 {runPipeline.data.run_id}，稍后在「任务历史」查看进度。</p>
      ) : null}

      {/* Recent runs */}
      <Card>
        <CardContent className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-base font-semibold">最近任务</h3>
            <span className="text-xs text-muted-foreground">手动与定时的分析运行记录</span>
          </div>
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
