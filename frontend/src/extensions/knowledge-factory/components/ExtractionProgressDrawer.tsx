"use client";

import {
  X,
  CheckCircle2,
  Loader2,
  AlertCircle,
  RefreshCw,
  ChevronRight,
  Settings,
} from "lucide-react";
import React, { useState, useEffect, useCallback, useRef } from "react";

import { kfApi } from "@/extensions/api";
import type { ExtractionTaskResponse, TemplateResult } from "@/extensions/knowledge-factory/types";
import ExtractionResultModal from "@/extensions/knowledge-factory/ExtractionResultModal";
import { cn } from "@/lib/utils";

const POLL_INTERVAL = 5000;

interface ExtractionProgressDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  reportId?: string;
}

export default function ExtractionProgressDrawer({
  isOpen,
  onClose,
  reportId,
}: ExtractionProgressDrawerProps) {
  const [tasks, setTasks] = useState<ExtractionTaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showResultModal, setShowResultModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState<ExtractionTaskResponse | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 加载与当前报告相关的任务
  const loadRelatedTasks = useCallback(async () => {
    try {
      const res = await kfApi.listTasks({ limit: 50 });
      // 过滤出与当前报告相关的任务
      const related = reportId
        ? res.tasks.filter((t) => t.source_reports?.includes(reportId))
        : res.tasks.filter((t) => t.status === "running" || t.status === "pending");
      setTasks(related);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    if (isOpen) {
      loadRelatedTasks();
    }
  }, [isOpen, loadRelatedTasks]);

  // 轮询运行中任务
  useEffect(() => {
    const running = tasks.filter((t) => t.status === "running" || t.status === "pending");
    if (running.length > 0 && !pollingRef.current) {
      pollingRef.current = setInterval(() => {
        loadRelatedTasks();
      }, POLL_INTERVAL);
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [tasks, loadRelatedTasks]);

  const handlePause = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.pauseTask(task.id);
      await loadRelatedTasks();
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async (task: ExtractionTaskResponse) => {
    setActionLoading(task.id);
    try {
      await kfApi.resumeTask(task.id);
      await loadRelatedTasks();
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (task: ExtractionTaskResponse) => {
    if (!confirm(`确定取消任务"${task.name}"吗？`)) return;
    setActionLoading(task.id);
    try {
      await kfApi.cancelTask(task.id);
      await loadRelatedTasks();
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewResult = (task: ExtractionTaskResponse) => {
    setSelectedTask(task);
    setShowResultModal(true);
  };

  if (!isOpen) return null;

  const runningTasks = tasks.filter((t) => t.status === "running" || t.status === "pending");
  const completedTasks = tasks.filter((t) => t.status === "completed");
  const failedTasks = tasks.filter((t) => t.status === "failed" || t.status === "paused");

  return (
    <>
      {/* 遮罩 */}
      <div className="fixed inset-0 z-40" onClick={onClose} />

      {/* 抽屉 */}
      <div className="fixed right-0 top-0 bottom-0 w-96 bg-background shadow-2xl z-50 flex flex-col animate-in slide-in-from-right">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/50">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-primary" />
            <span className="font-medium text-sm text-foreground">抽取进度</span>
            {runningTasks.length > 0 && (
              <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                {runningTasks.length} 进行中
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-accent rounded transition-colors"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              <Settings className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>暂无抽取任务</p>
              <p className="text-xs text-muted-foreground mt-1">在报告中点击&quot;提取模板&quot;开始抽取</p>
            </div>
          ) : (
            <>
              {/* 运行中的任务 */}
              {runningTasks.map((task) => (
                <div key={task.id} className="bg-primary/5 border border-primary/10 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-foreground truncate">
                      {task.name || "抽取任务"}
                    </span>
                    <div className="flex gap-1">
                      <button
                        disabled={actionLoading === task.id}
                        onClick={() => handlePause(task)}
                        className="p-1 hover:bg-accent rounded transition-colors"
                        title="暂停"
                      >
                        <svg className="w-3.5 h-3.5 text-primary" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                        </svg>
                      </button>
                      <button
                        disabled={actionLoading === task.id}
                        onClick={() => handleCancel(task)}
                        className="p-1 hover:bg-destructive/10 rounded transition-colors"
                        title="取消"
                      >
                        <X className="w-3.5 h-3.5 text-destructive" />
                      </button>
                    </div>
                  </div>
                  {/* 进度条 */}
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-muted-foreground mb-1">
                      <span>{task.progress}%</span>
                      <span className="text-primary animate-pulse">处理中</span>
                    </div>
                    <div className="w-full bg-primary/10 rounded-full h-1.5">
                      <div
                        className="bg-primary h-1.5 rounded-full transition-all"
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                  {/* 步骤 */}
                  {task.steps?.length > 0 && (
                    <div className="space-y-1 mt-2">
                      {task.steps.slice(-3).map((step, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs">
                          {step.status === "completed" ? (
                            <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                          ) : step.status === "running" ? (
                            <Loader2 className="w-3 h-3 text-primary animate-spin" />
                          ) : step.status === "failed" ? (
                            <AlertCircle className="w-3 h-3 text-red-500" />
                          ) : (
                            <div className="w-3 h-3 rounded-full border border-border" />
                          )}
                          <span className={cn(
                            step.status === "completed" && "text-emerald-500",
                            step.status === "running" && "text-primary",
                            step.status === "failed" && "text-red-500",
                            step.status === "waiting" && "text-muted-foreground"
                          )}>
                            {step.name}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {/* 失败的任务 */}
              {failedTasks.map((task) => (
                <div key={task.id} className="bg-destructive/5 border border-destructive/10 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <span className="text-sm font-medium text-foreground truncate block">
                        {task.name || "抽取任务"}
                      </span>
                      {task.error && (
                        <p className="text-xs text-destructive mt-1 truncate">{task.error}</p>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button
                        disabled={actionLoading === task.id}
                        onClick={async () => {
                          setActionLoading(task.id);
                          try {
                            await kfApi.rerunTask(task.id);
                            await loadRelatedTasks();
                          } finally {
                            setActionLoading(null);
                          }
                        }}
                        className="p-1 hover:bg-accent rounded transition-colors"
                        title="重新运行"
                      >
                        <RefreshCw className="w-3.5 h-3.5 text-primary" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}

              {/* 已完成的任务 */}
              {completedTasks.map((task) => (
                <div key={task.id} className="bg-emerald-500/5 border border-emerald-500/10 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        <span className="text-sm font-medium text-foreground truncate">
                          {task.name || "抽取任务"}
                        </span>
                      </div>
                      {task.result && (
                        <p className="text-xs text-emerald-500 mt-1">
                          {task.result.name} {task.result.version}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={() => handleViewResult(task)}
                      className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 shrink-0"
                    >
                      查看 <ChevronRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* Footer */}
        {tasks.length > 0 && (
          <div className="px-4 py-3 border-t border-border bg-muted/50">
            <button
              onClick={() => window.location.href = "/knowledge-factory?tab=extraction"}
              className="w-full text-xs text-primary hover:text-primary/80 hover:underline"
            >
              查看全部任务
            </button>
          </div>
        )}
      </div>

      {/* 结果详情弹窗 */}
      {showResultModal && selectedTask && (
        <ExtractionResultModal
          task={selectedTask}
          result={selectedTask.result ?? null}
          onClose={() => {
            setShowResultModal(false);
            setSelectedTask(null);
          }}
          onExport={() => {
            if (selectedTask.result) {
              const url = kfApi.exportTemplate(selectedTask.result.template_id);
              window.open(url, "_blank");
            }
          }}
        />
      )}
    </>
  );
}
