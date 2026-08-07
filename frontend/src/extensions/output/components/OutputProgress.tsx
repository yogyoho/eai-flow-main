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

export function OutputProgress({
  result,
  polling,
  onRetry,
}: OutputProgressProps) {
  if (!result) return null;

  if (result.status === "queued" || result.status === "processing") {
    return (
      <div className="border-border bg-card space-y-4 rounded-xl border p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <Loader2 className="text-primary h-5 w-5 animate-spin" />
          <span className="text-foreground text-sm font-medium">
            {STATUS_LABELS[result.status]}...
          </span>
        </div>
        <div className="bg-muted h-2 w-full overflow-hidden rounded-full">
          <div
            className="from-primary to-primary/70 h-full rounded-full bg-gradient-to-r transition-all duration-1000"
            style={{ width: result.status === "processing" ? "60%" : "20%" }}
          />
        </div>
        <p className="text-muted-foreground text-xs">
          {polling ? "正在等待生成结果..." : "任务已提交"}
        </p>
      </div>
    );
  }

  if (result.status === "completed" && result.downloadUrl) {
    return (
      <div className="border-success/20 bg-success/5 space-y-4 rounded-xl border p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <Download className="text-success h-5 w-5" />
          <div>
            <span className="text-foreground text-sm font-medium">
              报告已生成
            </span>
            {result.fileName && (
              <p className="text-muted-foreground text-xs">{result.fileName}</p>
            )}
          </div>
        </div>
        <a
          href={result.downloadUrl}
          download={result.fileName}
          className="bg-success hover:bg-success/90 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors"
        >
          <Download className="h-4 w-4" />
          下载文件
        </a>
      </div>
    );
  }

  if (result.status === "failed") {
    return (
      <div className="border-destructive/20 bg-destructive/5 space-y-4 rounded-xl border p-5 shadow-sm">
        <div className="flex items-center gap-3">
          <AlertCircle className="text-destructive h-5 w-5" />
          <span className="text-foreground text-sm font-medium">生成失败</span>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="border-destructive/20 bg-destructive/10 text-destructive hover:bg-destructive/20 inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
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
