"use client";

import { FolderKanban, SearchCheck, PenTool, AlertTriangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { MyStatsResponse } from "../types";

interface StatItem {
  label: string;
  sub: string;
  value: number;
  icon: LucideIcon;
  containerClass: string;
  valueClass: string;
}

export function StatsPanel({ data }: { data?: MyStatsResponse }) {
  if (!data) return null;

  const stats: StatItem[] = [
    {
      label: "进行中项目",
      sub: "Active Projects",
      value: data.projects_count,
      icon: FolderKanban,
      containerClass: "border-blue-500/20 bg-blue-500/5",
      valueClass: "text-blue-600",
    },
    {
      label: "待审核",
      sub: "Pending Review",
      value: data.pending_reviews,
      icon: SearchCheck,
      containerClass: "border-amber-500/20 bg-amber-500/5",
      valueClass: "text-amber-600",
    },
    {
      label: "待编写",
      sub: "Pending Writing",
      value: data.pending_writing,
      icon: PenTool,
      containerClass: "border-violet-500/20 bg-violet-500/5",
      valueClass: "text-violet-600",
    },
    {
      label: "逾期",
      sub: "Overdue",
      value: data.overdue_count,
      icon: AlertTriangle,
      containerClass: "border-rose-500/20 bg-rose-500/5",
      valueClass: "text-rose-600",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((item) => {
        const Icon = item.icon;
        return (
          <div
            key={item.label}
            className={`flex items-center gap-4 rounded-xl border p-4 bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md cursor-default ${item.containerClass}`}
          >
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border bg-background ${item.valueClass}`}>
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className={`text-2xl font-extrabold leading-none tracking-tight ${item.valueClass}`}>
                {item.value}
              </p>
              <p className="text-xs font-medium text-muted-foreground mt-1">{item.label}</p>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5 uppercase tracking-wider font-medium">{item.sub}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
