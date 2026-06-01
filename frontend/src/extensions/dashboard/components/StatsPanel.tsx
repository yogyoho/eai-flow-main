"use client";

import { useMyStats } from "../hooks/useMyStats";

export function StatsPanel() {
  const { data } = useMyStats();

  if (!data) return null;

  const stats = [
    { label: "进行中项目", value: data.projects_count, color: "text-primary" },
    { label: "待审核", value: data.pending_reviews, color: "text-amber-500" },
    { label: "待编写", value: data.pending_writing, color: "text-blue-500" },
    { label: "逾期", value: data.overdue_count, color: "text-red-500" },
  ];

  return (
    <div className="space-y-3">
      {stats.map((s) => (
        <div key={s.label} className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{s.label}</span>
          <span className={`text-lg font-semibold ${s.color}`}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}
