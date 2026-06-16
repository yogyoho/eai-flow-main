"use client";

import { Download, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyRow, PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import { useRuns } from "@/extensions/contract-price/hooks";
import { cn } from "@/lib/utils";

const statusTone: Record<string, string> = {
  completed: "text-success",
  running: "text-primary",
  failed: "text-destructive",
};

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

export function TasksView() {
  const { data, isLoading, isFetching, refetch } = useRuns({ limit: 50 });
  const runs = data?.items ?? [];

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="任务历史"
        description="手动与定时分析任务的运行记录，可下载产出的 Excel 报告。"
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
        }
      />

      <Card>
        <CardContent className="p-6">
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
                <TableHead className="text-right">报告</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={8}>加载中…</EmptyRow>
              ) : runs.length === 0 ? (
                <EmptyRow colSpan={8}>暂无运行记录。</EmptyRow>
              ) : (
                runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="whitespace-nowrap">{formatDate(run.started_at)}</TableCell>
                    <TableCell>{run.trigger_type === "scheduled" ? "定时" : "手动"}</TableCell>
                    <TableCell className={cn(statusTone[run.status] ?? "")}>{run.status}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.docs_processed}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.items_extracted}</TableCell>
                    <TableCell className="text-right tabular-nums">{run.clusters_formed}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {run.excel_path ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          title="下载 Excel"
                          onClick={() => {
                            // Trigger download via the API (auth cookie sent by browser navigation).
                            window.open(
                              `/api/extensions/contract-price/runs/${run.id}/excel`,
                              "_blank"
                            );
                          }}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
          {runs.some((r) => r.status === "failed" && r.error) ? (
            <div className="mt-4 space-y-1 text-xs text-destructive">
              {runs
                .filter((r) => r.status === "failed" && r.error)
                .slice(0, 3)
                .map((r) => (
                  <p key={r.id} className="truncate">
                    {formatDate(r.started_at)}: {r.error}
                  </p>
                ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
