"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { AppDefinition } from "../types";

import { AppCard } from "./AppCard";

interface AppGridProps {
  apps: AppDefinition[];
  isLoading: boolean;
  isFavorite: (appId: string) => boolean;
  onToggleFavorite: (appId: string) => void;
  /** 是否为收藏区（影响标题样式） */
  variant?: "default" | "compact";
}

/**
 * 应用卡片网格容器。
 * 加载中渲染骨架卡片（与真实卡片形状一致）。
 */
export function AppGrid({
  apps,
  isLoading,
  isFavorite,
  onToggleFavorite,
}: AppGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 8 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {apps.map((app) => (
        <AppCard
          key={app.id}
          app={app}
          isFavorite={isFavorite(app.id)}
          onToggleFavorite={onToggleFavorite}
        />
      ))}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-2xl border border-border bg-card p-5",
      )}
    >
      <Skeleton className="size-11 rounded-xl" />
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-3.5 w-2/3" />
        <Skeleton className="h-2.5 w-full" />
        <Skeleton className="h-2.5 w-4/5" />
      </div>
      <Skeleton className="mt-1 h-4 w-16 rounded-full" />
    </div>
  );
}
