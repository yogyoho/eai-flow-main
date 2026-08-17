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
    {
      label: "进行中项目",
      sub: "Active Projects",
      value: data.projects_count,
      color: "text-blue-600",
      borderTheme: "border-blue-500/20 bg-blue-500/5",
      icon: <Radio className="h-4 w-4 animate-pulse text-blue-500" />,
    },
    {
      label: "待审核项目",
      sub: "Pending Review",
      value: data.pending_reviews,
      color: "text-amber-600",
      borderTheme: "border-amber-500/20 bg-amber-500/5",
      icon: <Eye className="h-4 w-4 text-amber-500" />,
    },
    {
      label: "待处理待办",
      sub: "Pending Action",
      value: data.pending_writing,
      color: "text-purple-600",
      borderTheme: "border-purple-500/20 bg-purple-500/5",
      icon: <BarChart3 className="h-4 w-4 text-purple-500" />,
    },
    {
      label: "严重逾期数",
      sub: "Overdue",
      value: data.overdue_count,
      color: "text-red-600",
      borderTheme: "border-red-500/20 bg-red-500/5",
      icon: <AlertCircle className="h-4 w-4 animate-bounce text-red-500" />,
    },
  ];

  return (
    <div className="db-card relative flex flex-col rounded-xl p-4 md:p-5">
      <div className="absolute top-0 right-0 h-2.5 w-2.5 bg-blue-500/15" />

      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="rounded-md border border-blue-500/20 bg-blue-500/10 p-1.5 text-blue-500">
            <BarChart3 className="h-4 w-4" />
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            我的统计{" "}
            <span className="text-xs font-normal text-slate-500">
              Node Statistics
            </span>
          </h2>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="cursor-pointer rounded-lg border border-[var(--db-border-color-muted)] bg-[var(--db-bg-tertiary)] p-1.5 text-slate-500 transition-all hover:bg-[var(--db-bg-secondary)] hover:text-blue-500"
          title="重新校准核心指标"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${loading ? "animate-spin text-blue-500" : ""}`}
          />
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card, i) => (
          <div
            key={i}
            className={`flex flex-col justify-between rounded-xl border p-3.5 transition-all hover:scale-[1.015] ${card.borderTheme} group cursor-default`}
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="db-text-primary text-[11px] font-bold md:text-xs">
                {card.label}
              </span>
              <div className={`rounded-md border p-1 ${card.borderTheme}`}>
                {card.icon}
              </div>
            </div>
            <div className="my-2 select-all">
              <span
                className={`font-cyber text-xl font-extrabold tracking-tight md:text-2xl ${card.color}`}
              >
                {card.value}
              </span>
            </div>
            <span className="font-cyber text-[9px] tracking-wider text-slate-500 uppercase">
              {card.sub}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
