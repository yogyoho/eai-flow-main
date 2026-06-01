"use client";

import { useState, useMemo } from "react";
import type { TimelineEntry, ZoomLevel } from "./types";
import { GanttBar } from "./GanttBar";

interface GanttChartProps {
  entries: TimelineEntry[];
}

export function GanttChart({ entries }: GanttChartProps) {
  const [zoom, setZoom] = useState<ZoomLevel>("week");

  // Compute date range
  const { start, end } = useMemo(() => {
    const dates = entries.flatMap((e) =>
      [e.planned_start, e.planned_end, e.actual_start, e.actual_end].filter(
        Boolean
      ) as string[]
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
    (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
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
    Math.ceil(
      (Date.now() - start.getTime()) / (1000 * 60 * 60 * 24)
    ) * colWidth;

  return (
    <div className="space-y-2">
      {/* Zoom controls */}
      <div className="flex gap-2 mb-3">
        {(["month", "week", "day"] as ZoomLevel[]).map((z) => (
          <button
            key={z}
            onClick={() => setZoom(z)}
            className={`px-3 py-1 text-xs rounded-md border ${
              zoom === z
                ? "bg-primary text-primary-foreground"
                : "hover:bg-accent"
            }`}
          >
            {z === "month" ? "月" : z === "week" ? "周" : "日"}
          </button>
        ))}
        <span className="text-xs text-muted-foreground ml-2">
          {start.toLocaleDateString()} — {end.toLocaleDateString()}
        </span>
      </div>

      {/* Chart area */}
      <div className="overflow-x-auto border rounded-lg">
        <div className="flex min-w-full">
          {/* Phase labels */}
          <div className="w-48 shrink-0 border-r bg-muted/30">
            <div className="h-8 border-b px-3 flex items-center text-xs font-medium">
              阶段
            </div>
            {entries.map((entry) => (
              <div
                key={entry.id}
                className="h-10 border-b px-3 flex items-center text-sm truncate"
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
                className="absolute top-0 bottom-0 w-px bg-red-400 z-10"
                style={{ left: todayOffset }}
              >
                <span className="absolute top-0 -translate-x-1/2 text-[10px] text-red-500 bg-background px-1">
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
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border-2 border-primary" />{" "}
          计划
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm bg-primary" /> 实际
        </span>
        <span className="flex items-center gap-1">
          <span className="text-amber-500">■</span> 延期
        </span>
        <span className="flex items-center gap-1">◆ 里程碑</span>
      </div>
    </div>
  );
}
