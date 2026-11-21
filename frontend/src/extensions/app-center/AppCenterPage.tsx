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
    domains,
    licenseLoading,
    isLoading: dataLoading,
    isError,
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
  const isLoading = licenseLoading || dataLoading;

  // Error state
  if (isError && !isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-16 text-center">
        <p className="text-muted-foreground">加载失败，请刷新页面重试。</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* 标题区 */}
      <header className="mb-6 flex items-start gap-3">
        <div className="border-primary/20 bg-primary/10 text-primary shrink-0 rounded-lg border p-3">
          <Blocks className="h-6 w-6" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-foreground text-2xl font-bold tracking-tight">
              应用中心
            </h1>
            {!isLoading && (
              <span
                className="border-border bg-muted/50 text-muted-foreground inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium tabular-nums"
                suppressHydrationWarning
              >
                {visibleApps.length} 个应用
              </span>
            )}
          </div>
          <p className="text-muted-foreground mt-1 text-sm">
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
            <Star
              className="size-4 text-amber-500 dark:text-amber-400"
              fill="currentColor"
            />
            <h2 className="text-foreground text-sm font-semibold">我的收藏</h2>
            <span className="text-muted-foreground text-xs">
              {favoriteApps.length}
            </span>
          </div>
          <AppGrid
            apps={favoriteApps}
            isLoading={false}
            isFavorite={isFavorite}
            onToggleFavorite={toggleFavorite}
            domainOrder={domainOrder}
            domains={domains}
          />
        </section>
      )}

      {/* 主网格 / 空状态 */}
      <section className="mt-8">
        {showFavorites && (
          <div className="mb-3">
            <h2 className="text-foreground text-sm font-semibold">全部应用</h2>
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
