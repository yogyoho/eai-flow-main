"use client";

import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
}

// themed-card-sci:cyber 浅色科技感卡片面
export function ChartCard({ title, meta, children, className }: ChartCardProps) {
  return (
    <div
      className={
        "themed-card-sci rounded-xl border border-border/60 bg-card/80 p-5 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] backdrop-blur-sm " +
        (className ?? "")
      }
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-cyber text-sm font-semibold tracking-wide text-muted-foreground">{title}</h3>
        {meta ? (
          <span className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-0.5 text-[11px] font-bold text-primary">
            {meta}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}
