"use client";

import { KanbanCard } from "./KanbanCard";
import type { KanbanCardData } from "./types";

interface KanbanColumnProps {
  id: string;
  label: string;
  color: string;
  cards: KanbanCardData[];
  isDragging: boolean;
  onDragStart: (cardId: string) => void;
  onDrop: (columnId: string) => void;
}

export function KanbanColumn({
  id,
  label,
  color,
  cards,
  isDragging,
  onDragStart,
  onDrop,
}: KanbanColumnProps) {
  return (
    <div
      className={`rounded-lg border-t-4 ${color} bg-muted/30 min-h-[200px] ${
        isDragging ? "ring-2 ring-primary/30" : ""
      }`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={() => onDrop(id)}
    >
      <div className="p-3">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">{label}</h3>
          <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
            {cards.length}
          </span>
        </div>
        <div className="space-y-2">
          {cards.map((card) => (
            <KanbanCard key={card.id} card={card} onDragStart={onDragStart} />
          ))}
        </div>
      </div>
    </div>
  );
}
