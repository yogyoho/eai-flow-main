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
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div
            key={s.label}
            className={`flex items-center gap-3 rounded-lg border border-border p-3 ${s.bg}`}
          >
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/70 ${s.color}`}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className={`text-lg font-semibold leading-tight ${s.color}`}>{s.value}</p>
              <p className="text-[11px] text-muted-foreground truncate">{s.label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
