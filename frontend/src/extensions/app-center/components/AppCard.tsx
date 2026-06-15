"use client";

import { Star } from "lucide-react";
import Link from "next/link";
import { memo } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { ACCENT_STYLES, CATEGORY_MAP } from "../config/categories";
import type { AppDefinition } from "../types";

interface AppCardProps {
  app: AppDefinition;
  isFavorite: boolean;
  onToggleFavorite: (appId: string) => void;
}

/**
 * 单个应用卡片 —— Notion/Vercel 风格。
 *
 * 外层为 Next.js <Link>，确保中键/Cmd+Click 新标签打开、右键菜单、预加载生效。
 * 收藏按钮阻止冒泡，避免触发卡片跳转。
 */
function AppCardImpl({ app, isFavorite, onToggleFavorite }: AppCardProps) {
  const Icon = app.icon;
  const category = CATEGORY_MAP[app.category];
  const accent = ACCENT_STYLES[category.accent];

  const handleFavoriteClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite(app.id);
  };

  return (
    <Link
      href={app.path}
      role="link"
      aria-label={`${app.name} — ${app.description}`}
      className={cn(
        "group relative flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm transition-all",
        "hover:-translate-y-0.5 hover:border-primary/30 hover:bg-accent/40 hover:shadow-md",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        isFavorite && "border-primary/40 ring-1 ring-primary/10",
      )}
    >
      {/* 收藏按钮 */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={handleFavoriteClick}
            aria-label={isFavorite ? `取消收藏 ${app.name}` : `收藏 ${app.name}`}
            aria-pressed={isFavorite}
            className={cn(
              "absolute right-3 top-3 z-10 flex size-7 items-center justify-center rounded-full transition-all",
              "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
              isFavorite && "opacity-100",
              "hover:scale-110 active:scale-95",
              isFavorite
                ? "text-amber-500 hover:bg-amber-500/10"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <Star
              className="size-4 transition-all"
              fill={isFavorite ? "currentColor" : "none"}
              strokeWidth={isFavorite ? 0 : 2}
            />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">
          {isFavorite ? "取消收藏" : "添加到收藏"}
        </TooltipContent>
      </Tooltip>

      {/* 图标容器 */}
      <div
        className={cn(
          "flex size-11 shrink-0 items-center justify-center rounded-xl ring-1 transition-transform group-hover:scale-105",
          accent.container,
        )}
      >
        <Icon className={cn("size-5", accent.icon)} />
      </div>

      {/* 文本区 */}
      <div className="flex min-w-0 flex-col gap-1">
        <h3 className="truncate text-sm font-semibold text-foreground">
          {app.name}
        </h3>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
          {app.description}
        </p>
      </div>

      {/* 分类角标 */}
      <div className="mt-auto pt-1">
        <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {category.label}
        </span>
      </div>
    </Link>
  );
}

export const AppCard = memo(AppCardImpl);
