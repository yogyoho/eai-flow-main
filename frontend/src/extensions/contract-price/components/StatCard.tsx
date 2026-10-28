"use client";

import { cn } from "@/lib/utils";

type StatTone = "default" | "accent" | "warn";

interface StatCardProps {
  label: string;
  value: string | number;
  /** 数值后缀小字（如「份」「条」）。 */
  hint?: string;
  /** accent = 左侧 2px 主色竖条；warn = 数值用警示橙（amber-600，warning 500 对比度不足）。 */
  tone?: StatTone;
}

/**
 * 指标格（cpa UI 重构规范 §2-2）。
 * EAI-CUSTOM: 视觉习语取自 2026-10-12 eia-p2 原型 .metric-cell —— 无图标、
 * label 12px muted 在上 / 数值 22px bold tabular-nums 在下；原 icon/color API 已移除。
 */
export function StatCard({ label, value, hint, tone = "default" }: StatCardProps) {
  return (
    <div
      className={cn(
        "border-border bg-card relative flex flex-col gap-0.5 rounded-md border px-[18px] py-3",
        tone === "accent" &&
          "before:bg-primary before:absolute before:top-3 before:bottom-3 before:left-0 before:w-0.5 before:rounded-r-sm before:content-['']",
      )}
    >
      <span className="text-muted-foreground text-xs">{label}</span>
      <span
        className={cn(
          "text-foreground text-2xl leading-[1.1] font-bold tabular-nums",
          tone === "warn" && "text-amber-600 dark:text-amber-400",
        )}
      >
        {value}
        {hint ? (
          <small className="text-muted-foreground ml-1 text-xs font-normal">
            {hint}
          </small>
        ) : null}
      </span>
    </div>
  );
}
