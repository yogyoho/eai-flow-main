"use client";

import { Calendar, ChevronLeft, ChevronRight, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { useMyCalendar } from "../hooks/useMyCalendar";
import { dashboardApi } from "../api";
import type { CalendarEvent } from "../types";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const MONTHS = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];

function dateKey(y: number, m: number, d: number) {
  return `${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
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
  const events = data?.events || [];

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};
    for (const ev of events) {
      const d = new Date(ev.date);
      const k = dateKey(d.getFullYear(), d.getMonth(), d.getDate());
      if (!map[k]) map[k] = [];
      map[k].push(ev);
    }
    return map;
  }, [events]);

  const selectedDateStr = dateKey(currentYear, currentMonth, selectedDay);
  const dayEvents = eventsByDate[selectedDateStr] || [];

  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const daysArray = Array.from({ length: daysInMonth }, (_, i) => i + 1);
  const firstDay = new Date(currentYear, currentMonth, 1).getDay();
  const leadingBlanks = firstDay === 0 ? 6 : firstDay - 1;

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(y => y - 1); }
    else setCurrentMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(y => y + 1); }
    else setCurrentMonth(m => m + 1);
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
      queryClient.invalidateQueries({ queryKey: ["dashboard", "my-calendar"] });
    } catch {
      toast.error("添加日程失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  if (!mounted) {
    return <div className="h-40 flex items-center justify-center text-xs text-slate-500 animate-pulse">加载中...</div>;
  }

  return (
    <div className="flex flex-col">
      {/* Header — reference SpaceCalendar */}
      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
            <Calendar className="w-4 h-4 animate-pulse" />
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            日程 <span className="text-xs font-normal text-slate-500">Scheduler</span>
          </h2>
        </div>
        <button
          onClick={() => setScheduleOpen(!scheduleOpen)}
          className="text-xs text-blue-600 hover:text-blue-500 font-cyber flex items-center gap-1 cursor-pointer font-bold">
          {scheduleOpen ? "✖ 关闭" : "✚ 添加日程"}
        </button>
      </div>

      {/* Add Event Form — reference SpaceCalendar schedule form */}
      {scheduleOpen && (
        <form onSubmit={handleAddEvent}
          className="mb-4 p-3 border border-blue-500/20 bg-blue-500/5 rounded-lg text-xs flex flex-col gap-2.5 overflow-hidden">
          <h4 className="font-bold text-blue-600">安排于 {selectedDay}日 运作议程</h4>
          <div>
            <label className="block db-text-muted mb-1 text-[10px] uppercase tracking-wider font-cyber">事务名称</label>
            <input type="text" required value={newTitle} onChange={e => setNewTitle(e.target.value)}
              placeholder="例如: 安全备份与防壁校验..."
              className="w-full bg-[var(--db-bg-tertiary)] border border-[var(--db-border-color-muted)] rounded-lg pl-3 pr-3 py-2 text-[var(--db-text-main)] outline-none text-xs focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all placeholder:text-slate-400" />
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block db-text-muted mb-1 text-[10px] uppercase tracking-wider font-cyber">启动时间</label>
              <div className="relative">
                <input type="time" required value={newTime} onChange={e => setNewTime(e.target.value)}
                  className="w-full bg-[var(--db-bg-tertiary)] border border-[var(--db-border-color-muted)] rounded-lg pl-3 pr-2 py-2 text-[var(--db-text-main)] outline-none text-xs focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all appearance-none
                    [&::-webkit-calendar-picker-indicator]:opacity-60 [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:hover:opacity-100 [&::-webkit-calendar-picker-indicator]:filter [&::-webkit-calendar-picker-indicator]:invert-[.5] [&::-webkit-calendar-picker-indicator]:sepia-[.3] [&::-webkit-calendar-picker-indicator]:saturate-[10] [&::-webkit-calendar-picker-indicator]:hue-rotate-[160deg] [&::-webkit-calendar-picker-indicator]:brightness-[.95]" />
              </div>
            </div>
            <div>
              <label className="block db-text-muted mb-1 text-[10px] uppercase tracking-wider font-cyber">事务属性</label>
              <Select value={newType} onValueChange={(v) => setNewType(v as CalendarEvent["type"])}>
                <SelectTrigger className="w-full bg-[var(--db-bg-tertiary)] border-[var(--db-border-color-muted)] rounded-lg h-auto py-2 px-3 text-xs text-[var(--db-text-main)] focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 font-sans">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="z-[1010] bg-[var(--db-bg-secondary)] border-[var(--db-border-color)] text-[var(--db-text-main)] text-xs font-sans">
                  <SelectItem value="milestone">里程碑</SelectItem>
                  <SelectItem value="deadline">截止日期</SelectItem>
                  <SelectItem value="phase_start">阶段开始</SelectItem>
                  <SelectItem value="personal">个人事项</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <button type="submit" disabled={saving}
            className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 border border-blue-400/20 text-white font-bold rounded cursor-pointer text-xs transition-colors">
            {saving ? "确立中..." : "确立规划"}
          </button>
        </form>
      )}

      {/* Month swiper */}
      <div className="flex items-center justify-between px-1 mb-3.5 select-none">
        <button onClick={prevMonth}
          className="text-slate-500 hover:text-blue-500 p-1 bg-slate-400/5 rounded flex items-center transition-colors cursor-pointer border border-[var(--db-border-color-muted)]">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <div className="text-xs font-bold font-cyber db-text-primary">{currentYear}年{MONTHS[currentMonth]}</div>
        <button onClick={nextMonth}
          className="text-slate-500 hover:text-blue-500 p-1 bg-slate-400/5 rounded flex items-center transition-colors cursor-pointer border border-[var(--db-border-color-muted)]">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 text-center mb-1.5 font-cyber text-[10px] text-slate-500 font-bold select-none">
        {WEEKDAYS.map(d => <div key={d}>{d}</div>)}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-1 text-center font-cyber select-none text-xs">
        {Array.from({ length: leadingBlanks }).map((_, i) => (
          <div key={`blank-${i}`} className="py-1.5" />
        ))}
        {daysArray.map(day => {
          const key = dateKey(currentYear, currentMonth, day);
          const hasEvents = !!eventsByDate[key];
          const today = new Date();
          const isToday = day === today.getDate() && currentMonth === today.getMonth() && currentYear === today.getFullYear();
          const isSelected = day === selectedDay;
          return (
            <div key={`day-${day}`} onClick={() => setSelectedDay(day)}
              className={`relative py-1.5 rounded-md flex flex-col items-center justify-center cursor-pointer transition-all ${
                isSelected
                  ? "bg-blue-600 text-white font-bold shadow-[0_0_10px_rgba(37,99,235,0.4)] border border-blue-400/30"
                  : isToday
                  ? "bg-slate-400/15 text-blue-600 font-bold"
                  : "db-text-muted hover:bg-slate-400/10"
              }`}>
              <span>{day}</span>
              {hasEvents && (
                <span className={`w-1 h-1 rounded-full absolute bottom-1 ${isSelected ? "bg-white" : "bg-blue-500 animate-pulse shadow-[0_0_4px_#22d3ee]"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Selected date panel */}
      <div className="border-t border-[var(--db-border-color-muted)] pt-3.5 mt-3.5 flex flex-col">
        <div className="flex items-center justify-between text-[11px] text-slate-500 font-cyber">
          <span>SELECTED DATE</span>
          <span className="text-blue-600 font-bold">{currentMonth + 1}月{selectedDay}日</span>
        </div>
        <div className="mt-2 min-h-[50px] flex flex-col gap-2">
          {dayEvents.length === 0 ? (
            <div className="flex items-center gap-2 p-2.5 rounded bg-slate-400/5 border border-dashed border-[var(--db-border-color-muted)] justify-center">
              <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
              <p className="text-[11px] text-slate-500 italic">暂无事项 PROTOCOL STANDBY</p>
            </div>
          ) : (
            dayEvents.map(ev => (
              <Link key={ev.id} href={ev.project_id ? `/projects/${ev.project_id}` : "#"}
                className={`p-2.5 rounded border text-xs flex flex-col gap-1 no-underline ${
                  ev.type === "deadline" ? "bg-red-500/5 border-red-500/20" :
                  ev.type === "milestone" ? "bg-purple-500/5 border-purple-500/20" :
                  ev.type === "phase_start" ? "bg-blue-500/5 border-blue-500/20" :
                  "bg-slate-400/5 border-[var(--db-border-color-muted)]"
                }`}>
                <div className="flex items-center justify-between">
                  <span className={`px-1.5 py-0.5 rounded text-[8px] uppercase font-bold ${
                    ev.type === "deadline" ? "bg-red-500/10 text-red-600" :
                    ev.type === "milestone" ? "bg-purple-500/10 text-purple-600" :
                    ev.type === "phase_start" ? "bg-blue-500/10 text-blue-600" :
                    "bg-blue-500/10 text-blue-600"
                  }`}>
                    {ev.type === "deadline" ? "截止" : ev.type === "milestone" ? "里程碑" : ev.type === "phase_start" ? "阶段" : "个人"}
                  </span>
                </div>
                <h4 className="font-semibold db-text-primary mt-0.5 text-[11px]">{ev.title}</h4>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
