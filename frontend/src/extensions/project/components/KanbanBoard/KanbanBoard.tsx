"use client";

import { useCallback, useState } from "react";
import type { KanbanCardData } from "./types";
import { KanbanColumn } from "./KanbanColumn";

export interface KanbanBoardProps {
  cards: KanbanCardData[];
  onCardMove?: (cardId: string, newStatus: string) => void;
  /** Called when user clicks edit on a card */
  onCardEdit?: (cardId: string) => void;
}

const COLUMNS = [
  { id: "draft", label: "待编写", color: "border-t-gray-400" },
  { id: "writing", label: "编写中", color: "border-t-blue-500" },
  { id: "review", label: "审核中", color: "border-t-amber-500" },
  { id: "completed", label: "已完成", color: "border-t-green-500" },
] as const;

export function KanbanBoard({ cards, onCardMove, onCardEdit: _onCardEdit }: KanbanBoardProps) {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);

  const handleDragStart = useCallback((cardId: string) => {
    setDraggedId(cardId);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedId(null);
    setOverColumnId(null);
  }, []);

  const handleDrop = useCallback(
    (columnId: string) => {
      if (draggedId && onCardMove) {
        onCardMove(draggedId, columnId);
      }
      setDraggedId(null);
      setOverColumnId(null);
    },
    [draggedId, onCardMove],
  );

  const handleDragOverColumn = useCallback((columnId: string | null) => {
    setOverColumnId(columnId);
  }, []);

  return (
    <div className="grid grid-cols-4 gap-4">
      {COLUMNS.map((col) => (
        <KanbanColumn
          key={col.id}
          id={col.id}
          label={col.label}
          color={col.color}
          cards={cards.filter((c) => c.status === col.id)}
          isDragging={draggedId !== null}
          isDragOver={overColumnId === col.id}
          onDragStart={handleDragStart}
          onDrop={handleDrop}
          onDragEnd={handleDragEnd}
          onDragOverColumn={handleDragOverColumn}
        />
      ))}
    </div>
  );
}
