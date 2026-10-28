"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ClipboardList, GitBranch, Layers, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

const CARDS = [
  {
    key: "definitions",
    label: "流程定义",
    hint: "已建模流程",
    icon: Layers,
    accent: "text-sky-600 bg-sky-50 border-sky-100",
  },
  {
    key: "published",
    label: "已发布",
    hint: "可发起版本",
    icon: TrendingUp,
    accent: "text-emerald-600 bg-emerald-50 border-emerald-100",
  },
  {
    key: "instances",
    label: "流程实例",
    hint: "累计发起",
    icon: GitBranch,
    accent: "text-violet-600 bg-violet-50 border-violet-100",
  },
  {
    key: "running",
    label: "运行中",
    hint: "审批进行时",
    icon: Activity,
    accent: "text-amber-600 bg-amber-50 border-amber-100",
  },
  {
    key: "tasks",
    label: "待办任务",
    hint: "全租户待处理",
    icon: ClipboardList,
    accent: "text-rose-600 bg-rose-50 border-rose-100",
  },
] as const;

export function StatCards() {
  const { data, isLoading } = useQuery({
    queryKey: ["meta", "stats"],
    queryFn: api.meta.stats,
  });

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {CARDS.map((card) => {
        const Icon = card.icon;
        const value = data?.[card.key] ?? 0;
        return (
          <div
            key={card.key}
            className="relative overflow-hidden rounded-xl border border-border bg-card p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[11px] font-medium text-muted-foreground">{card.label}</p>
                {isLoading ? (
                  <Skeleton className="mt-2 h-7 w-12" />
                ) : (
                  <p className="mt-1 text-[24px] font-semibold leading-none tracking-tight tabular-nums">
                    {formatNumber(value)}
                  </p>
                )}
              </div>
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-lg border ${card.accent}`}
              >
                <Icon className="h-4 w-4" strokeWidth={2} />
              </span>
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground/80">{card.hint}</p>
          </div>
        );
      })}
    </div>
  );
}
