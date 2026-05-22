"use client";

import { AlertCircle, Download, RefreshCw, Loader2 } from "lucide-react";
import React from "react";

import type { GenerateOutputResult } from "@/extensions/output/types";

interface OutputProgressProps {
  result: GenerateOutputResult | null;
  polling: boolean;
  onRetry?: () => void;
}

const STATUS_LABELS: Record<GenerateOutputResult["status"], string> = {
  queued: "排队中",
  processing: "正在生成",
  completed: "已完成",
  failed: "生成失败",
};

export function OutputProgress({ result, polling, onRetry }: OutputProgressProps) {
  if (!result) return null;

  if (result.status === "queued" || result.status === "processing") {
    return (
      <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span className="text-sm font-medium text-foreground">
            {STATUS_LABELS[result.status]}...
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-primary/70 transition-all duration-1000"
            style={{ width: result.status === "processing" ? "60%" : "20%" }}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          {polling ? "正在等待生成结果..." : "任务已提交"}
        </p>
      </div>
    );
  }

  if (result.status === "completed" && result.downloadUrl) {
    return (
      <div className="space-y-4 rounded-xl border border-success/20 bg-success/5 p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <Download className="h-5 w-5 text-success" />
          <div>
            <span className="text-sm font-medium text-foreground">报告已生成</span>
            {result.fileName && (
              <p className="text-xs text-muted-foreground">{result.fileName}</p>
            )}
          </div>
        </div>
        <a
          href={result.downloadUrl}
          download={result.fileName}
          className="inline-flex items-center gap-2 rounded-lg bg-success px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-success/90"
        >
          <Download className="h-4 w-4" />
          下载文件
        </a>
      </div>
    );
  }

  if (result.status === "failed") {
    return (
      <div className="space-y-4 rounded-xl border border-destructive/20 bg-destructive/5 p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span className="text-sm font-medium text-foreground">生成失败</span>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-2 text-sm font-medium text-destructive transition-colors hover:bg-destructive/20"
          >
            <RefreshCw className="h-4 w-4" />
            重新生成
          </button>
        )}
      </div>
    );
  }

  return null;
}
