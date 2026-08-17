"use client";

import type { TimelineEntry } from "./types";

interface GanttBarProps {
  entry: TimelineEntry;
  timelineStart: Date;
  colWidth: number;
}

export function GanttBar({ entry, timelineStart, colWidth }: GanttBarProps) {
  const dayToOffset = (dateStr: string) => {
    const d = new Date(dateStr);
    const days = Math.ceil(
      (d.getTime() - timelineStart.getTime()) / (1000 * 60 * 60 * 24),
    );
    return days * colWidth;
  };

  const isOverdue = () => {
    if (!entry.planned_end || entry.progress_pct >= 100) return false;
    return new Date(entry.planned_end) < new Date();
  };

  // Planned bar (outline)
  const plannedStart = entry.planned_start
    ? dayToOffset(entry.planned_start)
    : 0;
  const plannedEnd = entry.planned_end
    ? dayToOffset(entry.planned_end)
    : plannedStart + colWidth * 14;
  const plannedWidth = Math.max(plannedEnd - plannedStart, colWidth);

  // Actual bar (filled)
  const actualStart = entry.actual_start
    ? dayToOffset(entry.actual_start)
    : plannedStart;
  const actualEnd = entry.actual_end
    ? dayToOffset(entry.actual_end)
    : dayToOffset(new Date().toISOString());
  const actualWidth = Math.max(actualEnd - actualStart, colWidth);

  const overdue = isOverdue();

  return (
    <div className="relative flex h-10 items-center border-b">
      {/* Planned outline */}
      <div
        className="absolute top-1.5 h-7 rounded-sm border-2 opacity-40"
        style={{
          left: plannedStart,
          width: plannedWidth,
          borderColor: overdue
            ? "var(--color-warning, #f59e0b)"
            : "var(--color-primary, #3b82f6)",
        }}
      />

      {/* Actual filled */}
      {(entry.actual_start ?? entry.progress_pct > 0) && (
        <div
          className={`absolute top-1.5 flex h-7 items-center rounded-sm px-2 text-xs text-white ${
            overdue ? "bg-warning" : "bg-primary"
          }`}
          style={{
            left: actualStart,
            width: Math.min(actualWidth, plannedWidth),
          }}
        >
          {entry.progress_pct > 0 && (
            <span className="truncate">{entry.progress_pct}%</span>
          )}
        </div>
      )}

      {/* Milestones */}
      {(entry.milestones ?? []).map((ms, i) =>
        ms.target_date ? (
          <div
            key={i}
            className="absolute top-1.5 -translate-x-1/2 text-sm"
            style={{ left: dayToOffset(ms.target_date) }}
            title={ms.label}
          >
            ◆
          </div>
        ) : null,
      )}
    </div>
  );
}
