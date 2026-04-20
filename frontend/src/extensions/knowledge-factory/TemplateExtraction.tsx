"use client";

import {
  Settings,
  Plus,
  Pause,
  Play,
  X,
  CheckCircle2,
  Loader2,
  Clock,
  ChevronRight,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import React, { useState, useEffect, useCallback, useRef } from "react";

import { kfApi } from "@/extensions/api";

import ExtractionResultModal from "./ExtractionResultModal";
import ExtractionTaskModal from "./ExtractionTaskModal";
import type {
  ExtractionTaskResponse,
  TemplateResult,
  StepStatus,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

const POLL_INTERVAL = 5000; // 5s

function StepRow({ step }: { step: StepStatus }) {
  return (
    <tr>
      <td className="py-3 font-medium text-foreground">{step.name}</td>
      <td className="py-3">
        {step.status === "completed" ? (
          <span className="text-emerald-600 flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" /> 完成
          </span>
        ) : step.status === "running" ? (
          <span className="text-blue-600 flex items-center gap-1">
            <Loader2 className="w-4 h-4 animate-spin" /> 进行中
          </span>
        ) : step.status === "failed" ? (
          <span className="text-red-600 flex items-center gap-1">
            <AlertCircle className="w-4 h-4" /> 失败
          </span>
        ) : (
          <span className="text-muted-foreground flex items-center gap-1">
            <Clock className="w-4 h-4" /> 等待
          </span>
        )}
      </td>
      <td className="py-3 text-muted-foreground tabular-nums">
        {step.duration ?? "-"}
      </td>
      <td className="py-3 text-muted-foreground text-sm">
        {step.detail || "-"}
      </td>
    </tr>
  );
}

export default function TemplateExtraction() {
  const [tasks, setTasks] = useState<ExtractionTaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showResultModal, setShowResultModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState<ExtractionTaskResponse | null>(null);
  const [selectedResult, setSelectedResult] = useState<TemplateResult | null>(null);

  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: number; msg: string; type: "success" | "error" | "info" }[]>([]);
  const toastId = useRef(0);

  const showToast = (msg: string, type: "success" | "error" | "info" = "info") => {
    const id = ++toastId.current;
    setToasts((prev) => [...prev, { id, msg, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  };

  const loadTasks = useCallback(async (pg = page) => {
    setLoading(true);
    try {
      const res = await kfApi.listTasks({ page: pg, limit: pageSize });
      setTasks(res.tasks);
      setTotal(res.total);
    } catch {
      showToast("加载任务列表失败", "error");
    } finally {
      setLoading(false);
    }
  }, [page]);  

  useEffect(() => { loadTasks(page); }, [loadTasks]);

  // 轮询运行中任务
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    const running = tasks.filter((t) => t.status === "running" || t.status === "pending");
    if (running.length > 0 && !pollingRef.current) {
      pollingRef.current = setInterval(async () => {
        for (const task of running) {
          try {
            const fresh = await kfApi.getTask(task.id);
            setTasks((prev) =>
              prev.map((t) => (t.id === task.id ? fresh : t))
            );
            // 如果已完成或失败，停止轮询
            if (fresh.status === "completed" || fresh.status === "failed") {
              setToasts((prev) => [
                ...prev,
                {
                  id: ++toastId.current,
                  msg: fresh.status === "completed"
                    ? `任务"${fresh.name}"已完成`
                    : `任务"${fresh.name}"失败: ${fresh.error}`,
                  type: fresh.status === "completed" ? "success" : "error",
                },
              ]);
            }
          } catch { /* ignore */ }
        }
        // 所有任务都结束，停止轮询
        const stillRunning = tasks.filter((t) => t.status === "running" || t.status === "pending");
        if (stillRunning.length === 0 && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }, POLL_INTERVAL);
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [tasks]);

  const handlePause = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.pauseTask(task.id);
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "paused" } : t));
      showToast("任务已暂停", "success");
    } catch {
      showToast("暂停失败", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.resumeTask(task.id);
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "running" } : t));
      showToast("任务已恢复", "success");
    } catch {
      showToast("恢复失败", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (task: ExtractionTaskResponse) => {
    if (!confirm(`确定取消任务"${task.name}"吗？`)) return;
    setActionLoading(task.id);
    try {
      await kfApi.cancelTask(task.id);
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "failed" } : t));
      showToast("任务已取消", "success");
    } catch {
      showToast("取消失败", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRerun = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      const newTask = await kfApi.rerunTask(task.id);
      setTasks((prev) => [newTask, ...prev.filter((t) => t.id !== task.id)]);
      showToast("新任务已创建", "success");
    } catch {
      showToast("重新运行失败", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewResult = (task: ExtractionTaskResponse) => {
    setSelectedTask(task);
    setSelectedResult(task.result ?? null);
    setShowResultModal(true);
  };

  const handleCreateSuccess = (newTask: ExtractionTaskResponse) => {
    setShowCreateModal(false);
    setTasks((prev) => [newTask, ...prev]);
    showToast("抽取任务已创建", "success");
  };

  const handleExport = (task: ExtractionTaskResponse) => {
    if (!task.result) return;
    const url = kfApi.exportTemplate(task.result.template_id);
    window.open(url, "_blank");
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const statusBadge = (status: ExtractionTaskResponse["status"]) => {
    switch (status) {
      case "completed":
        return (
          <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-100">
            <CheckCircle2 className="w-3.5 h-3.5" /> 完成
          </span>
        );
      case "running":
      case "pending":
        return (
          <span className="flex items-center gap-1.5 text-xs font-medium text-blue-600 bg-blue-50 px-2 py-1 rounded-full border border-blue-100">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {status === "pending" ? "排队中" : "进行中"}
          </span>
        );
      case "paused":
        return (
          <span className="flex items-center gap-1.5 text-xs font-medium text-amber-600 bg-amber-50 px-2 py-1 rounded-full border border-amber-100">
            <Pause className="w-3.5 h-3.5" /> 已暂停
          </span>
        );
      case "failed":
        return (
          <span className="flex items-center gap-1.5 text-xs font-medium text-red-600 bg-red-50 px-2 py-1 rounded-full border border-red-100">
            <AlertCircle className="w-3.5 h-3.5" /> 失败
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
            <Settings className="w-5 h-5 text-primary" />
            模板抽取任务
          </h2>
          <span className="text-sm text-muted-foreground">
            共 {total} 个任务
          </span>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shadow-sm font-medium text-sm"
        >
          <Plus className="w-4 h-4" />
          新建抽取任务
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-muted/30">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            加载中...
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Settings className="w-12 h-12 mb-3 opacity-30" />
            <p>暂无抽取任务</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-3 text-primary hover:underline text-sm"
            >
              创建第一个任务
            </button>
          </div>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              className="bg-card rounded-xl border border-border shadow-sm hover:shadow-md transition-all overflow-hidden"
            >
              {/* Card header */}
              <div className="p-5 border-b border-border bg-muted/50">
                <div className="flex justify-between items-start mb-4 gap-4">
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-mono text-muted-foreground">
                        {task.id.slice(0, 8)}...
                      </span>
                      {statusBadge(task.status)}
                    </div>
                    <h4 className="font-medium text-foreground truncate">
                      {task.name || "未命名任务"}
                    </h4>
                    <p className="text-sm text-muted-foreground truncate">
                      源报告: {task.source_reports?.join(" + ") || "-"}
                    </p>
                    {task.error && (
                      <p className="text-sm text-red-600 flex items-center gap-1">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        {task.error}
                      </p>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-1 shrink-0">
                    {task.status === "running" || task.status === "pending" ? (
                      <>
                        <button
                          disabled={actionLoading === task.id}
                          onClick={() => handlePause(task)}
                          title="暂停"
                          className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                        >
                          <Pause className="w-4 h-4" />
                        </button>
                        <button
                          disabled={actionLoading === task.id}
                          onClick={() => handleCancel(task)}
                          title="取消"
                          className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </>
                    ) : task.status === "paused" ? (
                      <>
                        <button
                          disabled={actionLoading === task.id}
                          onClick={() => handleResume(task)}
                          title="恢复"
                          className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                        <button
                          disabled={actionLoading === task.id}
                          onClick={() => handleCancel(task)}
                          title="取消"
                          className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </>
                    ) : task.status === "failed" ? (
                      <button
                        disabled={actionLoading === task.id}
                        onClick={() => handleRerun(task)}
                        title="重新运行"
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors disabled:opacity-50"
                      >
                        <RefreshCw className="w-4 h-4" /> 重新运行
                      </button>
                    ) : task.status === "completed" ? (
                      <>
                        <button
                          disabled={actionLoading === task.id}
                          onClick={() => handleRerun(task)}
                          title="重新运行"
                          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          <RefreshCw className="w-4 h-4" /> 重试
                        </button>
                        {task.result && (
                          <button
                            onClick={() => handleExport(task)}
                            className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                          >
                            导出
                          </button>
                        )}
                      </>
                    ) : null}
                  </div>
                </div>

                {/* Progress bar */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">进度: {task.progress}%</span>
                    {task.status === "running" && (
                      <span className="text-primary animate-pulse">处理中...</span>
                    )}
                  </div>
                  <div className="w-full bg-muted rounded-full h-2.5">
                    <div
                      className={cn(
                        "h-2.5 rounded-full transition-all duration-500",
                        task.status === "completed" ? "bg-emerald-500" :
                        task.status === "failed" ? "bg-red-500" : "bg-indigo-600"
                      )}
                      style={{ width: `${task.progress}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Steps table (running/paused) */}
              {(task.status === "running" || task.status === "pending" || task.status === "paused") &&
                task.steps?.length > 0 && (
                  <div className="p-5">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-muted-foreground border-b border-border text-left">
                          <th className="pb-3 font-medium">阶段</th>
                          <th className="pb-3 font-medium">状态</th>
                          <th className="pb-3 font-medium">耗时</th>
                          <th className="pb-3 font-medium">详情</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {task.steps.map((step, idx) => (
                          <StepRow key={idx} step={step} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

              {/* Result footer (completed) */}
              {task.status === "completed" && task.result && (
                <div className="px-5 py-4 flex justify-between items-center bg-emerald-50/30">
                  <div className="text-sm">
                    <span className="text-muted-foreground">生成模板: </span>
                    <span className="font-medium text-emerald-700">
                      {task.result.name} {task.result.version} ({task.result.chapters}章/{task.result.sections}节) 完整度 {task.result.completeness_score}%
                    </span>
                  </div>
                  <button
                    onClick={() => handleViewResult(task)}
                    className="flex items-center gap-1 text-primary hover:text-primary/70 hover:underline text-sm font-medium transition-colors"
                  >
                    查看结果 <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* Time info */}
              <div className="px-5 py-2 bg-muted/30 border-t border-border flex justify-between text-xs text-muted-foreground">
                <span>创建: {new Date(task.created_at).toLocaleString("zh-CN")}</span>
                {task.completed_at && (
                  <span>完成: {new Date(task.completed_at).toLocaleString("zh-CN")}</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="shrink-0 flex items-center justify-between px-6 py-3 border-t border-border bg-card">
          <span className="text-sm text-muted-foreground">
            第 {page} / {totalPages} 页，共 {total} 个任务
          </span>
          <div className="flex items-center gap-2">
            <button
              disabled={page === 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              上一页
            </button>
            <button
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      {/* Modals */}
      {showCreateModal && (
        <ExtractionTaskModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={handleCreateSuccess}
          onToast={showToast}
        />
      )}

      {showResultModal && selectedTask && (
        <ExtractionResultModal
          task={selectedTask}
          result={selectedResult}
          onClose={() => { setShowResultModal(false); setSelectedTask(null); }}
          onExport={() => selectedResult && handleExport(selectedTask)}
        />
      )}

      {/* Toast notifications */}
      <div className="fixed right-6 bottom-6 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg",
              t.type === "success" && "border-emerald-200 bg-emerald-50 text-emerald-800",
              t.type === "error" && "border-red-200 bg-red-50 text-red-800",
              t.type === "info" && "border-blue-200 bg-blue-50 text-blue-800"
            )}
          >
            {t.type === "success" && <CheckCircle2 className="w-4 h-4 shrink-0" />}
            {t.type === "error" && <AlertCircle className="w-4 h-4 shrink-0" />}
            {t.type === "info" && <Loader2 className="w-4 h-4 shrink-0 animate-spin" />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
