"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { usePermission } from "@/core/permissions";
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
  /** 原始领域列表（来自 API，用于标签/accent 查找） */
  domains: DomainResponse[];
  licenseLoading: boolean;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

// ponytail: cache domain labels per-domain so AppCard doesn't need to thread domains prop
let _domainLabelCache: Map<string, string> | null = null;

function toAppDefinition(a: AppResponse, domains?: DomainResponse[]): AppDefinition {
  // Build domain label cache on first call
  if (!_domainLabelCache && domains) {
    _domainLabelCache = new Map(domains.map((d) => [d.key, d.label]));
  }
  return {
    id: a.appId,
    name: a.name,
    description: a.description ?? "",
    iconName: a.iconName,
    businessDomain: a.businessDomain,
    // Pre-resolve domain label from cache
    domainLabel: _domainLabelCache?.get(a.businessDomain),
    stageTag: a.stageTag as AppDefinition["stageTag"] | undefined,
    path: a.path,
    licenseModule: a.licenseModule,
    adminOnly: a.adminOnly,
    sortOrder: a.sortOrder,
    sortKey: a.sortKey,
    isBuiltin: a.isBuiltin,
  };
}

function deriveNavId(path: string): string | null {
  const segment = path.replace(/^\//, "").split("/")[0];
  if (!segment) return null;
  const mapping: Record<string, string> = {
    "bid-quote": "nav:bid-quote",
    "biz-pipeline": "nav:biz-pipeline",
    "sales-personnel": "nav:sales-personnel",
    "contract-price": "nav:contract-price",
    "knowledge-factory": "nav:knowledge-factory",
    "workflow-admin": "nav:workflow-admin",
    "app-center": "nav:app-center",
  };
  return mapping[segment] || `nav:${segment}`;
}

/**
 * 应用中心主 hook：从 API 获取数据，聚合搜索、排序、业务域筛选与权限过滤。
 */
export function useApps(
  favorites: Set<string>,
  isFavoriteHydrated: boolean,
): UseAppsReturn {
  const { hasModule, isLoading: licenseLoading } = useLicense();

  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("default");
  const [activeDomain, setActiveDomain] = useState<DomainFilter>("all");

  // EAI-CUSTOM: gate admin-only apps by permission-system is_admin (U2), not display-name check
  const { canNav, is_admin } = usePermission();

  // Fetch apps & domains from API
  const {
    data: rawApps,
    isLoading: appsLoading,
    error: appsError,
  } = useQuery({
    queryKey: ["app-center-apps"],
    queryFn: fetchApps,
    staleTime: 60000,
  });
  const {
    data: domains,
    isLoading: domainsLoading,
    error: domainsError,
  } = useQuery({
    queryKey: ["app-center-domains"],
    queryFn: fetchDomains,
    staleTime: 60000,
  });

  const isLoading = appsLoading || domainsLoading;
  const isError = appsError != null || domainsError != null;
  const error = (appsError ?? domainsError ?? null) as Error | null;

  // Convert API response to AppDefinition
  const rawDefinitions = useMemo<AppDefinition[]>(
    () => (rawApps ? rawApps.map((a) => toAppDefinition(a, domains)) : []),
    [rawApps, domains],
  );

  // 1. 权限过滤
  const visibleApps = useMemo(() => {
    return rawDefinitions.filter((app) => {
      if (app.adminOnly && !is_admin) return false;
      if (app.licenseModule && !licenseLoading && !hasModule(app.licenseModule))
        return false;
      const navId = deriveNavId(app.path);
      if (navId && !canNav(navId)) return false;
      return true;
    });
  }, [rawDefinitions, hasModule, is_admin, licenseLoading, canNav]);

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
    domains: domains ?? [],
    licenseLoading,
    isLoading,
    isError,
    error,
  };
}
