"use client";

import { cn } from "@/lib/utils";

interface FilterPill {
  value: string;
  label: string;
}

interface FilterPillsProps {
  pills: FilterPill[];
  value: string;
  onChange: (value: string) => void;
}

export function FilterPills({ pills, value, onChange }: FilterPillsProps) {
  return (
    <div className="flex items-center gap-1">
      {pills.map((pill) => (
        <button
          key={pill.value}
          onClick={() => onChange(pill.value)}
          className={cn(
            "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
            value === pill.value
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-accent",
          )}
        >
          {pill.label}
        </button>
      ))}
    </div>
  );
}
