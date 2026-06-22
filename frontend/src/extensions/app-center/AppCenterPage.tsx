"use client";

import { Blocks, Star } from "lucide-react";
import { useMemo } from "react";

import { AppCenterToolbar } from "./components/AppCenterToolbar";
import { AppGrid } from "./components/AppGrid";
import { EmptyState } from "./components/EmptyState";
import { useApps } from "./hooks/useApps";
import { useFavorites } from "./hooks/useFavorites";

/**
 * 应用中心主页面。
 *
 * 布局：标题+搜索（顶）→ 工具栏（分类+排序）→ ⭐收藏区（有收藏才显示）
 *      → 全部应用主网格。
 */
export function AppCenterPage() {
  const { favorites, isFavorite, toggleFavorite, hydrated } = useFavorites();
  const {
    apps,
    visibleApps,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeDomain,
    setActiveDomain,
    domainOptions,
    licenseLoading,
  } = useApps(favorites, hydrated);

  // 业务域首次出现顺序（与 useApps 中 domainOptions 的派生逻辑一致，用于 AppCard accent 分配）
  const domainOrder = useMemo(() => {
    const seen: string[] = [];
    for (const app of visibleApps) {
      if (!seen.includes(app.businessDomain)) seen.push(app.businessDomain);
    }
    return seen;
  }, [visibleApps]);

  // 收藏区：仅在"默认/收藏优先"排序、无搜索、无分类筛选时展示，
  // 且至少有一条收藏。避免与主网格重复展示造成视觉冗余。
  const favoriteApps = useMemo(() => {
    if (!hydrated) return [];
    if (searchQuery.trim()) return [];
    if (activeDomain !== "all") return [];
    if (sortMode === "alphabetical") return [];
    return visibleApps.filter((a) => favorites.has(a.id));
  }, [hydrated, searchQuery, activeDomain, sortMode, visibleApps, favorites]);

  const showFavorites = favoriteApps.length > 0;
  const hasVisibleApps = visibleApps.length > 0;
  const isLoading = licenseLoading;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 标题区 */}
      <header className="mb-6 flex items-start gap-3">
        <div className="p-3 border rounded-lg bg-blue-50 border-blue-200 text-blue-600 shrink-0">
          <Blocks className="w-6 h-6" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">应用中心</h1>
            {!isLoading && (
              <span className="inline-flex items-center rounded-full border border-border bg-muted/50 px-2.5 py-0.5 text-xs font-medium text-muted-foreground tabular-nums" suppressHydrationWarning>
                {visibleApps.length} 个应用
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            发现并快速进入你需要的应用，收藏常用应用，让工作流更顺畅。
          </p>
        </div>
      </header>

      {/* 工具栏 */}
      <AppCenterToolbar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        domainOptions={domainOptions}
        activeDomain={activeDomain}
        onDomainChange={setActiveDomain}
        sortMode={sortMode}
        onSortChange={setSortMode}
      />

      {/* 收藏区 */}
      {showFavorites && (
        <section className="mt-8">
          <div className="mb-3 flex items-center gap-2">
            <Star className="size-4 text-amber-500" fill="currentColor" />
            <h2 className="text-sm font-semibold text-foreground">我的收藏</h2>
            <span className="text-xs text-muted-foreground">
              {favoriteApps.length}
            </span>
          </div>
          <AppGrid
            apps={favoriteApps}
            isLoading={false}
            isFavorite={isFavorite}
            onToggleFavorite={toggleFavorite}
            domainOrder={domainOrder}
          />
        </section>
      )}

      {/* 主网格 / 空状态 */}
      <section className="mt-8">
        {showFavorites && (
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-foreground">全部应用</h2>
          </div>
        )}

        {!hasVisibleApps && !isLoading ? (
          <EmptyState variant="no-apps" />
        ) : apps.length === 0 && !isLoading ? (
          <EmptyState variant="no-results" />
        ) : (
          <AppGrid
            apps={apps}
            isLoading={isLoading}
            isFavorite={isFavorite}
            onToggleFavorite={toggleFavorite}
            domainOrder={domainOrder}
          />
        )}
      </section>
    </div>
  );
}
