"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import {
  CHAPTER_STATUS_LABELS,
  type ChapterStatus,
  type ReportOutline,
} from "@/extensions/project/types";
import { cn } from "@/lib/utils";

const STATUS_DOT_COLORS: Record<ChapterStatus, string> = {
  not_started: "bg-muted-foreground",
  writing: "bg-primary",
  pending_review: "bg-amber-500",
  approved: "bg-success",
  signed: "bg-success",
};

interface OutlineTreeProps {
  items: ReportOutline[];
  onChapterClick: (id: string) => void;
  depth?: number;
}

interface TreeNodeProps {
  item: ReportOutline;
  onChapterClick: (id: string) => void;
  depth: number;
}

function TreeNode({ item, onChapterClick, depth }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 1);
  const hasChildren = item.children.length > 0;
  const progress =
    item.wordCountTarget > 0
      ? Math.round((item.wordCountCurrent / item.wordCountTarget) * 100)
      : 0;

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-2 py-1.5 px-2 cursor-pointer hover:bg-muted/50 rounded-lg transition-colors",
          depth > 0 && `pl-${depth * 4}`,
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => {
          if (hasChildren) {
            setExpanded((prev) => !prev);
          }
          onChapterClick(item.id);
        }}
      >
        {/* Expand/collapse arrow */}
        {hasChildren ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
          )
        ) : (
          <span className="w-4 shrink-0" />
        )}

        {/* Status dot */}
        <span
          className={cn(
            "h-2 w-2 rounded-full shrink-0",
            STATUS_DOT_COLORS[item.status],
          )}
        />

        {/* Title */}
        <span className="text-sm text-foreground truncate flex-1 min-w-0">
          {item.title}
        </span>

        {/* Assignee */}
        {item.assigneeName && (
          <span className="text-xs text-muted-foreground shrink-0 hidden sm:inline">
            {item.assigneeName}
          </span>
        )}

        {/* Word count */}
        <span className="text-[10px] text-muted-foreground shrink-0">
          {progress}%
        </span>

        {/* Status label */}
        <span className="text-[10px] text-muted-foreground shrink-0 hidden sm:inline">
          {CHAPTER_STATUS_LABELS[item.status]}
        </span>
      </div>

      {/* Children */}
      {hasChildren && expanded && (
        <div>
          {item.children.map((child) => (
            <TreeNode
              key={child.id}
              item={child}
              onChapterClick={onChapterClick}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function OutlineTree({
  items,
  onChapterClick,
  depth = 0,
}: OutlineTreeProps) {
  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
        暂无大纲数据
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {items.map((item) => (
        <TreeNode
          key={item.id}
          item={item}
          onChapterClick={onChapterClick}
          depth={depth}
        />
      ))}
    </div>
  );
}
