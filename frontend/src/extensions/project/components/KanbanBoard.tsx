"use client";

import { useMemo } from "react";

import { Progress } from "@/components/ui/progress";
import {
  CHAPTER_STATUS_LABELS,
  type ChapterStatus,
  type ReportOutline,
} from "@/extensions/project/types";
import { cn } from "@/lib/utils";

const STATUS_ORDER: ChapterStatus[] = [
  "not_started",
  "writing",
  "pending_review",
  "approved",
  "signed",
];

const STATUS_DOT_COLORS: Record<ChapterStatus, string> = {
  not_started: "bg-muted-foreground",
  writing: "bg-primary",
  pending_review: "bg-amber-500",
  approved: "bg-success",
  signed: "bg-success",
};

const STATUS_HEADER_COLORS: Record<ChapterStatus, string> = {
  not_started: "text-muted-foreground",
  writing: "text-primary",
  pending_review: "text-amber-600",
  approved: "text-success",
  signed: "text-success",
};

interface KanbanBoardProps {
  outline: ReportOutline[];
  onChapterClick: (chapterId: string) => void;
}

function flattenChapters(items: ReportOutline[]): ReportOutline[] {
  const result: ReportOutline[] = [];
  for (const item of items) {
    result.push(item);
    if (item.children.length > 0) {
      result.push(...flattenChapters(item.children));
    }
  }
  return result;
}

function AvatarInitials({ name }: { name: string | null }) {
  if (!name) {
    return (
      <div className="h-6 w-6 rounded-full bg-muted flex items-center justify-center text-[10px] text-muted-foreground shrink-0">
        --
      </div>
    );
  }
  const initials = name.slice(0, 2);
  const colors = [
    "bg-blue-500",
    "bg-emerald-500",
    "bg-violet-500",
    "bg-rose-500",
    "bg-amber-500",
    "bg-cyan-500",
  ];
  const colorIndex = name.charCodeAt(0) % colors.length;
  return (
    <div
      className={cn(
        "h-6 w-6 rounded-full flex items-center justify-center text-[10px] text-white shrink-0",
        colors[colorIndex],
      )}
    >
      {initials}
    </div>
  );
}

export function KanbanBoard({ outline, onChapterClick }: KanbanBoardProps) {
  const grouped = useMemo(() => {
    const all = flattenChapters(outline);
    const map = new Map<ChapterStatus, ReportOutline[]>();
    for (const status of STATUS_ORDER) {
      map.set(status, []);
    }
    for (const chapter of all) {
      const list = map.get(chapter.status) ?? [];
      list.push(chapter);
      map.set(chapter.status, list);
    }
    return map;
  }, [outline]);

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 h-full">
      {STATUS_ORDER.map((status) => {
        const chapters = grouped.get(status) ?? [];
        return (
          <div
            key={status}
            className="flex flex-col min-w-[260px] w-[260px] shrink-0"
          >
            {/* Column header */}
            <div className="flex items-center gap-2 mb-3 px-1">
              <span
                className={cn(
                  "h-2 w-2 rounded-full shrink-0",
                  STATUS_DOT_COLORS[status],
                )}
              />
              <span
                className={cn(
                  "text-sm font-medium",
                  STATUS_HEADER_COLORS[status],
                )}
              >
                {CHAPTER_STATUS_LABELS[status]}
              </span>
              <span className="inline-flex items-center justify-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {chapters.length}
              </span>
            </div>

            {/* Column cards */}
            <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
              {chapters.map((chapter) => {
                const progress =
                  chapter.wordCountTarget > 0
                    ? Math.round(
                        (chapter.wordCountCurrent / chapter.wordCountTarget) *
                          100,
                      )
                    : 0;
                return (
                  <div
                    key={chapter.id}
                    className="rounded-lg border border-border bg-background p-3 cursor-pointer hover:border-primary/50 transition-colors"
                    onClick={() => onChapterClick(chapter.id)}
                  >
                    <div className="text-sm font-medium text-foreground leading-snug mb-2">
                      {chapter.title}
                    </div>
                    <div className="flex items-center gap-2 mb-2">
                      <AvatarInitials name={chapter.assigneeName} />
                      <span className="text-xs text-muted-foreground truncate">
                        {chapter.assigneeName ?? "未分配"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Progress value={progress} className="h-1.5 flex-1" />
                      <span className="text-[10px] text-muted-foreground shrink-0">
                        {progress}%
                      </span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      {chapter.wordCountCurrent} / {chapter.wordCountTarget} 字
                    </div>
                  </div>
                );
              })}
              {chapters.length === 0 && (
                <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  暂无章节
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
