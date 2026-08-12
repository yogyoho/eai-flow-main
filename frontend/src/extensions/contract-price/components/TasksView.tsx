"use client";

import { Download, PackageSearch, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { useDeleteRun, useRuns } from "@/extensions/contract-price/hooks";
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

/** Download a run's Excel via credentialed fetch → blob (auth-cookie safe,
 * unlike window.open which can silently fail on expired sessions). */
async function downloadExcel(runId: string) {
  const res = await fetch(`/api/extensions/contract-price/runs/${runId}/excel`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`下载失败 (${res.status})`);
  const blob = await res.blob();
  // try Content-Disposition filename, else derive from run id
  const cd = res.headers.get("content-disposition") ?? "";
  const match = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
  const filename = match?.[1] ? decodeURIComponent(match[1]) : `run-${runId.slice(0, 8)}.xlsx`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const COL_SPAN = 12;

export function TasksView() {
  const [runStatus, setRunStatus] = useState<"all" | "running" | "completed" | "failed">("all");
  const { data, isLoading, isFetching, refetch } = useRuns({
    run_status: runStatus === "all" ? undefined : runStatus,
    limit: 50,
  });
  const deleteRun = useDeleteRun();
  const runs = data?.items ?? [];
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // clear selection when filter/refetch changes which runs are visible
  useEffect(() => { setSelected(new Set()); }, [runStatus, data]);

  const allSelected = useMemo(
    () => runs.length > 0 && runs.every((r) => selected.has(r.id)),
    [runs, selected],
  );

  const toggleAll = useCallback(() => {
    setSelected(allSelected ? new Set() : new Set(runs.map((r) => r.id)));
  }, [runs, allSelected]);

  const toggleOne = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="任务中心"
        description="手动与定时分析任务的运行记录，可下载产出的 Excel 报告。"
        icon={<PackageSearch className="w-4 h-4" />}
        actions={
          <>
            <div className="flex rounded-md border">
              {(["all", "running", "completed", "failed"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setRunStatus(f)}
                  className={cn(
                    "px-3 py-1.5 text-xs transition-colors",
                    runStatus === f ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f === "all" ? "全部" : f === "running" ? "运行中" : f === "completed" ? "完成" : "失败"}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
              刷新
            </Button>
          </>
        }
      />

      {/* Batch delete bar */}
      {selected.size > 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5">
          <span className="text-sm font-medium">已选 {selected.size} 项</span>
          <Button
            variant="destructive"
            size="sm"
            disabled={deleteRun.isPending}
            onClick={() => {
              if (!confirm(`确认删除选中的 ${selected.size} 条运行记录？`)) return;
              Promise.all([...selected].map((id) => deleteRun.mutateAsync(id))).finally(() =>
                setSelected(new Set()),
              );
            }}
          >
            <Trash2 className="h-4 w-4" />
            {deleteRun.isPending ? "删除中…" : "批量删除"}
          </Button>
        </div>
      ) : null}

      <Card>
        <CardContent className="p-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
                </TableHead>
                <TableHead>任务名称</TableHead>
                <TableHead>开始时间</TableHead>
                <TableHead>触发</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">进度</TableHead>
                <TableHead className="text-right">合同</TableHead>
                <TableHead className="text-right">条目</TableHead>
                <TableHead className="text-right">分组</TableHead>
                <TableHead className="text-right">耗时</TableHead>
                <TableHead className="text-right">报告</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <EmptyRow colSpan={COL_SPAN}>加载中…</EmptyRow>
              ) : runs.length === 0 ? (
                <EmptyRow colSpan={COL_SPAN}>暂无运行记录。</EmptyRow>
              ) : (
                runs.map((run) => (
                  <TableRow key={run.id} className={selected.has(run.id) ? "bg-primary/5" : undefined}>
                    <TableCell>
                      <Checkbox checked={selected.has(run.id)} onCheckedChange={() => toggleOne(run.id)} />
                    </TableCell>
                    <TableCell>{run.label || "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatDate(run.started_at)}</TableCell>
                    <TableCell>{run.trigger_type === "scheduled" ? "定时" : "手动"}</TableCell>
                    <TableCell className={cn(statusTone[run.status] ?? "")}>{run.status}</TableCell>
                    <TableCell className="text-right">
                      {run.status === "running" && run.progress ? (
                        <div className="flex flex-col items-end gap-1">
                          <span className="text-xs tabular-nums">
                            {run.progress.done}/{run.progress.total}
                            {run.progress.failed ? `（失败 ${run.progress.failed}）` : ""}
                          </span>
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full bg-primary transition-all"
                              style={{
                                width: `${run.progress.total ? (run.progress.done / run.progress.total) * 100 : 0}%`,
                              }}
                            />
                          </div>
                          {run.progress.processing?.length ? (
                            <span
                              className="max-w-[220px] truncate text-[10px] text-muted-foreground"
                              title={run.progress.processing.join(", ")}
                            >
                              处理中: {run.progress.processing.join(", ")}
                            </span>
                          ) : null}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
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
                            downloadExcel(run.id).catch((e) => {
                              alert(e instanceof Error ? e.message : "下载失败");
                            });
                          }}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="icon"
                        variant="ghost"
                        title="删除"
                        disabled={deleteRun.isPending}
                        onClick={() => {
                          if (!confirm("确认删除此运行记录？")) return;
                          deleteRun.mutate(run.id);
                        }}
                      >
                        <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                      </Button>
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
