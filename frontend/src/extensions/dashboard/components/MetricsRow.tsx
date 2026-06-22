"use client";

import { BarChart3, Radio, Eye, AlertCircle, RefreshCw } from "lucide-react";
import type { MyStatsResponse } from "../types";

interface MetricsRowProps {
  data?: MyStatsResponse;
  loading: boolean;
  onRefresh: () => void;
}

export function MetricsRow({ data, loading, onRefresh }: MetricsRowProps) {
  if (!data) return null;

  const cards = [
    { label: "进行中项目", sub: "Active Projects", value: data.projects_count, color: "text-blue-600", borderTheme: "border-blue-500/20 bg-blue-500/5", icon: <Radio className="w-4 h-4 text-blue-500 animate-pulse" /> },
    { label: "待审核项目", sub: "Pending Review", value: data.pending_reviews, color: "text-amber-600", borderTheme: "border-amber-500/20 bg-amber-500/5", icon: <Eye className="w-4 h-4 text-amber-500" /> },
    { label: "待处理待办", sub: "Pending Action", value: data.pending_writing, color: "text-purple-600", borderTheme: "border-purple-500/20 bg-purple-500/5", icon: <BarChart3 className="w-4 h-4 text-purple-500" /> },
    { label: "严重逾期数", sub: "Overdue", value: data.overdue_count, color: "text-red-600", borderTheme: "border-red-500/20 bg-red-500/5", icon: <AlertCircle className="w-4 h-4 text-red-500 animate-bounce" /> },
  ];

  return (
    <div className="db-card rounded-xl p-4 md:p-5 relative flex flex-col">
      <div className="absolute top-0 right-0 w-2.5 h-2.5 bg-blue-500/15" />

      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
            <BarChart3 className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            我的统计 <span className="text-xs font-normal text-slate-500">Node Statistics</span>
          </h2>
        </div>
        <button onClick={onRefresh} disabled={loading}
          className="p-1.5 rounded-lg border border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] hover:bg-[var(--db-bg-secondary)] text-slate-500 hover:text-blue-500 transition-all cursor-pointer"
          title="重新校准核心指标">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-blue-500" : ""}`} />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card, i) => (
          <div key={i} className={`border rounded-xl p-3.5 flex flex-col justify-between transition-all hover:scale-[1.015] ${card.borderTheme} cursor-default group`}>
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-[11px] md:text-xs font-bold db-text-primary">{card.label}</span>
              <div className={`p-1 rounded-md border ${card.borderTheme}`}>{card.icon}</div>
            </div>
            <div className="my-2 select-all">
              <span className={`text-xl md:text-2xl font-extrabold font-cyber tracking-tight ${card.color}`}>{card.value}</span>
            </div>
            <span className="text-[9px] text-slate-500 font-cyber uppercase tracking-wider">{card.sub}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
