"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface ChartCardProps {
  title: string;
  meta?: string;
  /** 标题行右侧操作区(meta 徽标旁),放每图筛选 Popover 等控件。 */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

// themed-card-sci:cyber 浅色科技感卡片面
export function ChartCard({
  title,
  meta,
  action,
  children,
  className,
}: ChartCardProps) {
  return (
    <div
      className={cn(
        "themed-card-sci border-border/60 bg-card/80 rounded-xl border p-5 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] backdrop-blur-sm",
        className,
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-cyber text-muted-foreground text-sm font-semibold tracking-wide">
          {title}
        </h3>
        <div className="flex items-center gap-2">
          {action}
          {meta ? (
            <span className="border-primary/20 bg-primary/5 text-primary rounded-full border px-2.5 py-0.5 text-[11px] font-bold">
              {meta}
            </span>
          ) : null}
        </div>
      </div>
      {children}
    </div>
  );
}
