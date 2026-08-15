"use client";

import { ChevronDown, Filter } from "lucide-react";
import { useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useFilterOptions } from "@/extensions/bid-quote/hooks";
import type { FilterState } from "@/extensions/bid-quote/types";

interface FilterBarProps {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

// 多选下拉 popover:复选框列表,选项来自 distinct 查询。
function MultiDropdown({
  label,
  options,
  selected,
  onToggle,
  status,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  status: "pending" | "error" | "ok";
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-1" role="group" aria-label={label}>
      <span className="text-muted-foreground text-[11px]">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          className="border-border bg-background flex w-full items-center justify-between rounded border px-2 py-1 text-[12px] transition-colors hover:text-foreground"
          aria-label={label}
        >
          <span className="truncate text-foreground">
            {selected.length === 0
              ? "全部"
              : selected.length === 1
                ? selected[0]
                : `已选 ${selected.length} 项`}
          </span>
          <ChevronDown className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-52 p-1">
          {status === "pending" && options.length === 0 && (
            <div className="text-muted-foreground/60 px-2 py-1 text-[11px]">
              加载中…
            </div>
          )}
          {status === "error" && options.length === 0 && (
            <div className="text-destructive/80 px-2 py-1 text-[11px]">
              选项加载失败
            </div>
          )}
          <div className="max-h-48 overflow-auto">
            {options.map((o) => (
              <label
                key={o}
                className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[12px]"
              >
                <Checkbox
                  checked={selected.includes(o)}
                  onCheckedChange={() => onToggle(o)}
                />
                <span className="truncate">{o}</span>
              </label>
            ))}
          </div>
          {selected.length > 0 && (
            <button
              onClick={() => selected.forEach(onToggle)}
              className="text-muted-foreground hover:text-foreground w-full px-2 py-1 text-left text-[11px]"
            >
              清空选择
            </button>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const optsQ = useFilterOptions();
  const opts = optsQ.data ?? { projects: [], competitors: [], goods: [] };
  // 评审修正:用查询状态而非 options.length 区分 加载中/失败,避免请求失败时永远显示"加载中…"
  const status = optsQ.isPending ? "pending" : optsQ.isError ? "error" : "ok";
  const toggle = (key: "projects" | "competitors", v: string) => {
    const cur = filters[key];
    onChange({
      ...filters,
      [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v],
    });
  };
  // 项目单选下拉:FilterState.projects 仍是 string[],单选即 0/1 元素数组(SQL IN 不变)
  const project = filters.projects[0] ?? "";
  // !! 收窄为布尔,避免 nullable 操作数上的 ||(prefer-nullish-coalescing)
  const active =
    !!filters.dateFrom ||
    !!filters.dateTo ||
    filters.projects.length > 0 ||
    filters.competitors.length > 0;

  return (
    <div className="border-border bg-card/50 rounded-xl border p-3">
      <div className="text-muted-foreground mb-2 flex items-center gap-2 text-xs font-medium">
        <Filter className="h-3.5 w-3.5" />
        全局过滤(所有图表联动)
        {active && (
          <button
            onClick={() =>
              onChange({
                projects: [],
                competitors: [],
                dateFrom: null,
                dateTo: null,
              })
            }
            className="text-primary ml-auto text-[11px] hover:underline"
          >
            清空
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="flex flex-col gap-1" role="group" aria-label="项目">
          <span className="text-muted-foreground text-[11px]">项目</span>
          <div className="relative">
            <select
              aria-label="项目"
              value={project}
              onChange={(e) =>
                onChange({
                  ...filters,
                  projects: e.target.value ? [e.target.value] : [],
                })
              }
              className="border-border bg-background text-foreground w-full appearance-none rounded border px-2 py-1 pr-7 text-[12px]"
            >
              <option value="">全部项目</option>
              {opts.projects.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <ChevronDown className="text-muted-foreground pointer-events-none absolute top-1/2 right-2 h-3.5 w-3.5 -translate-y-1/2" />
          </div>
        </div>
        <MultiDropdown
          label="友商"
          options={opts.competitors}
          selected={filters.competitors}
          onToggle={(v) => toggle("competitors", v)}
          status={status}
        />
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-[11px]">投标日期</span>
          <div className="flex items-center gap-1">
            <input
              type="date"
              aria-label="投标日期起"
              value={filters.dateFrom ?? ""}
              onChange={(e) =>
                onChange({ ...filters, dateFrom: e.target.value || null })
              }
              className="border-border bg-background rounded border px-1.5 py-0.5 text-[11px]"
            />
            <span className="text-muted-foreground text-[11px]">~</span>
            <input
              type="date"
              aria-label="投标日期止"
              value={filters.dateTo ?? ""}
              onChange={(e) =>
                onChange({ ...filters, dateTo: e.target.value || null })
              }
              className="border-border bg-background rounded border px-1.5 py-0.5 text-[11px]"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
