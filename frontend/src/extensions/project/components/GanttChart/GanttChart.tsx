"use client";

import { useState, useMemo } from "react";

import { GanttBar } from "./GanttBar";
import type { TimelineEntry, ZoomLevel } from "./types";

interface GanttChartProps {
  entries: TimelineEntry[];
}

export function GanttChart({ entries }: GanttChartProps) {
  const [zoom, setZoom] = useState<ZoomLevel>("week");

  // Compute date range
  const { start, end } = useMemo(() => {
    const dates = entries.flatMap(
      (e) =>
        [e.planned_start, e.planned_end, e.actual_start, e.actual_end].filter(
          Boolean,
        ) as string[],
    );
    if (dates.length === 0) return { start: new Date(), end: new Date() };
    const parsed = dates.map((d) => new Date(d));
    const minDate = new Date(Math.min(...parsed.map((d) => d.getTime())));
    const maxDate = new Date(Math.max(...parsed.map((d) => d.getTime())));
    // Add padding
    minDate.setDate(minDate.getDate() - 7);
    maxDate.setDate(maxDate.getDate() + 14);
    return { start: minDate, end: maxDate };
  }, [entries]);

  const totalDays = Math.ceil(
    (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24),
  );

  const getColumnWidth = () => {
    switch (zoom) {
      case "day":
        return 40;
      case "week":
        return 28;
      case "month":
        return 20;
    }
  };

  const colWidth = getColumnWidth();
  const timelineWidth = totalDays * colWidth;

  const todayOffset =
    Math.ceil((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24)) *
    colWidth;

  return (
    <div className="space-y-2">
      {/* Zoom controls */}
      <div className="mb-3 flex gap-2">
        {(["month", "week", "day"] as ZoomLevel[]).map((z) => (
          <button
            key={z}
            onClick={() => setZoom(z)}
            className={`rounded-md border px-3 py-1 text-xs ${
              zoom === z
                ? "bg-primary text-primary-foreground"
                : "hover:bg-accent"
            }`}
          >
            {z === "month" ? "月" : z === "week" ? "周" : "日"}
          </button>
        ))}
        <span className="text-muted-foreground ml-2 text-xs">
          {start.toLocaleDateString()} — {end.toLocaleDateString()}
        </span>
      </div>

      {/* Chart area */}
      <div className="overflow-x-auto rounded-lg border">
        <div className="flex min-w-full">
          {/* Phase labels */}
          <div className="bg-muted/30 w-48 shrink-0 border-r">
            <div className="flex h-8 items-center border-b px-3 text-xs font-medium">
              阶段
            </div>
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="flex h-10 items-center truncate border-b px-3 text-sm"
              >
                {entry.phase_node}
              </div>
            ))}
          </div>

          {/* Timeline */}
          <div
            className="relative"
            style={{ width: Math.max(timelineWidth, 400) }}
          >
            {/* Today line */}
            {todayOffset > 0 && todayOffset < timelineWidth && (
              <div
                className="bg-destructive absolute top-0 bottom-0 z-10 w-px"
                style={{ left: todayOffset }}
              >
                <span className="text-destructive bg-background absolute top-0 -translate-x-1/2 px-1 text-[10px]">
                  今天
                </span>
              </div>
            )}

            {/* Bars */}
            {entries.map((entry) => (
              <GanttBar
                key={entry.id}
                entry={entry}
                timelineStart={start}
                colWidth={colWidth}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="text-muted-foreground flex gap-4 text-xs">
        <span className="flex items-center gap-1">
          <span className="border-primary inline-block h-3 w-3 rounded-sm border-2" />{" "}
          计划
        </span>
        <span className="flex items-center gap-1">
          <span className="bg-primary inline-block h-3 w-3 rounded-sm" /> 实际
        </span>
        <span className="flex items-center gap-1">
          <span className="text-warning">■</span> 延期
        </span>
        <span className="flex items-center gap-1">◆ 里程碑</span>
      </div>
    </div>
  );
}
