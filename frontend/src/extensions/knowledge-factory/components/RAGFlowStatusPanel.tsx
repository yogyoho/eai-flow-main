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

export default function RAGFlowStatusPanel({ onClose }: RAGFlowStatusPanelProps) {
  const { data, isLoading, error, refetch, isFetching } = useRAGFlowStatus();
  const initMutation = useInitRAGFlow();
  const [initType, setInitType] = useState<string>("all");

  const handleInit = async () => {
    await initMutation.mutateAsync(initType === "all" ? undefined : (initType as LawType));
  };

  const statusMap = new Map(data?.statuses?.map((s) => [s.type, s]) ?? []);

  const healthyCount = data?.healthy_kbs ?? 0;
  const missingCount = data?.missing_kbs ?? 0;
  const errorCount = data?.error_kbs ?? 0;
  const totalCount = data?.total_kbs ?? 0;
  const healthyPercent = totalCount > 0 ? Math.round((healthyCount / totalCount) * 100) : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-card rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col border border-border/50"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">RAGFlow 知识库状态</h3>
              <p className="text-xs text-muted-foreground mt-0.5">查看和管理法规知识库的同步状态</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-accent rounded-xl transition-colors text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Summary Cards */}
          {data && (
            <div className="space-y-4">
              {/* Health Progress Bar */}
              <div className="rounded-xl border border-border/50 bg-gradient-to-br from-card to-card/80 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Activity className="w-4 h-4 text-primary" />
                    总体健康度
                  </div>
                  <span className={cn(
                    "text-sm font-bold tabular-nums",
                    healthyPercent >= 80 ? "text-success" : healthyPercent >= 50 ? "text-warning" : "text-destructive"
                  )}>
                    {healthyPercent}%
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-700",
                      healthyPercent >= 80
                        ? "bg-gradient-to-r from-success to-success/70"
                        : healthyPercent >= 50
                          ? "bg-gradient-to-r from-warning to-warning/70"
                          : "bg-gradient-to-r from-destructive to-destructive/70"
                    )}
                    style={{ width: `${healthyPercent}%` }}
                  />
                </div>
              </div>

              {/* Stat Cards */}
              <div className="grid grid-cols-4 gap-3">
                <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-gradient-to-br from-card to-card/80 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Database className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xl font-bold text-foreground tabular-nums">{totalCount}</div>
                    <div className="text-[11px] text-muted-foreground font-medium">知识库总数</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-success/20 bg-gradient-to-br from-card to-success/5 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/10 text-success">
                    <FolderCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xl font-bold text-success tabular-nums">{healthyCount}</div>
                    <div className="text-[11px] text-muted-foreground font-medium">正常运行</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-warning/20 bg-gradient-to-br from-card to-warning/5 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warning/10 text-warning">
                    <FolderX className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xl font-bold text-warning tabular-nums">{missingCount}</div>
                    <div className="text-[11px] text-muted-foreground font-medium">未创建</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-destructive/20 bg-gradient-to-br from-card to-destructive/5 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                    <CircleAlert className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="text-xl font-bold text-destructive tabular-nums">{errorCount}</div>
                    <div className="text-[11px] text-muted-foreground font-medium">异常</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Loading State */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
              <span className="text-sm text-muted-foreground">正在获取知识库状态...</span>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 flex items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-destructive/10">
                <AlertTriangle className="w-4 h-4 text-destructive" />
              </div>
              <span className="text-sm text-destructive">{error.message}</span>
            </div>
          )}

          {/* Knowledge Base List */}
          {data && !isLoading && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-semibold text-foreground">知识库详情</h4>
                <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{LAW_CATEGORIES.length} 个</span>
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
                        "flex items-center justify-between p-4 rounded-xl border transition-all hover:shadow-sm",
                        isHealthy
                          ? "bg-gradient-to-r from-card to-success/5 border-success/20 hover:border-success/30"
                          : isError
                            ? "bg-gradient-to-r from-card to-destructive/5 border-destructive/20 hover:border-destructive/30"
                            : "bg-gradient-to-r from-card to-warning/5 border-warning/20 hover:border-warning/30"
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", cat.bgColor)}>
                          <cat.icon className={cn("w-5 h-5", cat.color)} />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-foreground">{cat.name}</div>
                          <div className="text-xs text-muted-foreground font-mono mt-0.5">
                            {cat.ragflowKbName}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        {status?.document_count !== undefined && (
                          <div className="text-xs text-muted-foreground flex items-center gap-1.5 bg-muted/50 px-2.5 py-1 rounded-lg">
                            <FileText className="w-3.5 h-3.5" />
                            <span className="tabular-nums font-medium">{status.document_count}</span> 份
                          </div>
                        )}

                        {isHealthy && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/10 text-success">
                            <CheckCircle className="w-3.5 h-3.5" /> 正常
                          </span>
                        )}

                        {isMissing && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-warning/10 text-warning">
                            <AlertCircle className="w-3.5 h-3.5" /> 未创建
                          </span>
                        )}

                        {isError && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-destructive/10 text-destructive">
                            <AlertTriangle className="w-3.5 h-3.5" /> {status?.error_message ?? "错误"}
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
          <div className="px-6 py-3 border-t border-success/20 bg-success/5">
            <div className="text-sm text-success flex items-center gap-2">
              <CheckCircle className="w-4 h-4 shrink-0" />
              <span>
                {initMutation.data.created?.length > 0 && (
                  <span className="font-medium">已创建 {initMutation.data.created.length} 个知识库</span>
                )}
                {initMutation.data.already_exists?.length > 0 && (
                  <span className="text-muted-foreground">，{initMutation.data.already_exists.length} 个已存在</span>
                )}
                {initMutation.data.failed?.length > 0 && (
                  <span className="text-destructive font-medium">，{initMutation.data.failed.length} 个失败</span>
                )}
              </span>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between gap-4 px-6 py-4 border-t border-border shrink-0 bg-muted/30">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <Select value={initType} onValueChange={setInitType}>
              <SelectTrigger
                size="default"
                className="h-10 min-w-[13.5rem] max-w-full rounded-lg border-border bg-card shadow-sm hover:border-primary/30 hover:bg-accent/40 focus-visible:border-primary data-[state=open]:border-primary data-[state=open]:ring-2 data-[state=open]:ring-primary/15"
              >
                <Database className="size-4 shrink-0 text-muted-foreground" />
                <SelectValue placeholder="选择要初始化的知识库" />
              </SelectTrigger>
              <SelectContent
                position="popper"
                side="top"
                sideOffset={8}
                align="start"
                className="z-[200] max-h-64 min-w-[var(--radix-select-trigger-width)] rounded-xl border-border p-1.5 shadow-lg"
              >
                <SelectItem
                  value="all"
                  className="cursor-pointer rounded-lg py-2.5 pl-3 pr-8 text-sm data-[highlighted]:bg-accent data-[state=checked]:bg-primary/10 data-[state=checked]:text-foreground"
                >
                  全部知识库
                </SelectItem>
                {LAW_CATEGORIES.map((cat) => (
                  <SelectItem
                    key={cat.code}
                    value={cat.code}
                    className="cursor-pointer rounded-lg py-2.5 pl-3 pr-8 text-sm data-[highlighted]:bg-accent data-[state=checked]:bg-primary/10 data-[state=checked]:text-foreground"
                  >
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              onClick={handleInit}
              disabled={initMutation.isPending}
              className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 text-sm font-medium shadow-sm"
            >
              {initMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              初始化知识库
            </button>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-4 py-2.5 border border-border rounded-lg hover:bg-accent transition-colors text-sm text-muted-foreground hover:text-foreground"
          >
            {isFetching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>
    </div>
  );
}
