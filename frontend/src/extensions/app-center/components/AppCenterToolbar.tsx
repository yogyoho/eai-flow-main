"use client";

import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { DomainFilterOption } from "../hooks/useApps";
import type { DomainFilter, SortMode } from "../types";

import { CategoryTabs } from "./CategoryTabs";
import { SortControl } from "./SortControl";

interface AppCenterToolbarProps {
  searchQuery: string;
  onSearchChange: (q: string) => void;
  domainOptions: DomainFilterOption[];
  activeDomain: DomainFilter;
  onDomainChange: (key: DomainFilter) => void;
  sortMode: SortMode;
  onSortChange: (mode: SortMode) => void;
}

export function AppCenterToolbar({
  searchQuery,
  onSearchChange,
  domainOptions,
  activeDomain,
  onDomainChange,
  sortMode,
  onSortChange,
}: AppCenterToolbarProps) {
  const hasQuery = searchQuery.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="relative">
        <Search
          className={cn(
            "pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground",
          )}
        />
        <Input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label="搜索应用"
          placeholder="搜索应用名称或功能..."
          className={cn(
            "h-11 rounded-xl border-border bg-muted/50 pl-10 pr-10 text-sm transition-colors",
            "placeholder:text-muted-foreground/70 focus-visible:bg-background",
          )}
        />
        {hasQuery && (
          <button
            type="button"
            onClick={() => onSearchChange("")}
            aria-label="清除搜索"
            className="absolute right-3 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CategoryTabs
          options={domainOptions}
          active={activeDomain}
          onChange={onDomainChange}
        />
        <SortControl value={sortMode} onChange={onSortChange} />
      </div>
    </div>
  );
}
