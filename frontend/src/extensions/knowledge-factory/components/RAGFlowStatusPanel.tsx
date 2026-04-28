"use client";

import {
  X,
  CheckCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Database,
  FileText,
} from "lucide-react";
import React, { useState } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { LAW_CATEGORIES } from "../config/lawCategories";
import { useRAGFlowStatus, useInitRAGFlow } from "../hooks/useLawLibrary";
import type { LawType } from "@/extensions/knowledge-factory/types";
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Database className="w-5 h-5 text-primary" />
            RAGFlow知识库状态
          </h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-accent rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Summary */}
          {data && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-muted/50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-foreground">
                  {data.total_kbs}
                </div>
                <div className="text-sm text-muted-foreground">知识库总数</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-green-600">
                  {data.healthy_kbs}
                </div>
                <div className="text-sm text-green-600">正常</div>
              </div>
              <div className="bg-amber-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-amber-600">
                  {data.missing_kbs}
                </div>
                <div className="text-sm text-amber-600">未创建</div>
              </div>
              <div className="bg-red-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-red-600">
                  {data.error_kbs}
                </div>
                <div className="text-sm text-red-600">错误</div>
              </div>
            </div>
          )}

          {/* Loading/Error State */}
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <span className="ml-3 text-muted-foreground">加载中...</span>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
              <span className="text-red-700">{error.message}</span>
            </div>
          )}

          {/* Knowledge Base List */}
          {data && !isLoading && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium text-foreground">知识库详情</h4>
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
                        "flex items-center justify-between p-4 rounded-lg border",
                        isHealthy
                          ? "bg-green-50 border-green-200"
                          : isError
                            ? "bg-red-50 border-red-200"
                            : "bg-amber-50 border-amber-200"
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "w-10 h-10 rounded-lg flex items-center justify-center",
                            cat.bgColor
                          )}
                        >
                          <cat.icon className={cn("w-5 h-5", cat.color)} />
                        </div>
                        <div>
                          <div className="font-medium text-foreground">{cat.name}</div>
                          <div className="text-sm text-muted-foreground">
                            {cat.ragflowKbName}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        {status?.document_count !== undefined && (
                          <div className="text-sm text-muted-foreground flex items-center gap-1">
                            <FileText className="w-4 h-4" />
                            {status.document_count} 份文档
                          </div>
                        )}

                        {isHealthy && (
                          <div className="flex items-center gap-1 text-green-600">
                            <CheckCircle className="w-5 h-5" />
                            <span className="text-sm font-medium">正常</span>
                          </div>
                        )}

                        {isMissing && (
                          <div className="flex items-center gap-1 text-amber-600">
                            <AlertCircle className="w-5 h-5" />
                            <span className="text-sm font-medium">未创建</span>
                          </div>
                        )}

                        {isError && (
                          <div className="flex items-center gap-1 text-red-600">
                            <AlertCircle className="w-5 h-5" />
                            <span className="text-sm font-medium">
                              {status?.error_message ?? "错误"}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-4 p-4 border-t border-border shrink-0 bg-muted/30">
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
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
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
            className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg hover:bg-accent transition-colors"
          >
            {isFetching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新状态
          </button>
        </div>

        {/* Init Result */}
        {initMutation.data && (
          <div className="p-4 border-t border-border bg-green-50">
            <div className="text-sm text-green-700">
              <strong>初始化结果：</strong>
              {initMutation.data.created?.length > 0 && (
                <span>已创建 {initMutation.data.created.length} 个知识库</span>
              )}
              {initMutation.data.already_exists?.length > 0 && (
                <span>，{initMutation.data.already_exists.length} 个已存在</span>
              )}
              {initMutation.data.failed?.length > 0 && (
                <span className="text-red-600">
                  ，{initMutation.data.failed.length} 个失败
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}