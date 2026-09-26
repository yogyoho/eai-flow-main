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
  blue: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  violet: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  rose: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
};

export function StatCard({ label, value, icon: Icon, hint, color = "blue" }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/20 hover:shadow-md">
      <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]", colorClasses[color])}>
        <Icon className="h-[18px] w-[18px]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-wide text-muted-foreground/60">{label}</p>
        <p className="font-cyber text-2xl font-extrabold tracking-tight text-foreground">{value}</p>
        {hint ? <p className="truncate text-xs text-muted-foreground">{hint}</p> : null}
      </div>
    </div>
  );
}
