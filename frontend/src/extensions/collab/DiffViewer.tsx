"use client";

import { AlertTriangle, ArrowRight } from "lucide-react";

import type { VersionDiffResponse } from "../types";

interface DiffViewerProps {
  diff: VersionDiffResponse | null;
  loading: boolean;
}

export function DiffViewer({ diff, loading }: DiffViewerProps) {
  if (loading) {
    return (
      <div className="text-muted-foreground p-4 text-center text-sm">
        加载差异对比...
      </div>
    );
  }

  if (!diff) {
    return (
      <div className="text-muted-foreground p-4 text-center text-sm">
        <p>选择两个版本进行差异对比</p>
      </div>
    );
  }

  // Show legacy notice for versions created before text snapshot feature
  if (diff.legacy_notice) {
    return (
      <div className="space-y-3 p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span>v{diff.from_version}</span>
          <ArrowRight className="text-muted-foreground h-4 w-4" />
          <span>v{diff.to_version}</span>
        </div>
        <div className="flex items-start gap-2 rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{diff.legacy_notice}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span>v{diff.from_version}</span>
        <ArrowRight className="text-muted-foreground h-4 w-4" />
        <span>v{diff.to_version}</span>
      </div>

      {diff.ai_summary && (
        <div className="rounded-md bg-blue-50 p-3 text-sm dark:bg-blue-950/30">
          {diff.ai_summary}
        </div>
      )}

      <div className="space-y-1">
        {diff.diff_blocks.map((block, i) => (
          <div
            key={i}
            className={`rounded px-3 py-1.5 font-mono text-sm ${
              block.type === "added"
                ? "bg-green-100 text-green-800 dark:bg-green-950/30 dark:text-green-200"
                : block.type === "removed"
                  ? "bg-red-100 text-red-800 line-through dark:bg-red-950/30 dark:text-red-200"
                  : "bg-yellow-100 text-yellow-800 dark:bg-yellow-950/30 dark:text-yellow-200"
            }`}
          >
            {block.type === "added"
              ? "+ "
              : block.type === "removed"
                ? "- "
                : "~ "}
            {block.content ?? block.to_content ?? ""}
          </div>
        ))}
      </div>

      {diff.diff_blocks.length === 0 && (
        <p className="text-muted-foreground text-center text-sm">
          两个版本无差异
        </p>
      )}
    </div>
  );
}
