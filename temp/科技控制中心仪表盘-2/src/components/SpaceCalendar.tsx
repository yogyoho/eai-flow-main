/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, AlertTriangle, Plus, ShieldCheck } from "lucide-react";
import { CalendarEvent } from "../types.js";
import { motion, AnimatePresence } from "motion/react";

interface SpaceCalendarProps {
  events: CalendarEvent[];
  onAddEvent: (eventData: { title: string; date: string; time: string; type: CalendarEvent["type"] }) => void;
}

export default function SpaceCalendar({
  events,
  onAddEvent,
}: SpaceCalendarProps) {
  // Representing June 2026 as in the user screenshot
  const [currentYear, setCurrentYear] = useState(2026);
  const [currentMonth, setCurrentMonth] = useState(5); // June is month index 5 (0-indexed)
  const [selectedDay, setSelectedDay] = useState(20); // June 20th highlighted as in mockup
  const [scheduleOpen, setScheduleOpen] = useState(false);

  // New Event Form States
  const [newTitle, setNewTitle] = useState("");
  const [newTime, setNewTime] = useState("10:00");
  const [newType, setNewType] = useState<CalendarEvent["type"]>("meeting");

  const monthNames = [
    "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"
  ];
  
  const weekDays = ["一", "二", "三", "四", "五", "六", "日"];

  // Helper to construct dates for June 2026 (Starts on Monday June 1)
  // June 2026 has exactly 30 days. Let's build a simple calendar grid.
  const daysInMonth = 30;
  // June 1 2026 is a Monday, so offset is 0 for starting index
  const daysArray = Array.from({ length: daysInMonth }, (_, i) => i + 1);

  const prevMonthDays = [29, 30, 31]; // padding preceding June (3 days from May to fill grid)
  const nextMonthDays = [1, 2, 3, 4, 5]; // padding succeeding June

  const getFullDateString = (day: number) => {
    const yearStr = currentYear;
    const monthStr = String(currentMonth + 1).padStart(2, "0");
    const dayStr = String(day).padStart(2, "0");
    return `${yearStr}-${monthStr}-${dayStr}`;
  };

  const selectedDateStr = getFullDateString(selectedDay);
  const dayEvents = events.filter(e => e.date === selectedDateStr);

  const handleDayClick = (day: number) => {
    setSelectedDay(day);
  };

  const handlePrevMonth = () => {
    // Keep bounded around June 2026 for mock stability, or cycle
    if (currentMonth === 5) {
      setCurrentMonth(4);
    } else {
      setCurrentMonth(5);
    }
  };

  const handleNextMonth = () => {
    if (currentMonth === 5) {
      setCurrentMonth(6);
    } else {
      setCurrentMonth(5);
    }
  };

  const handleEventFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    onAddEvent({
      title: newTitle,
      date: selectedDateStr,
      time: newTime,
      type: newType
    });
    setNewTitle("");
    setScheduleOpen(false);
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-5 relative flex flex-col hover:border-slate-400/20 transition-colors shadow-lg">
      {/* Decorative calibration mark */}
      <div className="absolute top-0 right-0 w-3 h-3 bg-cyan-500/10 border-r border-t border-cyan-500/25" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-500 rounded-md">
            <Calendar className="w-4 h-4 animate-pulse" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            日程 <span className="text-xs font-normal text-slate-500">Scheduler</span>
          </h2>
        </div>

        <button
          onClick={() => setScheduleOpen(!scheduleOpen)}
          className="text-xs text-cyan-555 hover:text-cyan-600 font-cyber flex items-center gap-1 mt-0.5 cursor-pointer font-bold"
        >
          {scheduleOpen ? "✖ 关闭" : "✚ 添加日程"}
        </button>
      </div>

      {/* Monthly Control Swiper */}
      <div className="flex items-center justify-between px-1 mb-3.5 select-none font-sans">
        <button
          onClick={handlePrevMonth}
          className="text-slate-500 hover:text-cyan-500 p-1 bg-slate-400/5 rounded flex items-center transition-colors cursor-pointer border border-[var(--border-color-muted)]"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <div className="text-xs font-bold font-cyber text-[var(--text-main)]">
          {currentYear}年{monthNames[currentMonth]}
        </div>
        <button
          onClick={handleNextMonth}
          className="text-slate-500 hover:text-cyan-500 p-1 bg-slate-400/5 rounded flex items-center transition-colors cursor-pointer border border-[var(--border-color-muted)]"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Event Schedule Form Overlay */}
      <AnimatePresence>
        {scheduleOpen && (
          <motion.form
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            onSubmit={handleEventFormSubmit}
            className="mb-4 p-3 border border-cyan-500/20 bg-cyan-500/5 rounded-lg text-xs flex flex-col gap-2.5 overflow-hidden font-sans"
          >
            <h4 className="font-bold text-cyan-600 dark:text-cyan-400">安排于 {selectedDay}日 运作议程</h4>
            <div>
              <label className="block text-[var(--text-muted)] mb-0.5">事务名称</label>
              <input
                type="text"
                required
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="例如: 安全备份与防壁校验..."
                className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded px-2 py-1 text-[var(--text-main)] outline-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[var(--text-muted)] mb-0.5">启动时间</label>
                <input
                  type="time"
                  required
                  value={newTime}
                  onChange={e => setNewTime(e.target.value)}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded px-2 py-1 text-[var(--text-main)] outline-none"
                />
              </div>
              <div>
                <label className="block text-[var(--text-muted)] mb-0.5">事务属性</label>
                <select
                  value={newType}
                  onChange={e => setNewType(e.target.value as CalendarEvent["type"])}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded px-2 py-1 text-[var(--text-main)] outline-none cursor-pointer"
                >
                  <option value="meeting">协作审计 (Meeting)</option>
                  <option value="deployment">节点部署 (Deployment)</option>
                  <option value="security">壁垒校验 (Security)</option>
                  <option value="review">周期审计 (Review)</option>
                </select>
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-1.5 bg-cyan-600 hover:bg-cyan-500 border border-cyan-400/20 text-white font-bold rounded cursor-pointer"
            >
              确立规划
            </button>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Grid Days Headers (一 二 三 四 五 六 日) */}
      <div className="grid grid-cols-7 gap-1 text-center mb-1.5 font-cyber text-[10px] text-slate-505 dark:text-slate-500 font-bold select-none">
        {weekDays.map(d => (
          <div key={d}>{d}</div>
        ))}
      </div>

      {/* Number Calendars Grid */}
      <div className="grid grid-cols-7 gap-1 text-center font-cyber select-none text-xs">
        {/* Render June 2026 starting directly on Monday (0 offsets) */}
        {daysArray.map(day => {
          const formattedStr = getFullDateString(day);
          const hasEvents = events.some(e => e.date === formattedStr);
          const isToday = day === 20 && currentMonth === 5; // June 20th today
          const isSelected = day === selectedDay;

          return (
            <div
              key={`day-${day}`}
              onClick={() => handleDayClick(day)}
              className={`relative py-1.5 rounded-md flex flex-col items-center justify-center cursor-pointer transition-all ${
                isSelected
                  ? "bg-blue-600 text-white font-bold shadow-[0_0_10px_rgba(37,99,235,0.4)] border border-blue-400/30"
                  : isToday
                  ? "bg-slate-400/15 dark:bg-slate-800 text-cyan-600 dark:text-cyan-400 font-bold"
                  : "text-[var(--text-muted)] hover:bg-slate-400/10"
              }`}
            >
              <span>{day}</span>
              
              {/* Event indicators dot glow */}
              {hasEvents && (
                <span className={`w-1 h-1 rounded-full absolute bottom-1 ${isSelected ? "bg-white" : "bg-cyan-500 animate-pulse shadow-[0_0_4px_#22d3ee]"}`} />
              )}
            </div>
          );
        })}

        {/* Empty cells next month padding */}
        {nextMonthDays.map(day => (
          <div key={`next-${day}`} className="py-1 text-slate-505/40 dark:text-slate-700/60 font-normal">
            {day}
          </div>
        ))}
      </div>

      {/* Event Details Panel */}
      <div className="border-t border-[var(--border-color-muted)] pt-3.5 mt-3.5 flex flex-col font-sans">
        <div className="flex items-center justify-between text-[11px] text-slate-505 dark:text-slate-500 font-cyber">
          <span>SELECTED DATE</span>
          <span className="text-cyan-600 dark:text-cyan-400 font-bold ">{currentMonth + 1}月{selectedDay}日</span>
        </div>

        {/* Event List for selection */}
        <div className="mt-2 min-h-[50px] flex flex-col gap-2">
          {dayEvents.length === 0 ? (
            // Match mock calendar empty phrase
            <div className="flex items-center gap-2 p-2.5 rounded bg-slate-400/5 border border-dashed border-[var(--border-color-muted)] justify-center">
              <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
              <p className="text-[11px] text-slate-505 dark:text-slate-500 italic">暂无事项 PROTOCOL STANDBY</p>
            </div>
          ) : (
            dayEvents.map(event => (
              <div
                key={event.id}
                className={`p-2.5 rounded border text-xs flex flex-col gap-1 ${
                  event.type === "security" ? "bg-red-500/5 border-red-500/20" :
                  event.type === "deployment" ? "bg-purple-500/5 border-purple-500/20" :
                  "bg-slate-400/5 border-[var(--border-color-muted)]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`px-1.5 py-0.5 rounded text-[8px] uppercase font-bold ${
                    event.type === "security" ? "bg-red-500/10 text-red-550 dark:text-red-400" :
                    event.type === "deployment" ? "bg-purple-500/10 text-purple-555 dark:text-purple-400" :
                    "bg-slate-400/15 text-[var(--text-muted)]"
                  }`}>
                    {event.type}
                  </span>
                  <span className="text-[10px] text-slate-500 font-cyber font-bold">{event.time}</span>
                </div>
                <h4 className="font-semibold text-[var(--text-main)] mt-0.5">
                  {event.title}
                </h4>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
