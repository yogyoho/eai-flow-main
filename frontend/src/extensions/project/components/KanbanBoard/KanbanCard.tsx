"use client";

import { useCallback, useState } from "react";
import { GripVertical } from "lucide-react";
import type { KanbanCardData } from "./types";

interface KanbanCardProps {
  card: KanbanCardData;
  onDragStart: (cardId: string) => void;
  onDragEnd: () => void;
}

export function KanbanCard({ card, onDragStart, onDragEnd }: KanbanCardProps) {
  const [isDragging, setIsDragging] = useState(false);

  const progress =
    card.targetWordCount && card.wordCount !== undefined
      ? Math.round((card.wordCount / card.targetWordCount) * 100)
      : 0;

  const handleDragStart = useCallback(() => {
    setIsDragging(true);
    onDragStart(card.id);
  }, [card.id, onDragStart]);

  const handleDragEnd = useCallback(() => {
    setIsDragging(false);
    onDragEnd();
  }, [onDragEnd]);

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      className={`rounded-md border bg-background p-3 cursor-grab active:cursor-grabbing transition-all duration-150 ${
        isDragging
          ? "opacity-50 scale-95 shadow-lg rotate-1"
          : "hover:shadow-md hover:-translate-y-0.5"
      }`}
    >
      <div className="flex items-start gap-1.5">
        <GripVertical className="h-3.5 w-3.5 text-muted-foreground/40 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{card.title}</p>
          {card.assignee && (
            <p className="text-xs text-muted-foreground mt-1 truncate">{card.assignee}</p>
          )}
        </div>
      </div>
      {card.targetWordCount && (
        <div className="mt-2 pl-5">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-secondary overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  progress >= 100 ? "bg-green-500" : "bg-primary"
                }`}
                style={{ width: `${Math.min(progress, 100)}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground tabular-nums">{progress}%</span>
          </div>
        </div>
      )}
      {card.dueDate && (
        <p className="text-xs text-muted-foreground mt-1 pl-5">
          截止: {new Date(card.dueDate).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
