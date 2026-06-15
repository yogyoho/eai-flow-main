"use client";

import { ArrowDownAZ, LayoutList, Star } from "lucide-react";

import { cn } from "@/lib/utils";

import type { SortMode } from "../types";

interface SortControlProps {
  value: SortMode;
  onChange: (mode: SortMode) => void;
}

const OPTIONS: { value: SortMode; label: string; icon: typeof Star }[] = [
  { value: "default", label: "默认", icon: LayoutList },
  { value: "alphabetical", label: "字母", icon: ArrowDownAZ },
  { value: "favorites-first", label: "收藏优先", icon: Star },
];

/**
 * 排序模式切换 —— SegmentedControl 风格，选中态品牌色高亮。
 * 使用 role="radiogroup" 语义。
 */
export function SortControl({ value, onChange }: SortControlProps) {
  return (
    <div
      role="radiogroup"
      aria-label="排序方式"
      className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-muted/50 p-0.5"
    >
      {OPTIONS.map((opt) => {
        const isActive = value === opt.value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(opt.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
              isActive
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" />
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
