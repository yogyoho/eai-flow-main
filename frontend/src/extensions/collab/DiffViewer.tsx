"use client";

import { ArrowRight } from "lucide-react";
import type { VersionDiffResponse } from "../types";

interface DiffViewerProps {
  diff: VersionDiffResponse | null;
  loading: boolean;
}

export function DiffViewer({ diff, loading }: DiffViewerProps) {
  if (loading) {
    return <div className="p-4 text-center text-sm text-muted-foreground">加载差异对比...</div>;
  }

  if (!diff) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        <p>选择两个版本进行差异对比</p>
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span>v{diff.from_version}</span>
        <ArrowRight className="w-4 h-4 text-muted-foreground" />
        <span>v{diff.to_version}</span>
      </div>

      {diff.ai_summary && (
        <div className="p-3 rounded-md bg-blue-50 dark:bg-blue-950/30 text-sm">
          {diff.ai_summary}
        </div>
      )}

      <div className="space-y-1">
        {diff.diff_blocks.map((block, i) => (
          <div
            key={i}
            className={`px-3 py-1.5 rounded text-sm font-mono ${
              block.type === "added"
                ? "bg-green-100 dark:bg-green-950/30 text-green-800 dark:text-green-200"
                : block.type === "removed"
                  ? "bg-red-100 dark:bg-red-950/30 text-red-800 dark:text-red-200 line-through"
                  : "bg-yellow-100 dark:bg-yellow-950/30 text-yellow-800 dark:text-yellow-200"
            }`}
          >
            {block.type === "added" ? "+ " : block.type === "removed" ? "- " : "~ "}
            {block.content || block.to_content || ""}
          </div>
        ))}
      </div>

      {diff.diff_blocks.length === 0 && (
        <p className="text-sm text-muted-foreground text-center">两个版本无差异</p>
      )}
    </div>
  );
}
