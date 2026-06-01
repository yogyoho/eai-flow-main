"use client";

import type { KanbanCardData } from "./types";

interface KanbanCardProps {
  card: KanbanCardData;
  onDragStart: (cardId: string) => void;
}

export function KanbanCard({ card, onDragStart }: KanbanCardProps) {
  const progress =
    card.targetWordCount && card.wordCount !== undefined
      ? Math.round((card.wordCount / card.targetWordCount) * 100)
      : 0;

  return (
    <div
      draggable
      onDragStart={() => onDragStart(card.id)}
      className="rounded-md border bg-background p-3 cursor-grab active:cursor-grabbing hover:shadow-sm transition-shadow"
    >
      <p className="text-sm font-medium truncate">{card.title}</p>
      {card.assignee && (
        <p className="text-xs text-muted-foreground mt-1">
          👤 {card.assignee}
        </p>
      )}
      {card.targetWordCount && (
        <div className="mt-2">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full bg-primary rounded-full"
                style={{ width: `${Math.min(progress, 100)}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground">{progress}%</span>
          </div>
        </div>
      )}
      {card.dueDate && (
        <p className="text-xs text-muted-foreground mt-1">
          截止: {new Date(card.dueDate).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
