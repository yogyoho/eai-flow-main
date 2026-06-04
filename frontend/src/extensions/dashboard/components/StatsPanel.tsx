"use client";

import { FolderKanban, SearchCheck, PenTool, AlertTriangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMyStats } from "../hooks/useMyStats";

interface StatItem {
  label: string;
  value: number;
  color: string;
  bg: string;
  icon: LucideIcon;
}

export function StatsPanel() {
  const { data } = useMyStats();

  if (!data) return null;

  const stats: StatItem[] = [
    { label: "进行中项目", value: data.projects_count, color: "text-blue-600", bg: "bg-blue-50", icon: FolderKanban },
    { label: "待审核", value: data.pending_reviews, color: "text-amber-600", bg: "bg-amber-50", icon: SearchCheck },
    { label: "待编写", value: data.pending_writing, color: "text-violet-600", bg: "bg-violet-50", icon: PenTool },
    { label: "逾期", value: data.overdue_count, color: "text-rose-600", bg: "bg-rose-50", icon: AlertTriangle },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className={`flex flex-col items-center gap-1 rounded-lg border border-border p-3 ${s.bg}`}
        >
          <s.icon className={`h-4 w-4 ${s.color}`} />
          <span className={`text-lg font-semibold ${s.color}`}>{s.value}</span>
          <span className="text-[11px] text-muted-foreground">{s.label}</span>
        </div>
      ))}
    </div>
  );
}
