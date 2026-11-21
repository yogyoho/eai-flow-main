"use client";

import {
  X,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Loader2,
  RefreshCw,
  Database,
  FileText,
  Activity,
  FolderCheck,
  FolderX,
  CircleAlert,
} from "lucide-react";
import React, { useState } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { LawType } from "@/extensions/knowledge-factory/types";

import { LAW_CATEGORIES } from "../config/lawCategories";
import { useRAGFlowStatus, useInitRAGFlow } from "../hooks/useLawLibrary";
import { cn } from "../utils";

interface RAGFlowStatusPanelProps {
  onClose: () => void;
}

export default function RAGFlowStatusPanel({
  onClose,
}: RAGFlowStatusPanelProps) {
  const { data, isLoading, error, refetch, isFetching } = useRAGFlowStatus();
  const initMutation = useInitRAGFlow();
  const [initType, setInitType] = useState<string>("all");

  const handleInit = async () => {
    await initMutation.mutateAsync(
      initType === "all" ? undefined : (initType as LawType),
    );
  };

  const statusMap = new Map(data?.statuses?.map((s) => [s.type, s]) ?? []);

  const healthyCount = data?.healthy_kbs ?? 0;
  const missingCount = data?.missing_kbs ?? 0;
  const errorCount = data?.error_kbs ?? 0;
  const totalCount = data?.total_kbs ?? 0;
  const healthyPercent =
    totalCount > 0 ? Math.round((healthyCount / totalCount) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-card border-border/50 flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="from-primary/20 to-primary/5 text-primary flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-foreground text-lg font-semibold">
                RAG 知识库状态
              </h3>
              <p className="text-muted-foreground mt-0.5 text-xs">
                查看和管理法规知识库的同步状态
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="hover:bg-accent text-muted-foreground hover:text-foreground rounded-xl p-2 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {/* Summary Cards */}
          {data && (
            <div className="space-y-4">
              {/* Health Progress Bar */}
              <div className="border-border/50 from-card to-card/80 rounded-xl border bg-gradient-to-br p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-foreground flex items-center gap-2 text-sm font-medium">
                    <Activity className="text-primary h-4 w-4" />
                    总体健康度
                  </div>
                  <span
                    className={cn(
                      "text-sm font-bold tabular-nums",
                      healthyPercent >= 80
                        ? "text-success"
                        : healthyPercent >= 50
                          ? "text-warning"
                          : "text-destructive",
                    )}
                  >
                    {healthyPercent}%
                  </span>
                </div>
                <div className="bg-muted h-2.5 overflow-hidden rounded-full">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-700",
                      healthyPercent >= 80
                        ? "from-success to-success/70 bg-gradient-to-r"
                        : healthyPercent >= 50
                          ? "from-warning to-warning/70 bg-gradient-to-r"
                          : "from-destructive to-destructive/70 bg-gradient-to-r",
                    )}
                    style={{ width: `${healthyPercent}%` }}
                  />
                </div>
              </div>

              {/* Stat Cards */}
              <div className="grid grid-cols-4 gap-3">
                <div className="border-border/50 from-card to-card/80 flex items-center gap-3 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
                  <div className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <Database className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-foreground text-xl font-bold tabular-nums">
                      {totalCount}
                    </div>
                    <div className="text-muted-foreground text-xs font-medium">
                      知识库总数
                    </div>
                  </div>
                </div>
                <div className="border-success/20 from-card to-success/5 flex items-center gap-3 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
                  <div className="bg-success/10 text-success flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <FolderCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-success text-xl font-bold tabular-nums">
                      {healthyCount}
                    </div>
                    <div className="text-muted-foreground text-xs font-medium">
                      正常运行
                    </div>
                  </div>
                </div>
                <div className="border-warning/20 from-card to-warning/5 flex items-center gap-3 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
                  <div className="bg-warning/10 text-warning flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <FolderX className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-warning text-xl font-bold tabular-nums">
                      {missingCount}
                    </div>
                    <div className="text-muted-foreground text-xs font-medium">
                      未创建
                    </div>
                  </div>
                </div>
                <div className="border-destructive/20 from-card to-destructive/5 flex items-center gap-3 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
                  <div className="bg-destructive/10 text-destructive flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <CircleAlert className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="text-destructive text-xl font-bold tabular-nums">
                      {errorCount}
                    </div>
                    <div className="text-muted-foreground text-xs font-medium">
                      异常
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Loading State */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-2xl">
                <Loader2 className="text-primary h-6 w-6 animate-spin" />
              </div>
              <span className="text-muted-foreground text-sm">
                正在获取知识库状态...
              </span>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-destructive/10 border-destructive/20 flex items-center gap-3 rounded-xl border p-4">
              <div className="bg-destructive/10 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
                <AlertTriangle className="text-destructive h-4 w-4" />
              </div>
              <span className="text-destructive text-sm">{error.message}</span>
            </div>
          )}

          {/* Knowledge Base List */}
          {data && !isLoading && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h4 className="text-foreground text-sm font-semibold">
                  知识库详情
                </h4>
                <span className="text-muted-foreground bg-muted rounded-full px-2 py-0.5 text-xs">
                  {LAW_CATEGORIES.length} 个
                </span>
              </div>
              <div className="space-y-2">
                {LAW_CATEGORIES.map((cat) => {
                  const status = statusMap.get(cat.code);
                  const isHealthy = status?.status === "healthy";
                  const isMissing = status?.status === "missing";
                  const isError = status?.status === "error";

                  return (
                    <div
                      key={cat.code}
                      className={cn(
                        "flex items-center justify-between rounded-xl border p-4 transition-all hover:shadow-sm",
                        isHealthy
                          ? "from-card to-success/5 border-success/20 hover:border-success/30 bg-gradient-to-r"
                          : isError
                            ? "from-card to-destructive/5 border-destructive/20 hover:border-destructive/30 bg-gradient-to-r"
                            : "from-card to-warning/5 border-warning/20 hover:border-warning/30 bg-gradient-to-r",
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-xl",
                            cat.bgColor,
                          )}
                        >
                          <cat.icon className={cn("h-5 w-5", cat.color)} />
                        </div>
                        <div>
                          <div className="text-foreground text-sm font-medium">
                            {cat.name}
                          </div>
                          <div className="text-muted-foreground mt-0.5 font-mono text-xs">
                            {cat.ragflowKbName}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        {status?.document_count !== undefined && (
                          <div className="text-muted-foreground bg-muted/50 flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs">
                            <FileText className="h-3.5 w-3.5" />
                            <span className="font-medium tabular-nums">
                              {status.document_count}
                            </span>{" "}
                            份
                          </div>
                        )}

                        {isHealthy && (
                          <span className="bg-success/10 text-success inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium">
                            <CheckCircle className="h-3.5 w-3.5" /> 正常
                          </span>
                        )}

                        {isMissing && (
                          <span className="bg-warning/10 text-warning inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium">
                            <AlertCircle className="h-3.5 w-3.5" /> 未创建
                          </span>
                        )}

                        {isError && (
                          <span className="bg-destructive/10 text-destructive inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium">
                            <AlertTriangle className="h-3.5 w-3.5" />{" "}
                            {status?.error_message ?? "错误"}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Init Result */}
        {initMutation.data && (
          <div className="border-success/20 bg-success/5 border-t px-6 py-3">
            <div className="text-success flex items-center gap-2 text-sm">
              <CheckCircle className="h-4 w-4 shrink-0" />
              <span>
                {initMutation.data.created?.length > 0 && (
                  <span className="font-medium">
                    已创建 {initMutation.data.created.length} 个知识库
                  </span>
                )}
                {initMutation.data.aligned?.length > 0 && (
                  <span className="text-muted-foreground">
                    ，{initMutation.data.aligned.length} 个配置一致
                  </span>
                )}
                {initMutation.data.updated?.length > 0 && (
                  <span className="text-amber-600 dark:text-amber-400">
                    ，{initMutation.data.updated.length} 个已收敛到标准配置
                  </span>
                )}
                {initMutation.data.failed?.length > 0 && (
                  <span className="text-destructive font-medium">
                    ，{initMutation.data.failed.length} 个失败
                  </span>
                )}
              </span>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="border-border bg-muted/30 flex shrink-0 items-center justify-between gap-4 border-t px-6 py-4">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Select value={initType} onValueChange={setInitType}>
              <SelectTrigger
                size="default"
                className="border-border bg-card hover:border-primary/30 hover:bg-accent/40 focus-visible:border-primary data-[state=open]:border-primary data-[state=open]:ring-primary/15 h-10 max-w-full min-w-[13.5rem] rounded-lg shadow-sm data-[state=open]:ring-2"
              >
                <Database className="text-muted-foreground size-4 shrink-0" />
                <SelectValue placeholder="选择要初始化的知识库" />
              </SelectTrigger>
              <SelectContent
                position="popper"
                side="top"
                sideOffset={8}
                align="start"
                className="border-border z-[200] max-h-64 min-w-[var(--radix-select-trigger-width)] rounded-xl p-1.5 shadow-lg"
              >
                <SelectItem
                  value="all"
                  className="data-[highlighted]:bg-accent data-[state=checked]:bg-primary/10 data-[state=checked]:text-foreground cursor-pointer rounded-lg py-2.5 pr-8 pl-3 text-sm"
                >
                  全部知识库
                </SelectItem>
                {LAW_CATEGORIES.map((cat) => (
                  <SelectItem
                    key={cat.code}
                    value={cat.code}
                    className="data-[highlighted]:bg-accent data-[state=checked]:bg-primary/10 data-[state=checked]:text-foreground cursor-pointer rounded-lg py-2.5 pr-8 pl-3 text-sm"
                  >
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              onClick={handleInit}
              disabled={initMutation.isPending}
              className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium shadow-sm transition-colors disabled:opacity-50"
            >
              {initMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              初始化知识库
            </button>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="border-border hover:bg-accent text-muted-foreground hover:text-foreground flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors"
          >
            {isFetching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            刷新
          </button>
        </div>
      </div>
    </div>
  );
}
