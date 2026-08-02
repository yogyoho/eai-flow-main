"use client";

import { useMemo } from "react";

import type { ProjectChapter } from "@/extensions/project/types";
import { type ChapterStatus, flattenChapters, inferStatus } from "@/extensions/project/utils";

interface StatusDistributionProps {
  chapters: ProjectChapter[];
}

type StatusAccent = "slate" | "blue" | "amber" | "emerald";

const STATUS_ITEMS: {
  key: ChapterStatus;
  label: string;
  dotColor: string;
  accent: StatusAccent;
}[] = [
  // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
  { key: "pending", label: "未开始", dotColor: "bg-muted-foreground", accent: "slate" },
  { key: "draft", label: "编写中", dotColor: "bg-primary", accent: "blue" },
  { key: "reviewing", label: "审核中", dotColor: "bg-warning", accent: "amber" },
  { key: "approved", label: "已完成", dotColor: "bg-success", accent: "emerald" },
];

const RING_CLS: Record<StatusAccent, string> = {
  slate: "ring-muted-foreground/15",
  blue: "ring-primary/15",
  amber: "ring-warning/15",
  emerald: "ring-success/15",
};

export function StatusDistribution({ chapters }: StatusDistributionProps) {
  const { counts, totalCount } = useMemo(() => {
    const flat = flattenChapters(chapters);
    const map = { pending: 0, draft: 0, reviewing: 0, approved: 0 } as Record<ChapterStatus, number>;
    for (const ch of flat) {
      map[inferStatus(ch)]++;
    }
    return { counts: map, totalCount: flat.length };
  }, [chapters]);

  return (
    <div className="themed-card-sci rounded-xl p-3 flex flex-wrap items-center justify-between gap-4 text-xs">
      <div className="flex items-center gap-4 flex-wrap">
        {STATUS_ITEMS.map((item) => {
          const count = counts[item.key];
          return (
            <div
              key={item.key}
              className="relative flex items-center gap-2 px-3 py-1.5 rounded-lg border border-transparent"
              style={{ color: "var(--cyber-text-muted)" }}
            >
              {item.key === "draft" && (
                <span className="w-2.5 h-2.5 rounded-full bg-primary ring-4 ring-primary/10 animate-ping absolute" />
              )}
              <span className={`w-2.5 h-2.5 rounded-full ${item.dotColor} ring-2 ${RING_CLS[item.accent]}`} />
              <span>{item.label}</span>
              <span className="font-bold px-1 rounded bg-muted text-muted-foreground text-[10px]">
                {item.key === "approved" ? `${count}/${totalCount}` : count}
              </span>
            </div>
          );
        })}
      </div>
      <span className="hidden lg:inline-block text-[10px] italic text-muted-foreground">
        &gt; FILTERS READY // CLICK STAT NODE TO PIN CATEGORIES
      </span>
    </div>
  );
}
