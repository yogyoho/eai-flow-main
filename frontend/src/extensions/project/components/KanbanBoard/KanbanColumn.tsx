"use client";

import { useCallback, useState } from "react";
import { KanbanCard } from "./KanbanCard";
import type { KanbanCardData } from "./types";

interface KanbanColumnProps {
  id: string;
  label: string;
  color: string;
  cards: KanbanCardData[];
  isDragging: boolean;
  isDragOver: boolean;
  onDragStart: (cardId: string) => void;
  onDrop: (columnId: string) => void;
  onDragEnd: () => void;
  onDragOverColumn: (columnId: string | null) => void;
}

export function KanbanColumn({
  id,
  label,
  color,
  cards,
  isDragging,
  isDragOver,
  onDragStart,
  onDrop,
  onDragEnd,
  onDragOverColumn,
}: KanbanColumnProps) {
  return (
    <div
      className={`rounded-lg border-t-4 ${color} min-h-[200px] transition-all duration-200 ${
        isDragOver
          ? "bg-primary/5 ring-2 ring-primary/40 scale-[1.01]"
          : isDragging
            ? "bg-muted/30 ring-1 ring-dashed ring-muted-foreground/20"
            : "bg-muted/30"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        onDragOverColumn(id);
      }}
      onDragLeave={() => onDragOverColumn(null)}
      onDrop={() => {
        onDrop(id);
        onDragOverColumn(null);
      }}
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
            <KanbanCard key={card.id} card={card} onDragStart={onDragStart} onDragEnd={onDragEnd} />
          ))}
          {isDragging && cards.length === 0 && (
            <div className="border-2 border-dashed border-muted-foreground/20 rounded-md p-4 text-center text-xs text-muted-foreground/60">
              拖放至此
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
