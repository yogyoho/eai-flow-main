"use client";

import { GripVertical } from "lucide-react";
import { useCallback, useState } from "react";

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
      className={`bg-background cursor-grab rounded-md border p-3 transition-all duration-150 active:cursor-grabbing ${
        isDragging
          ? "scale-95 rotate-1 opacity-50 shadow-lg"
          : "hover:-translate-y-0.5 hover:shadow-md"
      }`}
    >
      <div className="flex items-start gap-1.5">
        <GripVertical className="text-muted-foreground/40 mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{card.title}</p>
          {card.assignee && (
            <p className="text-muted-foreground mt-1 truncate text-xs">
              {card.assignee}
            </p>
          )}
        </div>
      </div>
      {card.targetWordCount && (
        <div className="mt-2 pl-5">
          <div className="flex items-center gap-2">
            <div className="bg-secondary h-1 flex-1 overflow-hidden rounded-full">
              <div
                className={`h-full rounded-full transition-all ${
                  progress >= 100 ? "bg-success" : "bg-primary"
                }`}
                style={{ width: `${Math.min(progress, 100)}%` }}
              />
            </div>
            <span className="text-muted-foreground text-xs tabular-nums">
              {progress}%
            </span>
          </div>
        </div>
      )}
      {card.dueDate && (
        <p className="text-muted-foreground mt-1 pl-5 text-xs">
          截止: {new Date(card.dueDate).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
