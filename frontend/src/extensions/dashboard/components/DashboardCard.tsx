"use client";

import { type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";

interface DashboardCardProps {
  title: string;
  icon?: LucideIcon;
  iconColor?: string;
  badge?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function DashboardCard({
  title,
  icon: Icon,
  iconColor,
  badge,
  action,
  children,
  className = "",
}: DashboardCardProps) {
  return (
    <div className={`rounded-xl border border-border bg-card shadow-sm ${className}`}>
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/60">
        <div className="flex items-center gap-2.5">
          {Icon && (
            <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${iconColor || "bg-muted text-muted-foreground border-border"}`}>
              <Icon className="h-3.5 w-3.5" />
            </div>
          )}
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {badge}
        </div>
        {action}
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}
