"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/extensions/hooks/useAuth";
import { useLicense } from "@/extensions/license/useLicense";

import {
  fetchApps,
  fetchDomains,
  type AppResponse,
  type DomainResponse,
} from "../api";
import { getDomainLabel } from "../config/categories";
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
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

function toAppDefinition(a: AppResponse): AppDefinition {
  return {
    id: a.appId,
    name: a.name,
    description: a.description ?? "",
    iconName: a.iconName,
    businessDomain: a.businessDomain,
    stageTag: a.stageTag as AppDefinition["stageTag"] | undefined,
    path: a.path,
    licenseModule: a.licenseModule,
    adminOnly: a.adminOnly,
    sortOrder: a.sortOrder,
    sortKey: a.sortKey,
    isBuiltin: a.isBuiltin,
  };
}

/**
 * 应用中心主 hook：从 API 获取数据，聚合搜索、排序、业务域筛选与权限过滤。
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

  // Fetch apps & domains from API
  const {
    data: rawApps,
    isLoading: appsLoading,
    error: appsError,
  } = useSWR("app-center-apps", fetchApps, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });
  const {
    data: domains,
    isLoading: domainsLoading,
    error: domainsError,
  } = useSWR("app-center-domains", fetchDomains, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const isLoading = appsLoading || domainsLoading;
  const isError = appsError !== undefined || domainsError !== undefined;
  const error = (appsError ?? domainsError ?? null) as Error | null;

  // Convert API response to AppDefinition
  const rawDefinitions = useMemo<AppDefinition[]>(
    () => (rawApps ? rawApps.map(toAppDefinition) : []),
    [rawApps],
  );

  // 1. 权限过滤
  const visibleApps = useMemo(() => {
    return rawDefinitions.filter((app) => {
      if (app.adminOnly && !isAdmin) return false;
      if (app.licenseModule && !licenseLoading && !hasModule(app.licenseModule))
        return false;
      return true;
    });
  }, [rawDefinitions, hasModule, isAdmin, licenseLoading]);

  // 2. 业务域筛选项（通用域在前，含数量）
  const domainOptions = useMemo<DomainFilterOption[]>(() => {
    const universalKeys = (domains ?? [])
      .filter((d: DomainResponse) => d.isUniversal)
      .sort((a: DomainResponse, b: DomainResponse) => a.sortOrder - b.sortOrder)
      .map((d: DomainResponse) => d.key);

    const counts = new Map<BusinessDomainKey, number>();
    const seenOrder: BusinessDomainKey[] = [];

    for (const app of visibleApps) {
      const d = app.businessDomain;
      if (!counts.has(d)) seenOrder.push(d);
      counts.set(d, (counts.get(d) ?? 0) + 1);
    }

    const universalSet = new Set(universalKeys);
    const ordered = [
      ...universalKeys.filter((d) => counts.has(d)),
      ...seenOrder.filter((d) => !universalSet.has(d)),
    ];

    return [
      { key: "all", label: "全部", count: visibleApps.length },
      ...ordered.map((key) => ({
        key,
        label: getDomainLabel(
          key,
          domains as Array<{ key: string; label: string }> | undefined,
        ),
        count: counts.get(key) ?? 0,
      })),
    ];
  }, [visibleApps, domains]);

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
    allApps: rawDefinitions,
    searchQuery,
    setSearchQuery,
    sortMode,
    setSortMode,
    activeDomain,
    setActiveDomain,
    domainOptions,
    licenseLoading,
    isLoading,
    isError,
    error,
  };
}
