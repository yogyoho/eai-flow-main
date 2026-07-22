/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from "react";
import { BarChart3, Radio, Eye, AlertCircle, RefreshCw } from "lucide-react";
import { SystemMetrics, DynamicTelemetry } from "../types.js";
import { motion } from "motion/react";

interface MetricsTelemetryProps {
  metrics: SystemMetrics;
  telemetry: DynamicTelemetry;
  loading: boolean;
  onRefresh: () => void;
}

export default function MetricsTelemetry({
  metrics,
  telemetry,
  loading,
  onRefresh,
}: MetricsTelemetryProps) {
  // Metric configurations matching the 4 boxes in user screenshot
  const statCards = [
    {
      label: "进行中项目",
      sub: "Active Projects",
      value: metrics.activeProjects,
      textStyle: "text-blue-605 dark:text-blue-400 text-shadow-glow",
      borderTheme: "border-blue-500/20 bg-blue-500/5 dark:bg-blue-950/10",
      pillStyle: "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400",
      icon: <Radio className="w-4 h-4 text-blue-500 animate-pulse" />
    },
    {
      label: "待审核项目",
      sub: "Pending Review",
      value: metrics.pendingReviews,
      textStyle: "text-amber-600 dark:text-amber-400",
      borderTheme: "border-amber-500/20 bg-amber-500/5 dark:bg-amber-950/10",
      pillStyle: "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
      icon: <Eye className="w-4 h-4 text-amber-500" />
    },
    {
      label: "待处理待办",
      sub: "Pending Action",
      value: metrics.draftsInProgress,
      textStyle: "text-purple-600 dark:text-purple-400",
      borderTheme: "border-purple-500/20 bg-purple-500/5 dark:bg-purple-950/10",
      pillStyle: "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400",
      icon: <BarChart3 className="w-4 h-4 text-purple-500" />
    },
    {
      label: "严重逾期数",
      sub: "Overdue Protocols",
      value: metrics.overdueTasks,
      textStyle: "text-red-550 dark:text-red-400",
      borderTheme: "border-red-500/20 bg-red-500/5 dark:bg-red-950/10",
      pillStyle: "bg-red-500/15 border-red-500/30 text-red-500 dark:text-red-400",
      icon: <AlertCircle className="w-4 h-4 text-red-500 animate-bounce" />
    }
  ];

  return (
    <div className="themed-card rounded-xl p-4 md:p-5 relative flex flex-col transition-colors duration-300">
      <div className="absolute top-0 right-0 w-2.5 h-2.5 bg-cyan-500/15" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
            <BarChart3 className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5 font-bold">
            我的统计 <span className="text-xs font-normal text-slate-500">Node Statistics</span>
          </h2>
        </div>

        {/* Live sync loader icon */}
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded-lg border border-[var(--border-color-muted)] bg-[var(--bg-tertiary)] hover:bg-[var(--bg-secondary)] hover:border-[var(--text-muted)] text-slate-550 hover:text-cyan-555 transition-all cursor-pointer"
          title="重新校准核心指标"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-555" : ""}`} />
        </button>
      </div>

      {/* 4 Cards Grid - Laid out in 1x4 horizontal configuration */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {statCards.map((card, i) => (
          <div
            key={i}
            className={`border rounded-xl p-3.5 flex flex-col justify-between transition-all hover:scale-[1.015] ${card.borderTheme} cursor-default group`}
          >
            {/* Upper label row */}
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-[11px] md:text-xs font-bold text-[var(--text-main)] font-sans">
                {card.label}
              </span>
              <div className={`p-1 rounded-md border ${card.pillStyle}`}>
                {card.icon}
              </div>
            </div>

            {/* Metric Value */}
            <div className="my-2 select-all">
              <span className={`text-2xl md:text-3.5xl font-extrabold font-cyber tracking-tight ${card.textStyle}`}>
                {card.value}
              </span>
            </div>

            {/* Info sub */}
            <span className="text-[9px] text-slate-550 dark:text-slate-500 font-cyber uppercase tracking-wider">
              {card.sub}
            </span>
          </div>
        ))}
      </div>

      {/* Telemetry status meters - laid out side-by-side on larger screens */}
      <div className="border-t border-[var(--border-color-muted)] pt-3.5 flex flex-col md:flex-row gap-4 md:gap-8 font-cyber text-[10px] text-slate-500">
        <div className="flex-1 flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[9px] md:text-[10px] uppercase tracking-wider text-slate-555 dark:text-slate-550 header-glow">SYS RESOURCE ALLOCATION LOAD</span>
            <span className="text-cyan-600 dark:text-cyan-400 font-bold font-mono">{telemetry.cpuUsage}% CPU USED</span>
          </div>
          <div className="w-full h-1 bg-slate-100 dark:bg-slate-850 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500"
              animate={{ width: `${telemetry.cpuUsage}%` }}
              transition={{ duration: 1 }}
            />
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-1.5">
          <div className="flex items-center justify-between font-mono">
            <span className="text-[9px] md:text-[10px] uppercase tracking-wider text-slate-555 dark:text-slate-550 header-glow">MEM DOCK INTEGRITY</span>
            <span className="text-purple-600 dark:text-purple-400 font-bold">{telemetry.memoryUsage}% CACHE COMMITTED</span>
          </div>
          <div className="w-full h-1 bg-slate-100 dark:bg-slate-850 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-purple-500 to-indigo-500"
              animate={{ width: `${telemetry.memoryUsage}%` }}
              transition={{ duration: 1 }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
