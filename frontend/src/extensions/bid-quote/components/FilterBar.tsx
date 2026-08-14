"use client";

import { Filter } from "lucide-react";

import { useFilterOptions } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

interface FilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

// 多选下拉:点击 chip 切换选中。选项来自 distinct 查询。
function MultiSelect({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1">
        {options.length === 0 ? (
          <span className="text-[11px] text-muted-foreground/60">加载中…</span>
        ) : (
          options.map((o) => {
            const on = selected.includes(o);
            return (
              <button
                key={o}
                onClick={() => onToggle(o)}
                className={
                  "rounded border px-2 py-0.5 text-[11px] transition-colors " +
                  (on
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground")
                }
              >
                {o}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const optsQ = useFilterOptions();
  const opts = optsQ.data ?? { projects: [], competitors: [] };
  const toggle = (key: "projects" | "competitors", v: string) => {
    const cur = filters[key];
    onChange({ ...filters, [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] });
  };
  // !! 收窄为布尔,避免 nullable 操作数上的 ||(prefer-nullish-coalescing)
  const active = !!filters.dateFrom || !!filters.dateTo || filters.projects.length > 0 || filters.competitors.length > 0;

  return (
    <div className="rounded-xl border border-border bg-card/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Filter className="h-3.5 w-3.5" />
        全局过滤(所有图表联动)
        {active && (
          <button
            onClick={() => onChange({ projects: [], competitors: [], dateFrom: null, dateTo: null })}
            className="ml-auto text-[11px] text-primary hover:underline"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <MultiSelect label="项目" options={opts.projects} selected={filters.projects} onToggle={(v) => toggle("projects", v)} />
        <MultiSelect label="友商" options={opts.competitors} selected={filters.competitors} onToggle={(v) => toggle("competitors", v)} />
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">投标日期</span>
          <div className="flex items-center gap-1">
            <input
              type="date"
              value={filters.dateFrom ?? ""}
              onChange={(e) => onChange({ ...filters, dateFrom: e.target.value || null })}
              className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px]"
            />
            <span className="text-[11px] text-muted-foreground">~</span>
            <input
              type="date"
              value={filters.dateTo ?? ""}
              onChange={(e) => onChange({ ...filters, dateTo: e.target.value || null })}
              className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
