"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/extensions/hooks/useAuth";
import { useLicense } from "@/extensions/license/useLicense";

import { BUILTIN_APPS } from "../config/apps";
import { CATEGORIES } from "../config/categories";
import type {
  AppDefinition,
  CategoryFilter,
  SortMode,
} from "../types";

export interface CategoryFilterOption {
  key: CategoryFilter;
  label: string;
  count: number;
}

export interface UseAppsReturn {
  /** 经过 license/搜索/分类/排序后的最终应用列表 */
  apps: AppDefinition[];
  /** license + admin 过滤后、未应用搜索/分类/排序的应用列表（用于计数） */
  visibleApps: AppDefinition[];
  /** 原始应用列表（未过滤） */
  allApps: AppDefinition[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  sortMode: SortMode;
  setSortMode: (mode: SortMode) => void;
  activeCategory: CategoryFilter;
  setActiveCategory: (cat: CategoryFilter) => void;
  /** 分类筛选项（含"全部"），count 为该分类下可见应用数 */
  categoryOptions: CategoryFilterOption[];
  /** license 是否仍在加载（加载中显示所有应用，与 Sidebar 行为一致） */
  licenseLoading: boolean;
}

/**
 * 应用中心主 hook：聚合搜索、排序、分类筛选与权限过滤。
 *
 * 权限过滤逻辑镜像 Sidebar.tsx：
 *  - adminOnly 应用：仅 role_name === "Super Admin" 可见
 *  - licenseModule 应用：licenseLoading 时显示，加载完成后按 hasModule 过滤
 */
export function useApps(
  favorites: Set<string>,
  isFavoriteHydrated: boolean,
): UseAppsReturn {
  const { user } = useAuth();
  const { hasModule, isLoading: licenseLoading } = useLicense();

  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("default");
  const [activeCategory, setActiveCategory] = useState<CategoryFilter>("all");

  const isAdmin = user?.role_name === "Super Admin";

  // 1. 权限过滤（license + admin）
  const visibleApps = useMemo(() => {
    return BUILTIN_APPS.filter((app) => {
      if (app.adminOnly && !isAdmin) return false;
      if (app.licenseModule && !licenseLoading && !hasModule(app.licenseModule))
        return false;
      return true;
    });
  }, [hasModule, isAdmin, licenseLoading]);

  // 2. 分类筛选项（含数量）
  const categoryOptions = useMemo<CategoryFilterOption[]>(() => {
    const counts = new Map<CategoryFilter, number>();
    counts.set("all", visibleApps.length);
    for (const c of CATEGORIES) {
      counts.set(c.key, 0);
    }
    for (const app of visibleApps) {
      counts.set(app.category, (counts.get(app.category) ?? 0) + 1);
    }
    return [
      { key: "all", label: "全部", count: counts.get("all") ?? 0 },
      ...CATEGORIES.filter((c) => (counts.get(c.key) ?? 0) > 0).map((c) => ({
        key: c.key,
        label: c.label,
        count: counts.get(c.key) ?? 0,
      })),
    ];
  }, [visibleApps]);

  // 3. 搜索 + 分类 + 排序
  const apps = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let list = visibleApps;

    if (activeCategory !== "all") {
      list = list.filter((a) => a.category === activeCategory);
    }

    if (q) {
      list = list.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q),
      );
    }

    const sorted = [...list];
    switch (sortMode) {
      case "alphabetical":
        sorted.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
        break;
      case "favorites-first":
        // 水合前不重排，避免收藏态闪烁导致跳动
        sorted.sort((a, b) => {
          const af = isFavoriteHydrated && favorites.has(a.id) ? 0 : 1;
          const bf = isFavoriteHydrated && favorites.has(b.id) ? 0 : 1;
          if (af !== bf) return af - bf;
          return a.sortOrder - b.sortOrder;
        });
        break;
      case "default":
      default:
        sorted.sort((a, b) => a.sortOrder - b.sortOrder);
        break;
    }
    return sorted;
  }, [visibleApps, activeCategory, searchQuery, sortMode, favorites, isFavoriteHydrated]);

  return {
    apps,
    visibleApps,
    allApps: BUILTIN_APPS,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeCategory,
    setActiveCategory,
    categoryOptions,
    licenseLoading,
  };
}
