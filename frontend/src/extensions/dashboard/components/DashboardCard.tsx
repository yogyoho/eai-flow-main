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
  collapsible?: boolean;
  defaultCollapsed?: boolean;
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
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          {Icon && <Icon className={`h-4 w-4 ${iconColor || "text-muted-foreground"}`} />}
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          {badge}
        </div>
        {action}
      </div>
      <div className="px-5 pb-5">{children}</div>
    </div>
  );
}
