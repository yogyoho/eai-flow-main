"use client";

import { LayoutDashboard, Play, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { GoodsAnalysis } from "@/extensions/contract-price/components/GoodsAnalysis";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { StatCard } from "@/extensions/contract-price/components/StatCard";
import { useDashboard, useRunPipeline } from "@/extensions/contract-price/hooks";

export function DashboardView() {
  const { data, isLoading, refetch, isFetching } = useDashboard();
  const runPipeline = useRunPipeline();

  const d = data;
  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
      {/* 页头卡（cpa UI 重构规范 §2-1）：点阵底纹 + 图标容器 + 右侧动作 */}
      <PageHeader
        title="合同价格分析总览"
        description="跨合同货物价格基准 · 箱线图 / 趋势 / 供应商对比"
        icon={<LayoutDashboard />}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
              刷新
            </Button>
            <Button size="sm" onClick={() => runPipeline.mutate({ mode: "table", trigger: "manual" })} disabled={runPipeline.isPending}>
              <Play className="h-4 w-4" />
              {runPipeline.isPending ? "启动中…" : "立即分析"}
            </Button>
          </>
        }
      />

      {/* 指标格（§2-2）：无图标 label/数值上下排，accent 左竖条 / warn 数值橙 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {isLoading ? (
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[72px] animate-pulse rounded-md border border-border bg-card" />
          ))
        ) : (
          <>
            <StatCard label="合同数" value={d?.contract_count ?? 0} hint="份" />
            <StatCard label="分项条目" value={d?.item_count ?? 0} />
            <StatCard label="分组数" value={d?.cluster_count ?? 0} hint={`已确认 ${d?.confirmed_cluster_count ?? 0}`} tone="accent" />
            <StatCard label="异常价格" value={d?.outlier_count ?? 0} hint="离群 >1.5×IQR" tone="warn" />
          </>
        )}
      </div>

      {/* Cross-contract goods analysis */}
      <GoodsAnalysis />

      {runPipeline.isError ? (
        <p className="text-sm text-destructive">流水线启动失败：{(runPipeline.error).message}</p>
      ) : null}
      {runPipeline.isSuccess ? (
        <p className="text-sm text-success">已启动分析任务 {runPipeline.data.run_id}，稍后在「任务历史」查看进度。</p>
      ) : null}

    </div>
  );
}
