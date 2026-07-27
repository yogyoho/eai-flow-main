"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StatColor = "blue" | "violet" | "amber" | "rose";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  color?: StatColor;
}

const colorClasses: Record<StatColor, string> = {
  blue: "bg-blue-500/10 text-blue-500",
  violet: "bg-violet-500/10 text-violet-500",
  amber: "bg-amber-500/10 text-amber-500",
  rose: "bg-rose-500/10 text-rose-500",
};

export function StatCard({ label, value, icon: Icon, hint, color = "blue" }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-card p-5 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08),0_1px_3px_rgba(0,0,0,0.05)] transition-all hover:border-primary/35 hover:shadow-[0_10px_30px_-10px_rgba(15,23,42,0.12),0_2px_6px_rgba(0,0,0,0.06)]">
      <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]", colorClasses[color])}>
        <Icon className="h-[18px] w-[18px]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-wide text-muted-foreground/60">{label}</p>
        <p className="text-2xl font-bold tabular-nums text-foreground">{value}</p>
        {hint ? <p className="truncate text-[11px] text-muted-foreground">{hint}</p> : null}
      </div>
    </div>
  );
}
