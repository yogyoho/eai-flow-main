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
  ChevronDown,
  AlertCircle,
  RefreshCw,
  Download,
  Trash2,
} from "lucide-react";
import React, { useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";

import { kfApi } from "@/extensions/api";
import type {
  ExtractionTaskResponse,
  TemplateResult,
  StepStatus,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import ExtractionResultModal from "./ExtractionResultModal";
import ExtractionTaskModal from "./ExtractionTaskModal";

const POLL_INTERVAL = 5000;

const STATUS_TABS = [
  { key: "", label: "全部" },
  { key: "running", label: "运行中" },
  { key: "completed", label: "已完成" },
  { key: "failed", label: "失败" },
  { key: "paused", label: "已暂停" },
] as const;

function StepRow({ step }: { step: StepStatus }) {
  return (
    <tr className="align-middle">
      <td className="py-2.5 font-medium text-foreground text-sm align-middle">{step.name}</td>
      <td className="py-2.5 align-middle">
        {step.status === "completed" ? (
          <span className="inline-flex items-center gap-1 text-success text-xs">
            <CheckCircle2 className="w-3.5 h-3.5" /> 完成
          </span>
        ) : step.status === "running" ? (
          <span className="inline-flex items-center gap-1 text-primary text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> 进行中
          </span>
        ) : step.status === "failed" ? (
          <span className="inline-flex items-center gap-1 text-destructive text-xs">
            <AlertCircle className="w-3.5 h-3.5" /> 失败
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-muted-foreground text-xs">
            <Clock className="w-3.5 h-3.5" /> 等待
          </span>
        )}
      </td>
      <td className="py-2.5 text-muted-foreground tabular-nums text-xs align-middle">{step.duration ?? "-"}</td>
      <td className="py-2.5 text-muted-foreground text-xs align-middle">{step.detail || "-"}</td>
    </tr>
  );
}

export default function TemplateExtraction() {
  const [tasks, setTasks] = useState<ExtractionTaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const pageSize = 20;

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showResultModal, setShowResultModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState<ExtractionTaskResponse | null>(null);
  const [selectedResult, setSelectedResult] = useState<TemplateResult | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ action: () => Promise<void>; title: string; message: string } | null>(null);
  const tasksRef = useRef<ExtractionTaskResponse[]>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 保持 ref 与 state 同步
  useEffect(() => { tasksRef.current = tasks; }, [tasks]);

  const loadTasks = useCallback(async (pg: number, filter: string) => {
    setLoading(true);
    try {
      const params: { page: number; limit: number; status?: string } = { page: pg, limit: pageSize };
      if (filter) params.status = filter;
      const res = await kfApi.listTasks(params);
      setTasks(res.tasks);
      setTotal(res.total);
    } catch {
      toast.error("加载任务列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // 初始加载 + 翻页/筛选变化
  useEffect(() => { void loadTasks(page, statusFilter); }, [page, statusFilter, loadTasks]);

  // 轮询：用 ref 避免闭包陷阱
  useEffect(() => {
    const hasRunning = tasks.some((t) => t.status === "running" || t.status === "pending");
    if (hasRunning && !pollingRef.current) {
      pollingRef.current = setInterval(() => {
        void (async () => {
        const current = tasksRef.current;
        const running = current.filter((t) => t.status === "running" || t.status === "pending");
        if (running.length === 0) {
          if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
          return;
        }
        for (const task of running) {
          try {
            const fresh = await kfApi.getTask(task.id);
            setTasks((prev) => prev.map((t) => (t.id === task.id ? fresh : t)));
            if (fresh.status === "completed" || fresh.status === "failed") {
              const msg = fresh.status === "completed"
                ? `任务"${fresh.name}"已完成`
                : `任务"${fresh.name}"失败: ${fresh.error ?? ""}`;
              toast[fresh.status === "completed" ? "success" : "error"](msg);
            }
          } catch { /* ignore */ }
        }
        // 重新检查是否还有运行中的任务
        const stillRunning = tasksRef.current.some((t) => t.status === "running" || t.status === "pending");
        if (!stillRunning && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        })();
      }, POLL_INTERVAL);
    }
    if (!hasRunning && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    };
  }, [tasks]);

  const handlePause = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.pauseTask(task.id);
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "paused" as const } : t));
      toast.success("任务已暂停");
    } catch {
      toast.error("暂停失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.resumeTask(task.id);
      setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "running" as const } : t));
      toast.success("任务已恢复");
    } catch {
      toast.error("恢复失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (task: ExtractionTaskResponse) => {
    setConfirmTarget({
      title: "确认取消",
      message: `确定取消任务"${task.name}"吗？`,
      action: async () => {
        setActionLoading(task.id);
        try {
          await kfApi.cancelTask(task.id);
          setTasks((prev) => prev.map((t) => t.id === task.id ? { ...t, status: "failed" as const } : t));
          toast.success("任务已取消");
        } catch {
          toast.error("取消失败");
        } finally {
          setActionLoading(null);
        }
      },
    });
  };

  const handleRerun = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      const newTask = await kfApi.rerunTask(task.id);
      setTasks((prev) => [newTask, ...prev.filter((t) => t.id !== task.id)]);
      toast.success("新任务已创建");
    } catch {
      toast.error("重新运行失败");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (task: ExtractionTaskResponse) => {
    setConfirmTarget({
      title: "确认删除",
      message: `确定删除任务"${task.name ?? "未命名任务"}"吗？此操作不可撤销。`,
      action: async () => {
        setActionLoading(task.id);
        try {
          await kfApi.deleteTask(task.id);
          setTasks((prev) => prev.filter((t) => t.id !== task.id));
          setTotal((prev) => Math.max(0, prev - 1));
          toast.success("任务已删除");
        } catch {
          toast.error("删除失败");
        } finally {
          setActionLoading(null);
        }
      },
    });
  };

  const handleClearHistory = async () => {
    const terminalTasks = tasks.filter((t) => t.status === "completed" || t.status === "failed");
    if (terminalTasks.length === 0) {
      toast.info("没有可清除的历史任务");
      return;
    }
    setConfirmTarget({
      title: "确认清除",
      message: "确定清除所有已完成和失败的任务吗？此操作不可撤销。",
      action: async () => {
        setActionLoading("__clear__");
        try {
          const res = await kfApi.clearTasks();
          toast.success(res.message);
          void loadTasks(1, statusFilter);
          setPage(1);
        } catch {
          toast.error("清除失败");
        } finally {
          setActionLoading(null);
        }
      },
    });
  };

  const handleViewResult = (task: ExtractionTaskResponse) => {
    setSelectedTask(task);
    setSelectedResult(task.result ?? null);
    setShowResultModal(true);
  };

  const handleCreateSuccess = (newTask: ExtractionTaskResponse) => {
    setShowCreateModal(false);
    setTasks((prev) => [newTask, ...prev]);
    toast.success("抽取任务已创建");
  };

  const handleExport = (task: ExtractionTaskResponse) => {
    if (!task.result?.template_id) return;
    window.open(kfApi.exportTemplate(task.result.template_id), "_blank");
  };

  const toggleSteps = (taskId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
      return next;
    });
  };

  const handleFilterChange = (f: string) => {
    setStatusFilter(f);
    setPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const statusBadge = (status: ExtractionTaskResponse["status"]) => {
    switch (status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-success bg-success/10 px-2 py-0.5 rounded-full border border-success/20">
            <CheckCircle2 className="w-3 h-3" /> 完成
          </span>
        );
      case "running":
      case "pending":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20">
            <Loader2 className="w-3 h-3 animate-spin" /> {status === "pending" ? "排队中" : "进行中"}
          </span>
        );
      case "paused":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-warning bg-warning/10 px-2 py-0.5 rounded-full border border-warning/20">
            <Pause className="w-3 h-3" /> 已暂停
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive bg-destructive/10 px-2 py-0.5 rounded-full border border-destructive/20">
            <AlertCircle className="w-3 h-3" /> 失败
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center px-6 py-4 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-medium flex items-center gap-2 text-foreground tracking-tight">
            <Settings className="w-5 h-5 text-primary" />
            模板抽取任务
          </h2>
          <span className="text-sm text-muted-foreground">共 {total} 个任务</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleClearHistory}
            disabled={actionLoading === "__clear__"}
            className="flex items-center gap-2 px-3 py-2 border border-border text-muted-foreground rounded-lg hover:text-destructive hover:border-destructive/50 hover:bg-destructive/5 transition-colors text-sm disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
            {actionLoading === "__clear__" ? "清除中..." : "清除历史"}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors shadow-sm font-medium text-sm"
          >
            <Plus className="w-4 h-4" />
            新建抽取任务
          </button>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="flex items-center gap-1 px-6 py-2.5 border-b border-border bg-card shrink-0">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleFilterChange(tab.key)}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              statusFilter === tab.key
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-muted/30">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> 加载中...
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
            <Settings className="w-12 h-12 mb-3 opacity-30" />
            <p>暂无抽取任务</p>
            <button onClick={() => setShowCreateModal(true)} className="mt-3 text-primary hover:underline text-sm">
              创建第一个任务
            </button>
          </div>
        ) : (
          tasks.map((task) => {
            const isTerminal = task.status === "completed" || task.status === "failed";
            const stepsExpanded = expandedSteps.has(task.id) || !isTerminal;

            return (
              <div key={task.id} className={cn(
                "bg-card rounded-xl border border-border/50 shadow-sm overflow-hidden border-l-[3px] transition-shadow hover:shadow-md",
                task.status === "completed" && "border-l-success/60",
                (task.status === "running" || task.status === "pending") && "border-l-primary/60",
                task.status === "paused" && "border-l-warning/60",
                task.status === "failed" && "border-l-destructive/60"
              )}>
                {/* Card top: info + actions */}
                <div className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="font-medium text-sm text-foreground truncate">{task.name ?? "未命名任务"}</h4>
                        {statusBadge(task.status)}
                        <span className="text-[10px] font-mono text-muted-foreground/50">{task.id.slice(0, 8)}</span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        源报告: {task.source_reports && task.source_reports.length > 0
                          ? task.source_reports.join(" + ")
                          : "-"}
                      </p>
                      {task.error && (
                        <p className="text-xs text-destructive flex items-center gap-1">
                          <AlertCircle className="w-3 h-3 shrink-0" /> {task.error}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {(task.status === "running" || task.status === "pending") && (
                        <>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handlePause(task)}
                            title="暂停"
                            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                          >
                            <Pause className="w-4 h-4" />
                          </button>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleCancel(task)}
                            title="取消"
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {task.status === "paused" && (
                        <>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleResume(task)}
                            title="恢复"
                            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleCancel(task)}
                            title="取消"
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <X className="w-4 h-4" />
                          </button>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleDelete(task)}
                            title="删除"
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {task.status === "failed" && (
                        <>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleRerun(task)}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <RefreshCw className="w-3.5 h-3.5" /> 重新运行
                          </button>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleDelete(task)}
                            title="删除"
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {task.status === "completed" && task.result && (
                        <>
                          <button
                            onClick={() => handleViewResult(task)}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                          >
                            <ChevronRight className="w-3.5 h-3.5" /> 查看结果
                          </button>
                          <button
                            onClick={() => handleExport(task)}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" /> 导出
                          </button>
                          <button
                            disabled={actionLoading === task.id}
                            onClick={() => handleDelete(task)}
                            title="删除"
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Progress bar (running/pending) */}
                  {(task.status === "running" || task.status === "pending") && (
                    <div className="mt-3 space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">进度: {task.progress}%</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-2">
                        <div
                          className="h-2 rounded-full bg-gradient-to-r from-primary to-primary/70 transition-all duration-500"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Completed result summary */}
                  {task.status === "completed" && task.result && (
                    <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        模板: <span className="font-medium text-foreground">{task.result.name} {task.result.version}</span>
                      </span>
                      <span>{task.result.chapters}章 / {task.result.sections}节</span>
                      <span>完整度: <span className={cn("font-medium", (task.result.completeness_score ?? 0) >= 80 ? "text-success" : (task.result.completeness_score ?? 0) >= 60 ? "text-info" : "text-warning")}>{task.result.completeness_score}%</span></span>
                    </div>
                  )}
                </div>

                {/* Steps table — always visible, collapsed for terminal states by default */}
                {task.steps && task.steps.length > 0 && (
                  <div className="border-t border-border">
                    {isTerminal && (
                      <button
                        onClick={() => toggleSteps(task.id)}
                        className="flex items-center gap-1.5 w-full px-4 py-2 text-xs text-muted-foreground hover:bg-muted/50 transition-colors"
                      >
                        {stepsExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        步骤详情
                      </button>
                    )}
                    {stepsExpanded && (
                      <div className="px-4 pb-3">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-muted-foreground border-b border-border text-left align-middle">
                              <th className="pb-2 font-medium text-xs align-middle">阶段</th>
                              <th className="pb-2 font-medium text-xs align-middle">状态</th>
                              <th className="pb-2 font-medium text-xs align-middle">耗时</th>
                              <th className="pb-2 font-medium text-xs align-middle">详情</th>
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
                  </div>
                )}

                {/* Time footer */}
                <div className="px-4 py-2 bg-gradient-to-r from-muted/40 to-muted/20 border-t border-border/40 flex justify-between text-xs text-muted-foreground">
                  <span>创建: {new Date(task.created_at).toLocaleString("zh-CN")}</span>
                  {task.completed_at && (
                    <span>完成: {new Date(task.completed_at).toLocaleString("zh-CN")}</span>
                  )}
                </div>
              </div>
            );
          })
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

      {/* Confirmation Modal */}
      {confirmTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background rounded-2xl shadow-2xl w-full max-w-sm flex flex-col">
            <div className="px-6 py-5 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <AlertCircle className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-1">{confirmTarget.title}</h3>
              <p className="text-sm text-muted-foreground">{confirmTarget.message}</p>
            </div>
            <div className="flex justify-center gap-3 px-6 py-4 border-t border-border">
              <button
                onClick={() => setConfirmTarget(null)}
                className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  const action = confirmTarget.action;
                  setConfirmTarget(null);
                  await action();
                }}
                className="px-4 py-2 bg-destructive text-white rounded-lg text-sm font-medium hover:bg-destructive/90 transition-colors"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
