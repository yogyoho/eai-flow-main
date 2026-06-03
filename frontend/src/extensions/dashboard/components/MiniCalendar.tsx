"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarIcon } from "lucide-react";
import { zhCN } from "date-fns/locale/zh-CN";
import { Calendar } from "@/components/ui/calendar";
import { useMyCalendar } from "../hooks/useMyCalendar";
import type { CalendarEvent } from "../types";

const COLOR_MAP: Record<string, string> = {
  blue: "bg-blue-500",
  yellow: "bg-amber-500",
  green: "bg-green-500",
  red: "bg-red-500",
  purple: "bg-purple-500",
};

const TYPE_LABELS: Record<string, string> = {
  deadline: "截止",
  milestone: "里程碑",
  phase_start: "阶段",
  personal: "个人",
};

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function MiniCalendar() {
  const [mounted, setMounted] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);
  const [month, setMonth] = useState<Date | undefined>(undefined);

  useEffect(() => {
    const now = new Date();
    setSelectedDate(now);
    setMonth(now);
    setMounted(true);
  }, []);

  // Compute start/end for the visible month
  const { startStr, endStr } = useMemo(() => {
    if (!month) return { startStr: "", endStr: "" };
    const y = month.getFullYear();
    const m = month.getMonth();
    const start = new Date(y, m, 1);
    const end = new Date(y, m + 1, 0);
    return {
      startStr: start.toISOString(),
      endStr: end.toISOString(),
    };
  }, [month]);

  const { data, isLoading } = useMyCalendar(startStr, endStr);
  const events = data?.events || [];

  // Build a map of date string → events
  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};
    for (const ev of events) {
      const d = new Date(ev.date);
      const key = dateKey(d);
      if (!map[key]) map[key] = [];
      map[key].push(ev);
    }
    return map;
  }, [events]);

  // Dates that have events (for highlighting via modifiers)
  const eventDates = useMemo(() => {
    return events.map((ev) => new Date(ev.date));
  }, [events]);

  const selectedKey = selectedDate ? dateKey(selectedDate) : "";
  const selectedEvents = eventsByDate[selectedKey] || [];

  if (!mounted || !month) {
    return (
      <div className="h-40 flex items-center justify-center">
        <div className="animate-pulse text-xs text-muted-foreground">加载中...</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {isLoading ? (
        <div className="h-40 flex items-center justify-center">
          <div className="animate-pulse text-xs text-muted-foreground">加载中...</div>
        </div>
      ) : (
        <Calendar
          mode="single"
          selected={selectedDate}
          onSelect={setSelectedDate}
          month={month}
          onMonthChange={setMonth}
          locale={zhCN}
          className="rounded-md text-xs [&_.rd-day]:h-8 [&_.rd-day]:w-8"
          modifiers={{ hasEvent: eventDates }}
          modifiersStyles={{
            hasEvent: { fontWeight: 700, textDecoration: "underline", textDecorationColor: "var(--color-primary)", textUnderlineOffset: "3px" },
          }}
        />
      )}

      {/* Events for selected date */}
      {selectedDate && (
        <div className="space-y-1.5">
          <div className="text-[10px] text-muted-foreground flex items-center gap-1">
            <CalendarIcon className="h-3 w-3" />
            {selectedDate.getMonth() + 1}月{selectedDate.getDate()}日
          </div>
          {selectedEvents.length === 0 ? (
            <div className="text-[10px] text-muted-foreground/60">暂无事项</div>
          ) : (
            selectedEvents.map((ev) => (
              <a
                key={ev.id}
                href={ev.project_id ? `/projects/${ev.project_id}?tab=workflow` : "#"}
                className="flex items-center gap-1.5 text-xs px-2 py-1 rounded hover:bg-muted transition-colors"
              >
                <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${COLOR_MAP[ev.color] || "bg-blue-500"}`} />
                <span className="truncate flex-1">{ev.title}</span>
                <span className="text-[10px] text-muted-foreground shrink-0">{TYPE_LABELS[ev.type] || ev.type}</span>
              </a>
            ))
          )}
        </div>
      )}
    </div>
  );
}
