"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Globe, Loader2, Play, RotateCcw, Save, XCircle, AlertTriangle, X } from "lucide-react";
import React, { useEffect, useState } from "react";

import { scraperApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { useScraperContext } from "./ScraperContext";

const STATUS_CONFIG: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string; bg: string; dot: string }> = {
  pending: { label: "等待中", icon: Clock, color: "text-warning", bg: "bg-warning/10 border-warning/20", dot: "bg-warning" },
  running: { label: "运行中", icon: Loader2, color: "text-primary", bg: "bg-primary/10 border-primary/20", dot: "bg-primary animate-pulse" },
  completed: { label: "已完成", icon: CheckCircle2, color: "text-success", bg: "bg-success/10 border-success/20", dot: "bg-success" },
  failed: { label: "失败", icon: AlertTriangle, color: "text-destructive", bg: "bg-destructive/10 border-destructive/20", dot: "bg-destructive" },
  cancelled: { label: "已取消", icon: XCircle, color: "text-muted-foreground", bg: "bg-muted border-border/50", dot: "bg-muted-foreground" },
};

const STATUS_FILTERS = [
  { value: "", label: "全部", count: 0 },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

export default function ScraperTaskCenter() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const { openScrapeDialog, triggerTaskRefresh, taskRefreshTrigger, newlyCreatedTaskId, setNewlyCreatedTaskId, triggerDraftRefresh } = useScraperContext();
  const queryClient = useQueryClient();

  // Auto-expand newly created task
  useEffect(() => {
    if (newlyCreatedTaskId) {
      setExpandedTask(newlyCreatedTaskId);
      setNewlyCreatedTaskId(null);
    }
  }, [newlyCreatedTaskId, setNewlyCreatedTaskId]);

  const { data, isLoading } = useQuery({
    queryKey: ["scraper-tasks", statusFilter, page, taskRefreshTrigger],
    queryFn: () => scraperApi.listTasks({ status: statusFilter || undefined, page, page_size: 20 }),
    refetchInterval: (query) => {
      const hasRunning = query.state.data?.tasks.some((t) => t.status === "running" || t.status === "pending");
      return hasRunning ? 5000 : false;
    },
  });

  const detailQuery = useQuery({
    queryKey: ["scraper-task-detail", expandedTask],
    queryFn: () => (expandedTask ? scraperApi.getTaskDetail(expandedTask) : null),
    enabled: !!expandedTask,
  });

  const rerunMutation = useMutation({
    mutationFn: (taskId: string) => scraperApi.rerunTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scraper-tasks"] });
      triggerTaskRefresh();
    },
  });

  const draftMutation = useMutation({
    mutationFn: (taskId: string) => scraperApi.getTaskDetail(taskId).then((task) =>
      scraperApi.createDraft({
        source_url: task.url,
        source_title: task.schema_name || task.url,
        schema_name: task.schema_name || "",
        raw_content: task.result || "",
        title: task.schema_name || task.url,
      })
    ),
    onSuccess: () => {
      triggerDraftRefresh();
    },
  });

  const tasks = data?.tasks || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 20);

  function formatTime(iso: string | undefined) {
    if (!iso) return "-";
    return new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function getDuration(start?: string, end?: string) {
    if (!start) return "-";
    const s = new Date(start).getTime();
    const e = end ? new Date(end).getTime() : Date.now();
    const sec = Math.round((e - s) / 1000);
    if (sec < 60) return `${sec}s`;
    return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  }

  return (
    <div className="flex h-full">
      {/* Task list */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b shrink-0 bg-card/50">
          <div className="flex items-center gap-1.5">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => { setStatusFilter(f.value); setPage(1); }}
                className={cn(
                  "px-3.5 py-1.5 text-sm rounded-lg transition-all duration-200 font-medium",
                  statusFilter === f.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                {f.label}
              </button>
            ))}
            <span className="ml-2 text-xs text-muted-foreground">共 {total} 条</span>
          </div>
          <button
            onClick={() => openScrapeDialog()}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 shadow-sm transition-all duration-200 active:scale-[0.98]"
          >
            <Play className="h-4 w-4" />
            新建抓取
          </button>
        </div>

        {/* Task list */}
        <div className="flex-1 overflow-auto p-3 space-y-2">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mb-3 text-primary/60" />
              <p className="text-sm">加载任务列表...</p>
            </div>
          ) : tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <div className="bg-muted/50 rounded-2xl p-6 mb-4">
                <Globe className="h-12 w-12 text-muted-foreground/30" />
              </div>
              <p className="text-sm font-medium mb-1">暂无抓取任务</p>
              <p className="text-xs text-muted-foreground/70 mb-4">创建一个新任务来开始抓取网页数据</p>
              <button
                onClick={() => openScrapeDialog()}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 shadow-sm transition-all"
              >
                <Play className="h-3.5 w-3.5" />
                创建第一个抓取任务
              </button>
            </div>
          ) : (
            tasks.map((task) => {
              const sc = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.pending!;
              const Icon = sc.icon;
              const isExpanded = expandedTask === task.task_id;
              return (
                <div
                  key={task.task_id}
                  className={cn(
                    "group rounded-xl border transition-all duration-200 cursor-pointer",
                    isExpanded
                      ? "border-primary/30 shadow-md bg-primary/[0.02] ring-1 ring-primary/10"
                      : "border-border bg-card shadow-sm hover:shadow-md hover:border-primary/20"
                  )}
                  onClick={() => setExpandedTask(isExpanded ? null : task.task_id)}
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Status badge */}
                    <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border", sc.bg, sc.color)}>
                      <Icon className={cn("h-3 w-3", task.status === "running" && "animate-spin")} />
                      {sc.label}
                    </div>

                    {/* URL & meta */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{task.url}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {task.provider_used && (
                          <span className="text-xs text-muted-foreground/80 bg-muted/50 px-1.5 py-0.5 rounded">{task.provider_used}</span>
                        )}
                        {task.schema_name && (
                          <span className="text-xs text-muted-foreground/80">· {task.schema_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Duration & time */}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {getDuration(task.started_at, task.completed_at)}
                      </span>
                      <span>{formatTime(task.created_at)}</span>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 px-4 py-3 border-t shrink-0 bg-card/50">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
            >
              上一页
            </button>
            <span className="text-sm text-muted-foreground font-medium tabular-nums">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {expandedTask && (
        <div className="w-[840px] border-l flex flex-col overflow-hidden shrink-0 bg-card">
          <div className="flex items-center justify-between px-5 py-3 border-b shrink-0 bg-card/80">
            <h3 className="text-sm font-semibold tracking-tight">任务详情</h3>
            <button
              onClick={() => setExpandedTask(null)}
              className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {detailQuery.isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-primary/60" />
            </div>
          ) : detailQuery.data ? (
            <div className="flex-1 overflow-auto">
              <div className="p-5 space-y-5">
                {/* Status + provider */}
                <div className="flex items-center gap-2">
                  {(() => {
                    const sc = STATUS_CONFIG[detailQuery.data.status] ?? STATUS_CONFIG.pending!;
                    const Icon = sc.icon;
                    return (
                      <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border", sc.bg, sc.color)}>
                        <Icon className={cn("h-3 w-3", detailQuery.data.status === "running" && "animate-spin")} />
                        {sc.label}
                      </div>
                    );
                  })()}
                  {detailQuery.data.provider_used && (
                    <span className="text-xs text-muted-foreground bg-muted/50 px-2 py-0.5 rounded">{detailQuery.data.provider_used}</span>
                  )}
                </div>

                {/* URL section */}
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">目标 URL</p>
                  <p className="text-sm break-all bg-muted/40 rounded-lg px-3 py-2 font-mono text-xs">{detailQuery.data.url}</p>
                </div>

                {/* Error */}
                {detailQuery.data.error && (
                  <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-destructive" />
                    <span>{detailQuery.data.error}</span>
                  </div>
                )}

                {/* Logs */}
                {detailQuery.data.logs && detailQuery.data.logs.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">执行日志</p>
                    <div className="bg-gray-950 text-gray-100 rounded-xl p-3 text-xs font-mono max-h-56 overflow-auto space-y-1 shadow-inner">
                      {detailQuery.data.logs
                        .filter((l) => l.type !== "heartbeat")
                        .map((log, i) => (
                          <div key={i} className={cn(
                            "leading-relaxed",
                            log.level === "error" ? "text-destructive" : log.level === "success" ? "text-success" : "text-muted-foreground"
                          )}>
                            {log.message || log.content || JSON.stringify(log)}
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Result preview */}
                {detailQuery.data.result && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">抓取结果</p>
                      <span className="text-xs text-muted-foreground tabular-nums">{detailQuery.data.result.length.toLocaleString()} 字符</span>
                    </div>
                    <div className="border rounded-xl p-3 text-sm max-h-72 overflow-auto whitespace-pre-wrap bg-muted/20 leading-relaxed">
                      {detailQuery.data.result.slice(0, 2000)}
                      {detailQuery.data.result.length > 2000 && <span className="text-muted-foreground">...</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="px-5 py-4 border-t bg-muted/20">
                <div className="flex gap-2">
                  {["completed", "failed"].includes(detailQuery.data.status) && (
                    <button
                      onClick={() => {
                        openScrapeDialog({
                          url: detailQuery.data!.url,
                          provider: detailQuery.data!.provider,
                          schema: detailQuery.data!.schema_name,
                        });
                      }}
                      className="flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 shadow-sm transition-all"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> 调整参数重跑
                    </button>
                  )}
                  {detailQuery.data.status === "completed" && detailQuery.data.result && (
                    <button
                      onClick={() => draftMutation.mutate(expandedTask)}
                      disabled={draftMutation.isPending}
                      className="flex items-center gap-1.5 px-4 py-2 border rounded-lg text-sm hover:bg-muted transition-colors shadow-sm disabled:opacity-50"
                    >
                      {draftMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                      保存草稿
                    </button>
                  )}
                  <button
                    onClick={() => rerunMutation.mutate(expandedTask)}
                    disabled={rerunMutation.isPending}
                    className="flex items-center gap-1.5 px-4 py-2 border rounded-lg text-sm hover:bg-muted transition-colors shadow-sm disabled:opacity-50"
                  >
                    {rerunMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                    快速重跑
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
