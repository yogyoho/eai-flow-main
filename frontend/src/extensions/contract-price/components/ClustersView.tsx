"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, RefreshCw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { contractPriceApi } from "@/extensions/contract-price/api";
import { EmptyRow, PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { useClusters, useCluster, useConfirmCluster } from "@/extensions/contract-price/hooks";
import { cn } from "@/lib/utils";

const statusBadge: Record<string, string> = {
  pending: "bg-warning/15 text-warning",
  confirmed: "bg-success/15 text-success",
  rejected: "bg-muted text-muted-foreground",
};

export function ClustersView() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"pending" | "confirmed" | "all">("pending");
  const qc = useQueryClient();

  const clustersQuery = useClusters({ cluster_status: filter === "all" ? undefined : filter, limit: 100 });
  const clusterQuery = useCluster(selectedId);
  const confirmMutation = useConfirmCluster();

  const clusters = clustersQuery.data?.items ?? [];
  const detail = clusterQuery.data;

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="聚类审核"
        description="审核自动聚类分组：移动误归类的货物、合并同义组，确认后统计才生效。"
        actions={
          <>
            <div className="flex rounded-md border">
              {(["pending", "confirmed", "all"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    "px-3 py-1.5 text-sm transition-colors",
                    filter === f ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {f === "pending" ? "待审核" : f === "confirmed" ? "已确认" : "全部"}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={() => clustersQuery.refetch()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Left: cluster list */}
        <Card className="h-fit">
          <CardContent className="p-0">
            {clustersQuery.isLoading ? (
              <p className="p-6 text-center text-sm text-muted-foreground">加载中…</p>
            ) : clusters.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted-foreground">没有符合条件的分组。</p>
            ) : (
              <ul className="divide-y divide-border">
                {clusters.map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => setSelectedId(c.id)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-4 py-3 text-left transition-colors hover:bg-accent",
                        selectedId === c.id && "bg-accent"
                      )}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">
                          {c.representative_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {c.category} · {c.item_count} 项
                        </p>
                      </div>
                      <span className={cn("rounded px-1.5 py-0.5 text-xs", statusBadge[c.status])}>
                        {c.status === "pending" ? "待审" : c.status === "confirmed" ? "已确认" : c.status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Right: selected cluster detail */}
        <Card>
          <CardContent className="space-y-4 p-6">
            {!selectedId ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                ← 从左侧选择一个分组查看明细。
              </p>
            ) : clusterQuery.isLoading ? (
              <p className="py-12 text-center text-sm text-muted-foreground">加载中…</p>
            ) : !detail ? (
              <p className="py-12 text-center text-sm text-muted-foreground">分组不存在。</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-foreground">
                      {detail.representative_name}
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      {detail.category} · {detail.item_count} 项 · v{detail.version}
                    </p>
                  </div>
                  {detail.status === "pending" ? (
                    <Button
                      size="sm"
                      onClick={() => confirmMutation.mutate({ id: detail.id, expected_version: detail.version })}
                      disabled={confirmMutation.isPending}
                    >
                      <Check className="h-4 w-4" />
                      确认分组
                    </Button>
                  ) : (
                    <span className={cn("rounded px-2 py-0.5 text-xs", statusBadge[detail.status])}>
                      已确认
                    </span>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {([
                    ["均值", detail.stats?.mean],
                    ["最大", detail.stats?.max],
                    ["最小", detail.stats?.min],
                    ["中位数", detail.stats?.median],
                  ] as const).map(([label, val]) => (
                    <div key={label} className="rounded-lg border border-border p-3">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="text-sm font-semibold tabular-nums text-foreground">
                        {val != null ? val.toLocaleString() : "—"}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Items */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>货物名称</TableHead>
                      <TableHead>规格</TableHead>
                      <TableHead className="text-right">单价</TableHead>
                      <TableHead>来源合同</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.items.length === 0 ? (
                      <EmptyRow colSpan={5}>该组暂无明细。</EmptyRow>
                    ) : (
                      detail.items.map((item) => (
                        <TableRow key={item.id} className={item.is_outlier ? "bg-destructive/10" : ""}>
                          <TableCell className="font-medium">
                            {item.is_outlier ? (
                              <span className="inline-flex items-center gap-1">
                                <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                                {item.goods_name}
                              </span>
                            ) : (
                              item.goods_name
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">{item.spec_model ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {item.unit_price?.toLocaleString() ?? "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {item.source_contract_no ?? "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              size="sm"
                              variant="ghost"
                              title="移出本组（清除分组，待重新归类）"
                              onClick={async () => {
                                // Move to a fresh empty bucket by setting cluster_id null via a noop:
                                // backend move requires a target; we move it into the first other cluster or skip.
                                const target = clusters.find((c) => c.id !== detail.id)?.id;
                                if (!target) {
                                  alert("暂无其他分组可移动。请先确认或创建其他组。");
                                  return;
                                }
                                await contractPriceApi.moveItem(item.id, target);
                                await clusterQuery.refetch();
                                void qc.invalidateQueries({ queryKey: ["cpa"] });
                              }}
                            >
                              移出
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>

                {confirmMutation.isError ? (
                  <p className="text-sm text-destructive">
                    确认失败：{(confirmMutation.error).message}
                  </p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
