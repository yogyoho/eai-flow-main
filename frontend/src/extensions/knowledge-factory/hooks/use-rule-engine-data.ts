import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchRuleExecutionStatistics,
  fetchRuleLogs,
  fetchRuleOverview,
  fetchRules,
  importSeedRules,
  toggleRuleEnabled,
  type RuleExecutionLog,
  type RuleExecutionStatistics,
} from "../complianceRulesApi";
import { updateRuleFilters } from "../rule-filter-utils";
import type {
  ComplianceRule,
  ComplianceRuleListResponse,
  ComplianceRuleOverview,
  RuleFilterParams,
} from "@/extensions/knowledge-factory/types";

interface UseRuleEngineDataOptions {
  initialFilters?: RuleFilterParams;
  showManagement?: boolean;
}

export function useRuleEngineData({
  initialFilters,
  showManagement = true,
}: UseRuleEngineDataOptions) {
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<RuleFilterParams>({
    ...initialFilters,
    page: 1,
    limit: 20,
  });
  const [overview, setOverview] = useState<ComplianceRuleOverview | null>(null);
  const [logs, setLogs] = useState<RuleExecutionLog[]>([]);
  const [logStatistics, setLogStatistics] = useState<RuleExecutionStatistics | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response: ComplianceRuleListResponse = await fetchRules(filters);
      setRules(response.rules);
      setTotal(response.total);
      setPage(response.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载规则列表失败");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadOverview = useCallback(async () => {
    if (!showManagement) {
      return;
    }

    try {
      const nextOverview = await fetchRuleOverview();
      setOverview(nextOverview);
    } catch (err) {
      console.error("加载规则总览失败:", err);
    }
  }, [showManagement]);

  const refresh = useCallback(() => {
    void loadRules();
    void loadOverview();
  }, [loadOverview, loadRules]);

  const loadRuleLogs = useCallback(async (ruleKey: string) => {
    setLoadingLogs(true);
    try {
      const [logsData, statsData] = await Promise.all([
        fetchRuleLogs(ruleKey),
        fetchRuleExecutionStatistics(ruleKey),
      ]);
      setLogs(logsData.logs);
      setLogStatistics(statsData);
    } catch (err) {
      console.error("加载规则日志失败:", err);
    } finally {
      setLoadingLogs(false);
    }
  }, []);

  const clearLogState = useCallback(() => {
    setLogs([]);
    setLogStatistics(null);
  }, []);

  const handleToggleEnabled = useCallback(async (ruleKey: string, enabled: boolean) => {
    await toggleRuleEnabled(ruleKey, enabled);
    refresh();
  }, [refresh]);

  const handleBatchToggleEnabled = useCallback(
    async (ruleKeys: string[], enabled: boolean) => {
      const results = await Promise.allSettled(
        ruleKeys.map((ruleKey) => toggleRuleEnabled(ruleKey, enabled))
      );

      await Promise.all([loadRules(), loadOverview()]);

      const errors = results.flatMap((result, index) =>
        result.status === "rejected"
          ? [`${ruleKeys[index]}: ${result.reason instanceof Error ? result.reason.message : "更新失败"}`]
          : []
      );

      return {
        successCount: results.length - errors.length,
        failedCount: errors.length,
        errors,
      };
    },
    [loadOverview, loadRules]
  );

  const handleImportSeed = useCallback(async (forceUpdate: boolean) => {
    const result = await importSeedRules(forceUpdate);
    if (result.success) {
      refresh();
    }
    return result;
  }, [refresh]);

  const handleRuleDeleted = useCallback((ruleKey: string) => {
    setRules((prev) => prev.filter((rule) => rule.ruleId !== ruleKey));
    void loadOverview();
  }, [loadOverview]);

  const setFilter = useCallback(
    (key: keyof RuleFilterParams, value: string | boolean | number | undefined) => {
      setFilters((prev) => updateRuleFilters(prev, key, value));
    },
    []
  );

  const clearFilters = useCallback(() => {
    setFilters({ page: 1, limit: 20 });
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const statistics = useMemo(() => overview?.statistics ?? null, [overview]);
  const seedStatus = useMemo(() => overview?.seedStatus ?? null, [overview]);
  const triggerStats = useMemo(() => overview?.triggerStatistics ?? null, [overview]);

  return {
    rules,
    total,
    page,
    limit,
    loading,
    error,
    filters,
    statistics,
    seedStatus,
    triggerStats,
    logs,
    logStatistics,
    loadingLogs,
    loadRules,
    refresh,
    loadRuleLogs,
    clearLogState,
    handleToggleEnabled,
    handleBatchToggleEnabled,
    handleImportSeed,
    handleRuleDeleted,
    setFilter,
    clearFilters,
  };
}
