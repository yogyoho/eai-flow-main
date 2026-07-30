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
  /** 业务域首次出现顺序（用于 accent 确定性分配） */
  domainOrder: string[];
  /** 领域列表（来自 API，用于标签查找） */
  domains?: Array<{ key: string; label: string; accentColor: string }>;
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
  domainOrder,
  domains,
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
      {/* EAI-CUSTOM: nav-level permission gate — add canNav(app.nav_id) when API provides nav_id */}
      {apps.map((app) => (
        <AppCard
          key={app.id}
          app={app}
          isFavorite={isFavorite(app.id)}
          onToggleFavorite={onToggleFavorite}
          domainOrder={domainOrder}
          domains={domains}
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
