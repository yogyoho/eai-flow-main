"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock,
  Globe,
  Loader2,
  Play,
  RotateCcw,
  Save,
  XCircle,
  AlertTriangle,
  X,
} from "lucide-react";
import React, { useEffect, useState } from "react";

import { scraperApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { useScraperContext } from "./ScraperContext";

const STATUS_CONFIG: Record<
  string,
  {
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bg: string;
    dot: string;
  }
> = {
  pending: {
    label: "等待中",
    icon: Clock,
    color: "text-warning",
    bg: "bg-warning/10 border-warning/20",
    dot: "bg-warning",
  },
  running: {
    label: "运行中",
    icon: Loader2,
    color: "text-primary",
    bg: "bg-primary/10 border-primary/20",
    dot: "bg-primary animate-pulse",
  },
  completed: {
    label: "已完成",
    icon: CheckCircle2,
    color: "text-success",
    bg: "bg-success/10 border-success/20",
    dot: "bg-success",
  },
  failed: {
    label: "失败",
    icon: AlertTriangle,
    color: "text-destructive",
    bg: "bg-destructive/10 border-destructive/20",
    dot: "bg-destructive",
  },
  cancelled: {
    label: "已取消",
    icon: XCircle,
    color: "text-muted-foreground",
    bg: "bg-muted border-border/50",
    dot: "bg-muted-foreground",
  },
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
  const {
    openScrapeDialog,
    triggerTaskRefresh,
    taskRefreshTrigger,
    newlyCreatedTaskId,
    setNewlyCreatedTaskId,
    triggerDraftRefresh,
  } = useScraperContext();
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
    queryFn: () =>
      scraperApi.listTasks({
        status: statusFilter || undefined,
        page,
        page_size: 20,
      }),
    refetchInterval: (query) => {
      const hasRunning = query.state.data?.tasks.some(
        (t) => t.status === "running" || t.status === "pending",
      );
      return hasRunning ? 5000 : false;
    },
  });

  const detailQuery = useQuery({
    queryKey: ["scraper-task-detail", expandedTask],
    queryFn: () =>
      expandedTask ? scraperApi.getTaskDetail(expandedTask) : null,
    enabled: !!expandedTask,
  });

  const rerunMutation = useMutation({
    mutationFn: (taskId: string) => scraperApi.rerunTask(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["scraper-tasks"] });
      triggerTaskRefresh();
    },
  });

  const draftMutation = useMutation({
    mutationFn: (taskId: string) =>
      scraperApi.getTaskDetail(taskId).then((task) =>
        scraperApi.createDraft({
          source_url: task.url,
          source_title: task.schema_name ?? task.url,
          schema_name: task.schema_name ?? "",
          raw_content: task.result ?? "",
          title: task.schema_name ?? task.url,
        }),
      ),
    onSuccess: () => {
      triggerDraftRefresh();
    },
  });

  const tasks = data?.tasks ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  function formatTime(iso: string | undefined) {
    if (!iso) return "-";
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
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
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <div className="bg-card/50 flex shrink-0 items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-1.5">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => {
                  setStatusFilter(f.value);
                  setPage(1);
                }}
                className={cn(
                  "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
                  statusFilter === f.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {f.label}
              </button>
            ))}
            <span className="text-muted-foreground ml-2 text-xs">
              共 {total} 条
            </span>
          </div>
          <button
            onClick={() => openScrapeDialog()}
            className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-all duration-200 active:scale-[0.98]"
          >
            <Play className="h-4 w-4" />
            新建抓取
          </button>
        </div>

        {/* Task list */}
        <div className="flex-1 space-y-2 overflow-auto p-3">
          {isLoading ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-24">
              <Loader2 className="text-primary/60 mb-3 h-6 w-6 animate-spin" />
              <p className="text-sm">加载任务列表...</p>
            </div>
          ) : tasks.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-24">
              <div className="bg-muted/50 mb-4 rounded-2xl p-6">
                <Globe className="text-muted-foreground/30 h-12 w-12" />
              </div>
              <p className="mb-1 text-sm font-medium">暂无抓取任务</p>
              <p className="text-muted-foreground/70 mb-4 text-xs">
                创建一个新任务来开始抓取网页数据
              </p>
              <button
                onClick={() => openScrapeDialog()}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-all"
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
                    "group cursor-pointer rounded-xl border transition-all duration-200",
                    isExpanded
                      ? "border-primary/30 bg-primary/[0.02] ring-primary/10 shadow-md ring-1"
                      : "border-border bg-card hover:border-primary/20 shadow-sm hover:shadow-md",
                  )}
                  onClick={() =>
                    setExpandedTask(isExpanded ? null : task.task_id)
                  }
                >
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Status badge */}
                    <div
                      className={cn(
                        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium",
                        sc.bg,
                        sc.color,
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-3 w-3",
                          task.status === "running" && "animate-spin",
                        )}
                      />
                      {sc.label}
                    </div>

                    {/* URL & meta */}
                    <div className="min-w-0 flex-1">
                      <p className="group-hover:text-primary truncate text-sm font-medium transition-colors">
                        {task.url}
                      </p>
                      <div className="mt-0.5 flex items-center gap-2">
                        {task.provider_used && (
                          <span className="text-muted-foreground/80 bg-muted/50 rounded px-1.5 py-0.5 text-xs">
                            {task.provider_used}
                          </span>
                        )}
                        {task.schema_name && (
                          <span className="text-muted-foreground/80 text-xs">
                            · {task.schema_name}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Duration & time */}
                    <div className="text-muted-foreground flex shrink-0 items-center gap-3 text-xs">
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
          <div className="bg-card/50 flex shrink-0 items-center justify-center gap-3 border-t px-4 py-3">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="bg-card hover:bg-muted rounded-lg border px-4 py-1.5 text-sm shadow-sm transition-colors disabled:pointer-events-none disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-muted-foreground text-sm font-medium tabular-nums">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="bg-card hover:bg-muted rounded-lg border px-4 py-1.5 text-sm shadow-sm transition-colors disabled:pointer-events-none disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {expandedTask && (
        <div className="bg-card flex w-[840px] shrink-0 flex-col overflow-hidden border-l">
          <div className="bg-card/80 flex shrink-0 items-center justify-between border-b px-5 py-3">
            <h3 className="text-sm font-semibold tracking-tight">任务详情</h3>
            <button
              onClick={() => setExpandedTask(null)}
              className="hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg p-1.5 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {detailQuery.isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="text-primary/60 h-6 w-6 animate-spin" />
            </div>
          ) : detailQuery.data ? (
            <div className="flex-1 overflow-auto">
              <div className="space-y-5 p-5">
                {/* Status + provider */}
                <div className="flex items-center gap-2">
                  {(() => {
                    const sc =
                      STATUS_CONFIG[detailQuery.data.status] ??
                      STATUS_CONFIG.pending!;
                    const Icon = sc.icon;
                    return (
                      <div
                        className={cn(
                          "flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium",
                          sc.bg,
                          sc.color,
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-3 w-3",
                            detailQuery.data.status === "running" &&
                              "animate-spin",
                          )}
                        />
                        {sc.label}
                      </div>
                    );
                  })()}
                  {detailQuery.data.provider_used && (
                    <span className="text-muted-foreground bg-muted/50 rounded px-2 py-0.5 text-xs">
                      {detailQuery.data.provider_used}
                    </span>
                  )}
                </div>

                {/* URL section */}
                <div className="space-y-1.5">
                  <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                    目标 URL
                  </p>
                  <p className="bg-muted/40 rounded-lg px-3 py-2 font-mono text-sm text-xs break-all">
                    {detailQuery.data.url}
                  </p>
                </div>

                {/* Error */}
                {detailQuery.data.error && (
                  <div className="bg-destructive/10 border-destructive/20 text-destructive flex items-start gap-2 rounded-xl border p-3 text-sm">
                    <AlertTriangle className="text-destructive mt-0.5 h-4 w-4 shrink-0" />
                    <span>{detailQuery.data.error}</span>
                  </div>
                )}

                {/* Logs */}
                {detailQuery.data.logs && detailQuery.data.logs.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                      执行日志
                    </p>
                    <div className="max-h-56 space-y-1 overflow-auto rounded-xl bg-gray-950 p-3 font-mono text-xs text-gray-100 shadow-inner">
                      {detailQuery.data.logs
                        .filter((l) => l.type !== "heartbeat")
                        .map((log, i) => (
                          <div
                            key={i}
                            className={cn(
                              "leading-relaxed",
                              log.level === "error"
                                ? "text-destructive"
                                : log.level === "success"
                                  ? "text-success"
                                  : "text-muted-foreground",
                            )}
                          >
                            {log.message ?? log.content ?? JSON.stringify(log)}
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Result preview */}
                {detailQuery.data.result && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
                        抓取结果
                      </p>
                      <span className="text-muted-foreground text-xs tabular-nums">
                        {detailQuery.data.result.length.toLocaleString()} 字符
                      </span>
                    </div>
                    <div className="bg-muted/20 max-h-72 overflow-auto rounded-xl border p-3 text-sm leading-relaxed whitespace-pre-wrap">
                      {detailQuery.data.result.slice(0, 2000)}
                      {detailQuery.data.result.length > 2000 && (
                        <span className="text-muted-foreground">...</span>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="bg-muted/20 border-t px-5 py-4">
                <div className="flex gap-2">
                  {["completed", "failed"].includes(
                    detailQuery.data.status,
                  ) && (
                    <button
                      onClick={() => {
                        openScrapeDialog({
                          url: detailQuery.data!.url,
                          provider: detailQuery.data!.provider,
                          schema: detailQuery.data!.schema_name,
                        });
                      }}
                      className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-all"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> 调整参数重跑
                    </button>
                  )}
                  {detailQuery.data.status === "completed" &&
                    detailQuery.data.result && (
                      <button
                        onClick={() => draftMutation.mutate(expandedTask)}
                        disabled={draftMutation.isPending}
                        className="hover:bg-muted flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm shadow-sm transition-colors disabled:opacity-50"
                      >
                        {draftMutation.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="h-3.5 w-3.5" />
                        )}
                        保存草稿
                      </button>
                    )}
                  <button
                    onClick={() => rerunMutation.mutate(expandedTask)}
                    disabled={rerunMutation.isPending}
                    className="hover:bg-muted flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm shadow-sm transition-colors disabled:opacity-50"
                  >
                    {rerunMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
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
