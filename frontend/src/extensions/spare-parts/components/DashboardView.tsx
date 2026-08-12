"use client";

import { AlertTriangle, Boxes, FileText, ListChecks, PackageSearch, Play, RefreshCw, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PartAnalysis } from "@/extensions/spare-parts/components/PartAnalysis";
import { StatCard } from "@/extensions/spare-parts/components/StatCard";
import { useClusters, useDashboard, useRunPipeline } from "@/extensions/spare-parts/hooks";

export function DashboardView() {
  const { data, isLoading, refetch, isFetching } = useDashboard();
  const runPipeline = useRunPipeline();
  const { data: clustersData } = useClusters({ limit: 30 });

  const d = data;
  const clusters = clustersData?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-6 p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 shrink-0">
            <PackageSearch className="h-[18px] w-[18px] text-blue-500" />
          </div>
          <div>
            <h1 className="text-[22px] font-bold tracking-tight">备品备件价格分析总览</h1>
            <p className="text-[13px] text-muted-foreground">跨客户备品备件价格基准 · 箱线图 / 趋势 / 客户对比</p>
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {isLoading ? (
          [0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-[88px] animate-pulse rounded-xl border border-border bg-card" />
          ))
        ) : (
          <>
            <StatCard label="文档数" value={d?.contract_count ?? 0} icon={FileText} hint={`已解析 ${d?.contract_count ?? 0} 份`} color="blue" />
            <StatCard label="分项条目" value={d?.item_count ?? 0} icon={ListChecks} color="violet" />
            <StatCard label="客户数" value={d?.customer_count ?? 0} icon={Users} hint="已归并客户" color="emerald" />
            <StatCard label="分组数" value={d?.cluster_count ?? 0} hint={`已确认 ${d?.confirmed_cluster_count ?? 0}`} icon={Boxes} color="amber" />
            <StatCard label="异常价格" value={d?.outlier_count ?? 0} hint="离群 >1.5×IQR" icon={AlertTriangle} color="rose" />
          </>
        )}
      </div>

      {/* Cross-contract goods analysis */}
      <PartAnalysis clusters={clusters} />

      {runPipeline.isError ? (
        <p className="text-sm text-destructive">流水线启动失败：{(runPipeline.error).message}</p>
      ) : null}
      {runPipeline.isSuccess ? (
        <p className="text-sm text-emerald-500">已启动分析任务 {runPipeline.data.run_id}，稍后在「任务历史」查看进度。</p>
      ) : null}

    </div>
  );
}
