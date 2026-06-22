"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/extensions/hooks/useAuth";
import { useLicense } from "@/extensions/license/useLicense";

import { BUILTIN_APPS } from "../config/apps";
import {
  getDomainLabel,
  UNIVERSAL_DOMAINS,
  UNIVERSAL_DOMAIN_SET,
} from "../config/categories";
import type {
  AppDefinition,
  BusinessDomainKey,
  DomainFilter,
  SortMode,
} from "../types";

export interface DomainFilterOption {
  key: DomainFilter;
  label: string;
  count: number;
}

export interface UseAppsReturn {
  apps: AppDefinition[];
  visibleApps: AppDefinition[];
  allApps: AppDefinition[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  sortMode: SortMode;
  setSortMode: (mode: SortMode) => void;
  activeDomain: DomainFilter;
  setActiveDomain: (d: DomainFilter) => void;
  domainOptions: DomainFilterOption[];
  licenseLoading: boolean;
}

/**
 * 应用中心主 hook：聚合搜索、排序、业务域筛选与权限过滤。
 */
export function useApps(
  favorites: Set<string>,
  isFavoriteHydrated: boolean,
): UseAppsReturn {
  const { user } = useAuth();
  const { hasModule, isLoading: licenseLoading } = useLicense();

  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("default");
  const [activeDomain, setActiveDomain] = useState<DomainFilter>("all");

  const isAdmin = user?.role_name === "Super Admin";

  // 1. 权限过滤
  const visibleApps = useMemo(() => {
    return BUILTIN_APPS.filter((app) => {
      if (app.adminOnly && !isAdmin) return false;
      if (app.licenseModule && !licenseLoading && !hasModule(app.licenseModule))
        return false;
      return true;
    });
  }, [hasModule, isAdmin, licenseLoading]);

  // 2. 业务域筛选项（通用域在前，业务域按首次出现顺序，含数量）
  const domainOptions = useMemo<DomainFilterOption[]>(() => {
    const counts = new Map<BusinessDomainKey, number>();
    const seenOrder: BusinessDomainKey[] = [];

    for (const app of visibleApps) {
      const d = app.businessDomain;
      if (!counts.has(d)) seenOrder.push(d);
      counts.set(d, (counts.get(d) ?? 0) + 1);
    }

    // 通用域在前（按 UNIVERSAL_DOMAINS 声明顺序），业务域按首次出现顺序
    const ordered = [
      ...UNIVERSAL_DOMAINS.filter((d) => counts.has(d)),
      ...seenOrder.filter((d) => !UNIVERSAL_DOMAIN_SET.has(d)),
    ];

    return [
      { key: "all", label: "全部", count: visibleApps.length },
      ...ordered.map((key) => ({
        key,
        label: getDomainLabel(key),
        count: counts.get(key) ?? 0,
      })),
    ];
  }, [visibleApps]);

  // 3. 搜索 + 域筛选 + 排序
  const apps = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let list = visibleApps;

    if (activeDomain !== "all") {
      list = list.filter((a) => a.businessDomain === activeDomain);
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
  }, [visibleApps, activeDomain, searchQuery, sortMode, favorites, isFavoriteHydrated]);

  return {
    apps,
    visibleApps,
    allApps: BUILTIN_APPS,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeDomain,
    setActiveDomain,
    domainOptions,
    licenseLoading,
  };
}
