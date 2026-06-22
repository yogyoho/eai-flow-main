"use client";

import { cn } from "@/lib/utils";

import type { DomainFilterOption } from "../hooks/useApps";

interface CategoryTabsProps {
  options: DomainFilterOption[];
  active: string;
  onChange: (key: DomainFilterOption["key"]) => void;
}

/**
 * 分类筛选 pills。
 * 使用 role="group" + toggle button 模式（分类筛选改变网格内容，
 * 非切换 tab panel，故不适用 WAI-ARIA Tab 模式）。
 */
export function CategoryTabs({ options, active, onChange }: CategoryTabsProps) {
  return (
    <div
      role="group"
      aria-label="按分类筛选"
      className="flex flex-wrap items-center gap-1.5"
    >
      {options.map((opt) => {
        const isActive = active === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(opt.key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              isActive
                ? "bg-primary text-primary-foreground shadow-sm"
                : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            {opt.label}
            <span
              className={cn(
                "rounded-full px-1.5 text-[10px] tabular-nums",
                isActive
                  ? "bg-primary-foreground/20 text-primary-foreground"
                  : "bg-background/60 text-muted-foreground",
              )}
            >
              {opt.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
