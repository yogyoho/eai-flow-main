"use client";

import { cn } from "@/lib/utils";

import { CHAPTER_STATUS_LABELS, type ChapterStatus } from "./types";

const STATUS_STYLES: Record<ChapterStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  writing: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  draft: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  editing: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",
  approved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
};

interface ChapterStatusBadgeProps {
  status: ChapterStatus;
  className?: string;
}

export function ChapterStatusBadge({ status, className }: ChapterStatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
        STATUS_STYLES[status],
        className,
      )}
    >
      {CHAPTER_STATUS_LABELS[status]}
    </span>
  );
}