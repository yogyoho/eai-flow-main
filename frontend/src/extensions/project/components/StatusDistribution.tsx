"use client";

import { useMemo } from "react";

import type { ProjectChapter } from "@/extensions/project/types";
import { type ChapterStatus, flattenChapters, inferStatus } from "@/extensions/project/utils";

interface StatusDistributionProps {
  chapters: ProjectChapter[];
}

const STATUS_ITEMS: { key: ChapterStatus; label: string; dotColor: string; activeColor: string }[] = [
  { key: "draft", label: "待编写", dotColor: "bg-slate-300", activeColor: "text-slate-600" },
  { key: "writing", label: "编写中", dotColor: "bg-blue-400", activeColor: "text-blue-600" },
  { key: "review", label: "审核中", dotColor: "bg-amber-400", activeColor: "text-amber-600" },
  { key: "completed", label: "已完成", dotColor: "bg-emerald-400", activeColor: "text-emerald-600" },
];

export function StatusDistribution({ chapters }: StatusDistributionProps) {
  const counts = useMemo(() => {
    const flat = flattenChapters(chapters);
    const map = { draft: 0, writing: 0, review: 0, completed: 0 } as Record<ChapterStatus, number>;
    for (const ch of flat) {
      map[inferStatus(ch)]++;
    }
    return map;
  }, [chapters]);

  return (
    <div className="flex items-center gap-4 px-1">
      {STATUS_ITEMS.map((item) => (
        <div key={item.key} className="flex items-center gap-1.5 text-[13px]">
          <span className={`h-2 w-2 rounded-full ${item.dotColor}`} />
          <span className={counts[item.key] > 0 ? item.activeColor : "text-muted-foreground"}>
            {item.label}
          </span>
          <span className="font-medium text-foreground">{counts[item.key]}</span>
        </div>
      ))}
    </div>
  );
}
