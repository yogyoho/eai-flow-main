"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Calendar, ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { dashboardApi } from "../api";
import { useMyCalendar } from "../hooks/useMyCalendar";
import type { CalendarEvent } from "../types";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const MONTHS = [
  "1月",
  "2月",
  "3月",
  "4月",
  "5月",
  "6月",
  "7月",
  "8月",
  "9月",
  "10月",
  "11月",
  "12月",
];

function dateKey(y: number, m: number, d: number) {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function MiniCalendar() {
  const queryClient = useQueryClient();
  const [mounted, setMounted] = useState(false);
  const [currentYear, setCurrentYear] = useState(2026);
  const [currentMonth, setCurrentMonth] = useState(5);
  const [selectedDay, setSelectedDay] = useState(20);

  // Add-event form state (reference SpaceCalendar pattern)
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newTime, setNewTime] = useState("10:00");
  const [newType, setNewType] = useState<CalendarEvent["type"]>("personal");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const now = new Date();
    setCurrentYear(now.getFullYear());
    setCurrentMonth(now.getMonth());
    setSelectedDay(now.getDate());
    setMounted(true);
  }, []);

  const { startStr, endStr } = useMemo(() => {
    const start = new Date(currentYear, currentMonth, 1);
    const end = new Date(currentYear, currentMonth + 1, 0);
    return { startStr: start.toISOString(), endStr: end.toISOString() };
  }, [currentYear, currentMonth]);

  const { data } = useMyCalendar(startStr, endStr);
  const events = useMemo(() => data?.events ?? [], [data]);

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};
    for (const ev of events) {
      const d = new Date(ev.date);
      const k = dateKey(d.getFullYear(), d.getMonth(), d.getDate());
      map[k] ??= [];
      map[k].push(ev);
    }
    return map;
  }, [events]);

  const selectedDateStr = dateKey(currentYear, currentMonth, selectedDay);
  const dayEvents = eventsByDate[selectedDateStr] ?? [];

  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const daysArray = Array.from({ length: daysInMonth }, (_, i) => i + 1);
  const firstDay = new Date(currentYear, currentMonth, 1).getDay();
  const leadingBlanks = firstDay === 0 ? 6 : firstDay - 1;

  const prevMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else setCurrentMonth((m) => m - 1);
  };
  const nextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else setCurrentMonth((m) => m + 1);
  };

  const handleAddEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || saving) return;
    setSaving(true);
    try {
      await dashboardApi.createCalendarEvent({
        title: newTitle.trim(),
        date: selectedDateStr,
        time: newTime,
        type: newType,
      });
      toast.success(`已添加日程: ${newTitle.trim()}`);
      setNewTitle("");
      setScheduleOpen(false);
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "my-calendar"],
      });
    } catch {
      toast.error("添加日程失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  if (!mounted) {
    return (
      <div className="flex h-40 animate-pulse items-center justify-center text-xs text-slate-500">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Header — reference SpaceCalendar */}
      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="rounded-md border border-blue-500/20 bg-blue-500/10 p-1.5 text-blue-500">
            <Calendar className="h-4 w-4 animate-pulse" />
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            日程{" "}
            <span className="text-xs font-normal text-slate-500">
              Scheduler
            </span>
          </h2>
        </div>
        <button
          onClick={() => setScheduleOpen(!scheduleOpen)}
          className="font-cyber flex cursor-pointer items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-500"
        >
          {scheduleOpen ? "✖ 关闭" : "✚ 添加日程"}
        </button>
      </div>

      {/* Add Event Form — reference SpaceCalendar schedule form */}
      {scheduleOpen && (
        <form
          onSubmit={handleAddEvent}
          className="mb-4 flex flex-col gap-2.5 overflow-hidden rounded-lg border border-blue-500/20 bg-blue-500/5 p-3 text-xs"
        >
          <h4 className="font-bold text-blue-600">
            安排于 {selectedDay}日 运作议程
          </h4>
          <div>
            <label className="db-text-muted font-cyber mb-1 block text-[10px] tracking-wider uppercase">
              事务名称
            </label>
            <input
              type="text"
              required
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="例如: 安全备份与防壁校验..."
              className="w-full rounded-lg border border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] py-2 pr-3 pl-3 text-xs text-[var(--db-text-main)] transition-all outline-none placeholder:text-slate-400 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
            />
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="db-text-muted font-cyber mb-1 block text-[10px] tracking-wider uppercase">
                启动时间
              </label>
              <div className="relative">
                <input
                  type="time"
                  required
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] py-2 pr-2 pl-3 text-xs text-[var(--db-text-main)] transition-all outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-60 [&::-webkit-calendar-picker-indicator]:brightness-[.95] [&::-webkit-calendar-picker-indicator]:hue-rotate-[160deg] [&::-webkit-calendar-picker-indicator]:invert-[.5] [&::-webkit-calendar-picker-indicator]:saturate-[10] [&::-webkit-calendar-picker-indicator]:sepia-[.3] [&::-webkit-calendar-picker-indicator]:filter [&::-webkit-calendar-picker-indicator]:hover:opacity-100"
                />
              </div>
            </div>
            <div>
              <label className="db-text-muted font-cyber mb-1 block text-[10px] tracking-wider uppercase">
                事务属性
              </label>
              <Select
                value={newType}
                onValueChange={(v) => setNewType(v as CalendarEvent["type"])}
              >
                <SelectTrigger className="h-auto w-full rounded-lg border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] px-3 py-2 font-sans text-xs text-[var(--db-text-main)] focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="z-[1010] border-[var(--db-border-color)] bg-[var(--db-bg-secondary)] font-sans text-xs text-[var(--db-text-main)]">
                  <SelectItem value="milestone">里程碑</SelectItem>
                  <SelectItem value="deadline">截止日期</SelectItem>
                  <SelectItem value="phase_start">阶段开始</SelectItem>
                  <SelectItem value="personal">个人事项</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="w-full cursor-pointer rounded border border-blue-400/20 bg-blue-600 py-1.5 text-xs font-bold text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? "确立中..." : "确立规划"}
          </button>
        </form>
      )}

      {/* Month swiper */}
      <div className="mb-3.5 flex items-center justify-between px-1 select-none">
        <button
          onClick={prevMonth}
          className="flex cursor-pointer items-center rounded border border-[var(--db-border-color-muted)] bg-slate-400/5 p-1 text-slate-500 transition-colors hover:text-blue-500"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <div className="font-cyber db-text-primary text-xs font-bold">
          {currentYear}年{MONTHS[currentMonth]}
        </div>
        <button
          onClick={nextMonth}
          className="flex cursor-pointer items-center rounded border border-[var(--db-border-color-muted)] bg-slate-400/5 p-1 text-slate-500 transition-colors hover:text-blue-500"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Weekday headers */}
      <div className="font-cyber mb-1.5 grid grid-cols-7 gap-1 text-center text-[10px] font-bold text-slate-500 select-none">
        {WEEKDAYS.map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>

      {/* Day grid */}
      <div className="font-cyber grid grid-cols-7 gap-1 text-center text-xs select-none">
        {Array.from({ length: leadingBlanks }).map((_, i) => (
          <div key={`blank-${i}`} className="py-1.5" />
        ))}
        {daysArray.map((day) => {
          const key = dateKey(currentYear, currentMonth, day);
          const hasEvents = !!eventsByDate[key];
          const today = new Date();
          const isToday =
            day === today.getDate() &&
            currentMonth === today.getMonth() &&
            currentYear === today.getFullYear();
          const isSelected = day === selectedDay;
          return (
            <div
              key={`day-${day}`}
              onClick={() => setSelectedDay(day)}
              className={`relative flex cursor-pointer flex-col items-center justify-center rounded-md py-1.5 transition-all ${
                isSelected
                  ? "border border-blue-400/30 bg-blue-600 font-bold text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]"
                  : isToday
                    ? "bg-slate-400/15 font-bold text-blue-600"
                    : "db-text-muted hover:bg-slate-400/10"
              }`}
            >
              <span>{day}</span>
              {hasEvents && (
                <span
                  className={`absolute bottom-1 h-1 w-1 rounded-full ${isSelected ? "bg-white" : "animate-pulse bg-blue-500 shadow-[0_0_4px_#22d3ee]"}`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Selected date panel */}
      <div className="mt-3.5 flex flex-col border-t border-[var(--db-border-color-muted)] pt-3.5">
        <div className="font-cyber flex items-center justify-between text-[11px] text-slate-500">
          <span>SELECTED DATE</span>
          <span className="font-bold text-blue-600">
            {currentMonth + 1}月{selectedDay}日
          </span>
        </div>
        <div className="mt-2 flex min-h-[50px] flex-col gap-2">
          {dayEvents.length === 0 ? (
            <div className="flex items-center justify-center gap-2 rounded border border-dashed border-[var(--db-border-color-muted)] bg-slate-400/5 p-2.5">
              <ShieldCheck className="h-3.5 w-3.5 text-slate-400" />
              <p className="text-[11px] text-slate-500 italic">
                暂无事项 PROTOCOL STANDBY
              </p>
            </div>
          ) : (
            dayEvents.map((ev) => (
              <Link
                key={ev.id}
                href={ev.project_id ? `/projects/${ev.project_id}` : "#"}
                className={`flex flex-col gap-1 rounded border p-2.5 text-xs no-underline ${
                  ev.type === "deadline"
                    ? "border-red-500/20 bg-red-500/5"
                    : ev.type === "milestone"
                      ? "border-purple-500/20 bg-purple-500/5"
                      : ev.type === "phase_start"
                        ? "border-blue-500/20 bg-blue-500/5"
                        : "border-[var(--db-border-color-muted)] bg-slate-400/5"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[8px] font-bold uppercase ${
                      ev.type === "deadline"
                        ? "bg-red-500/10 text-red-600"
                        : ev.type === "milestone"
                          ? "bg-purple-500/10 text-purple-600"
                          : ev.type === "phase_start"
                            ? "bg-blue-500/10 text-blue-600"
                            : "bg-blue-500/10 text-blue-600"
                    }`}
                  >
                    {ev.type === "deadline"
                      ? "截止"
                      : ev.type === "milestone"
                        ? "里程碑"
                        : ev.type === "phase_start"
                          ? "阶段"
                          : "个人"}
                  </span>
                </div>
                <h4 className="db-text-primary mt-0.5 text-[11px] font-semibold">
                  {ev.title}
                </h4>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
