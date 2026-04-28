"use client";

import {
  Activity,
  AlertCircle,
  BadgeCheck,
  ChevronRight,
  Database,
  LayoutList,
  MoreVertical,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sprout,
  Terminal,
} from "lucide-react";
import React, { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";

import { useRuleDictionaries } from "@/extensions/knowledge-factory/hooks/use-rule-dictionaries";
import { useRuleEngineData } from "@/extensions/knowledge-factory/hooks/use-rule-engine-data";
import { getDictionaryLabel } from "./rule-dictionary-utils";
import {
  areAllRulesSelected,
  getAllSelectedRuleIds,
  toggleRuleSelection,
} from "./rule-selection-utils";
import { RuleCreatePanel } from "./RuleCreatePanel";
import { RuleDetail } from "./RuleDetail";
import { RuleLogsViewer } from "./RuleLogsViewer";
import { RuleTestModal } from "./RuleTestModal";
import { SeedDataManager } from "./SeedDataManager";
import {
  type ComplianceRule,
  type RuleFilterParams,
  RULE_TYPES,
  SEVERITY_LEVELS,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface RuleEngineProps {
  showManagement?: boolean;
  readOnly?: boolean;
  selectionMode?: boolean;
  selectedRules?: string[];
  onSelectionChange?: (ruleIds: string[]) => void;
  initialFilters?: RuleFilterParams;
}

export default function RuleEngine({
  showManagement = true,
  readOnly = false,
  selectionMode = false,
  selectedRules: initialSelectedRules = [],
  onSelectionChange,
  initialFilters,
}: RuleEngineProps) {
  const dictionaries = useRuleDictionaries();
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [showCreatePanel, setShowCreatePanel] = useState(false);
  const [selectedRules, setSelectedRules] = useState<string[]>(initialSelectedRules);
  const [batchSelectionMode, setBatchSelectionMode] = useState(false);
  const [batchActionLoading, setBatchActionLoading] = useState(false);
  const [batchActionError, setBatchActionError] = useState<string | null>(null);
  const [showSeedManager, setShowSeedManager] = useState(false);
  const [logsModalRule, setLogsModalRule] = useState<ComplianceRule | null>(null);
  const [testModalRule, setTestModalRule] = useState<ComplianceRule | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const {
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
    clearFilters: clearServerFilters,
  } = useRuleEngineData({
    initialFilters,
    showManagement,
  });

  const effectiveSelectionMode = selectionMode || batchSelectionMode;

  const handleViewLogs = async (rule: ComplianceRule) => {
    if (!rule.ruleId) return;
    setLogsModalRule(rule);
    await loadRuleLogs(rule.ruleId);
  };

  const handleCloseLogs = () => {
    setLogsModalRule(null);
    clearLogState();
  };

  const handleTestRule = (rule: ComplianceRule) => {
    setTestModalRule(rule);
  };

  const handleCloseTest = () => {
    setTestModalRule(null);
  };

  const handleRuleUpdated = () => {
    refresh();
    setSelectedRuleId(null);
  };

  const handleRuleDeletedInPanel = (ruleKey: string) => {
    handleRuleDeleted(ruleKey);
    setSelectedRuleId(null);
  };

  const handleRuleCreated = (rule: ComplianceRule) => {
    refresh();
    setShowCreatePanel(false);
    setSelectedRuleId(rule.ruleId ?? null);
  };

  const handleFilterChange = (key: keyof RuleFilterParams, value: string | boolean | number | undefined) => {
    setFilter(key, value);
  };

  const clearFilters = () => {
    clearServerFilters();
    setSearchQuery("");
  };

  const filteredRules = searchQuery
    ? rules.filter(
        (rule) =>
          rule.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (rule.ruleId ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
          rule.description?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : rules;

  const selectedRule = selectedRuleId
    ? rules.find((rule) => rule.ruleId === selectedRuleId) ?? null
    : null;

  const hasActiveFilters =
    filters.industry !== undefined ||
    filters.reportType !== undefined ||
    filters.region !== undefined ||
    filters.type !== undefined ||
    filters.severity !== undefined ||
    filters.enabled !== undefined ||
    searchQuery.length > 0;

  const industrySummary = statistics
    ? Object.entries(statistics.industryDistribution ?? {})
        .filter(([, count]) => count > 0)
        .map(([industry, count]) => {
          const label = getDictionaryLabel(dictionaries.industries, industry);
          return `${label} ${count}`;
        })
    : [];

  const allFilteredRulesSelected = areAllRulesSelected(
    filteredRules.map((rule) => rule.id),
    selectedRules
  );

  const selectedBatchRules = rules.filter((rule) => selectedRules.includes(rule.id));

  const handleToggleRuleSelection = (ruleId: string) => {
    const nextSelection = toggleRuleSelection(selectedRules, ruleId);
    setSelectedRules(nextSelection);
    onSelectionChange?.(nextSelection);
  };

  const handleSelectAll = () => {
    const nextSelection = getAllSelectedRuleIds(
      filteredRules.map((rule) => rule.id),
      selectedRules
    );
    setSelectedRules(nextSelection);
    onSelectionChange?.(nextSelection);
  };

  const resetBatchSelection = () => {
    setBatchSelectionMode(false);
    setSelectedRules([]);
    setBatchActionError(null);
    onSelectionChange?.([]);
  };

  const handleStartBatchSelection = () => {
    setBatchSelectionMode(true);
    setSelectedRuleId(null);
    setBatchActionError(null);
  };

  const handleBatchToggle = async (enabled: boolean) => {
    if (selectedBatchRules.length === 0) {
      setBatchActionError(`请先选择要${enabled ? "启用" : "禁用"}的规则`);
      return;
    }

    const confirmed = window.confirm(
      `确定要批量${enabled ? "启用" : "禁用"} ${selectedBatchRules.length} 条规则吗？`
    );
    if (!confirmed) {
      return;
    }

    setBatchActionLoading(true);
    setBatchActionError(null);

    try {
      const result = await handleBatchToggleEnabled(
        selectedBatchRules.map((rule) => rule.ruleId).filter((id): id is string => !!id),
        enabled
      );

      if (result.failedCount > 0) {
        setBatchActionError(
          `已处理 ${result.successCount} 条，失败 ${result.failedCount} 条。${result.errors[0] ?? ""}`
        );
        return;
      }

      resetBatchSelection();
    } catch (err) {
      setBatchActionError(err instanceof Error ? err.message : "批量操作失败");
    } finally {
      setBatchActionLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-foreground">
              <ShieldCheck className="h-5 w-5 text-primary" />
              合规规则引擎
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              当前筛选结果 {total} 条
              {searchQuery ? `，本地搜索命中 ${filteredRules.length} 条` : ""}
            </p>
          </div>

          <div className="flex gap-2">
            <button
              className="flex shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => {
                setSelectedRuleId(null);
                setShowCreatePanel(true);
              }}
              disabled={!showManagement || readOnly}
              title={!showManagement || readOnly ? "当前模式不可新建规则" : undefined}
            >
              <Plus className="h-4 w-4" />
              新建规则
            </button>

            {showManagement && (
              <button
                className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setShowSeedManager(true)}
                disabled={loading}
                title="种子数据管理"
              >
                <Database className="h-4 w-4" />
                种子数据
              </button>
            )}

            {!batchSelectionMode ? (
              <button
                className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleStartBatchSelection}
                disabled={!showManagement || readOnly || loading || rules.length === 0}
              >
                批量启用/禁用
              </button>
            ) : (
              <>
                <button
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 shadow-sm transition-colors hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleBatchToggle(true)}
                  disabled={batchActionLoading || selectedBatchRules.length === 0}
                >
                  批量启用
                </button>
                <button
                  className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 shadow-sm transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleBatchToggle(false)}
                  disabled={batchActionLoading || selectedBatchRules.length === 0}
                >
                  批量禁用
                </button>
                <button
                  className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-muted-foreground shadow-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={resetBatchSelection}
                  disabled={batchActionLoading}
                >
                  取消
                </button>
              </>
            )}

            {showManagement && (
              <button
                className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={refresh}
                disabled={loading || batchActionLoading}
                title="刷新"
              >
                <RefreshCw className="h-4 w-4" />
                刷新
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto bg-muted/30 p-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              <LayoutList className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-sm text-muted-foreground">总规则数</div>
              <div className="text-2xl font-bold text-foreground">{statistics?.total ?? "-"}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
              <BadgeCheck className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-sm text-muted-foreground">已启用</div>
              <div className="text-2xl font-bold text-emerald-600">{statistics?.enabled ?? "-"}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
              <Activity className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-sm text-muted-foreground">本月触发</div>
              <div className="text-2xl font-bold text-primary">
                {triggerStats?.monthTriggers?.toLocaleString() ?? "-"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
              <ShieldAlert className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-sm text-muted-foreground">拦截问题</div>
              <div className="text-2xl font-bold text-destructive">{triggerStats?.monthBlocked ?? "-"}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400">
              <Sprout className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 text-sm text-muted-foreground">种子规则</div>
              <div className="text-2xl font-bold text-amber-600">{seedStatus?.seedTotal ?? "-"}</div>
            </div>
          </div>
        </div>

        {industrySummary.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground shadow-sm">
            行业分布: {industrySummary.join(" | ")}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex gap-4">
            <AdminSelect
              value={filters.type ?? "all"}
              onChange={(value) => handleFilterChange("type", value === "all" ? undefined : value)}
              options={[
                { value: "all", label: "全部规则分类" },
                ...RULE_TYPES.map((item) => ({ value: item.value, label: item.label })),
              ]}
              className="w-40"
            />
            <AdminSelect
              value={filters.enabled === undefined ? "all" : filters.enabled ? "enabled" : "disabled"}
              onChange={(value) =>
                handleFilterChange("enabled", value === "all" ? undefined : value === "enabled")
              }
              options={[
                { value: "all", label: "全部状态" },
                { value: "enabled", label: "已启用" },
                { value: "disabled", label: "已禁用" },
              ]}
              className="w-32"
            />
            <AdminSelect
              value={filters.severity ?? "all"}
              onChange={(value) => handleFilterChange("severity", value === "all" ? undefined : value)}
              options={[
                { value: "all", label: "全部严重级别" },
                ...SEVERITY_LEVELS.map((item) => ({ value: item.value, label: item.label })),
              ]}
              className="w-36"
            />
            <AdminSelect
              value={filters.industry ?? "all"}
              onChange={(value) => handleFilterChange("industry", value === "all" ? undefined : value)}
              options={[
                { value: "all", label: "全部行业" },
                ...dictionaries.industries.map((item) => ({ value: item.value, label: item.label })),
              ]}
              className="w-36"
            />
            <AdminSelect
              value={filters.reportType ?? "all"}
              onChange={(value) => handleFilterChange("reportType", value === "all" ? undefined : value)}
              options={[
                { value: "all", label: "全部报告类型" },
                ...dictionaries.reportTypes.map((item) => ({ value: item.value, label: item.label })),
              ]}
              className="w-44"
            />
            <AdminSelect
              value={filters.region ?? "all"}
              onChange={(value) => handleFilterChange("region", value === "all" ? undefined : value)}
              options={[
                { value: "all", label: "全部地区" },
                ...dictionaries.regions.map((item) => ({ value: item.value, label: item.label })),
              ]}
              className="w-32"
            />
          </div>

          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="搜索规则名称、ID、描述..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="w-full rounded-lg border border-border bg-muted py-2 pl-10 pr-4 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="flex items-center gap-2">
            {hasActiveFilters && (
              <button
                className="px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                onClick={clearFilters}
              >
                清除筛选
              </button>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {batchActionError && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {batchActionError}
            </div>
          )}

          {effectiveSelectionMode && (
            <div className="flex items-center justify-between rounded-xl border border-border bg-muted p-4">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={allFilteredRulesSelected}
                  onChange={handleSelectAll}
                  className="h-4 w-4"
                />
                <span className="text-sm font-medium">全选当前页</span>
              </label>
              <div className="text-sm text-muted-foreground">
                已选择 {selectedRules.length} 条规则
                {batchActionLoading ? "，正在执行批量操作..." : ""}
              </div>
            </div>
          )}

          {loading && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <RefreshCw className="mb-4 h-8 w-8 animate-spin" />
              <span>加载中...</span>
            </div>
          )}

          {!loading && error && (
            <div className="flex flex-col items-center justify-center py-16 text-destructive">
              <span className="mb-2 text-lg">加载失败</span>
              <span className="mb-4 text-sm text-muted-foreground">{error}</span>
              <button
                className="rounded-lg bg-destructive px-4 py-2 text-sm text-white hover:bg-destructive/90"
                onClick={() => {
                  void loadRules();
                }}
              >
                重试
              </button>
            </div>
          )}

          {!loading && !error && filteredRules.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <span className="mb-4 text-4xl">📭</span>
              <span className="mb-2 text-lg">
                {hasActiveFilters ? "没有符合条件的规则" : "暂无规则"}
              </span>
              {hasActiveFilters && (
                <button className="text-sm text-primary hover:underline" onClick={clearFilters}>
                  清除筛选
                </button>
              )}
            </div>
          )}

          {!loading && !error && filteredRules.length > 0 && (
            <>
              <div className="text-sm text-muted-foreground">
                共 {total} 条规则
                {searchQuery ? `，搜索到 ${filteredRules.length} 条` : ""}
              </div>

              {filteredRules.map((rule) => (
                <div
                  key={rule.id}
                  className={cn(
                    "overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all group hover:border-primary/30 hover:shadow-md",
                    effectiveSelectionMode && selectedRules.includes(rule.id) && "border-primary/40 ring-2 ring-primary/30"
                  )}
                  onClick={() => {
                    if (effectiveSelectionMode) {
                      handleToggleRuleSelection(rule.id);
                    }
                  }}
                >
                  <div className="flex items-start justify-between border-b border-border p-5">
                    <div className="flex gap-4">
                      {effectiveSelectionMode && (
                        <label
                          className="mt-1 flex items-center"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={selectedRules.includes(rule.id)}
                            onChange={() => handleToggleRuleSelection(rule.id)}
                            className="h-4 w-4"
                          />
                        </label>
                      )}

                      <div
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-lg",
                          rule.severity === "critical"
                            ? "bg-destructive/10 text-destructive"
                            : rule.severity === "warning"
                              ? "bg-amber-50 text-amber-600"
                              : "bg-muted text-muted-foreground"
                        )}
                      >
                        <AlertCircle className="h-6 w-6" />
                      </div>

                      <div className="space-y-1">
                        <div className="flex items-center gap-3">
                          <h4 className="font-medium text-foreground">
                            {rule.ruleId} | {rule.name}
                          </h4>
                          <span
                            className={cn(
                              "flex cursor-pointer items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-medium",
                              rule.enabled
                                ? "border-emerald-100 bg-emerald-50 text-emerald-600"
                                : "border-border bg-muted text-muted-foreground"
                            )}
                            onClick={() => {
                              if (!effectiveSelectionMode && !readOnly && showManagement && rule.ruleId) {
                                void handleToggleEnabled(rule.ruleId, !rule.enabled);
                              }
                            }}
                          >
                            {rule.enabled ? "启用" : "禁用"}
                          </span>
                        </div>

                        <div className="flex gap-4 text-xs text-muted-foreground">
                          <span>类型: {rule.typeName || rule.type}</span>
                          <span className="flex items-center gap-1">
                            级别:
                            {rule.severity === "critical" ? (
                              <span className="font-medium text-destructive">严重</span>
                            ) : rule.severity === "warning" ? (
                              <span className="font-medium text-amber-600">警告</span>
                            ) : (
                              <span>{rule.severity}</span>
                            )}
                          </span>
                          {rule.industryName && <span>行业: {rule.industryName}</span>}
                        </div>
                      </div>
                    </div>

                    <button
                      className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <MoreVertical className="h-5 w-5" />
                    </button>
                  </div>

                  <div className="space-y-4 p-5">
                    <p className="text-sm text-muted-foreground">
                      {rule.description ?? rule.errorMessage ?? "暂无描述"}
                    </p>

                    {((rule.sourceSections?.length ?? 0) > 0 || (rule.targetSections?.length ?? 0) > 0) && (
                      <div className="grid grid-cols-1 gap-6 text-sm md:grid-cols-2">
                        <div className="space-y-2">
                          <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                            涉及章节
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {(rule.sourceSections ?? []).map((section, index) => (
                              <span
                                key={`src-${index}`}
                                className="rounded bg-muted px-2 py-1 text-foreground"
                              >
                                [{section}]
                              </span>
                            ))}
                            {((rule.targetSections?.length ?? 0) > 0) && (
                              <ChevronRight className="h-4 w-4 self-center text-muted-foreground" />
                            )}
                            {(rule.targetSections ?? []).map((section, index) => (
                              <span
                                key={`tgt-${index}`}
                                className="rounded bg-secondary px-2 py-1 text-primary"
                              >
                                [{section}]
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
                      <div>
                        {rule.seedVersion && <span className="mr-4">种子版本: {rule.seedVersion}</span>}
                        {rule.updatedAt && (
                          <span>更新: {new Date(rule.updatedAt).toLocaleDateString()}</span>
                        )}
                      </div>

                      <div className="flex gap-4">
                        {showManagement && !readOnly && (
                          <button
                            className="font-medium text-primary transition-colors hover:text-primary/70 hover:underline"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedRuleId(rule.ruleId ?? null);
                            }}
                          >
                            编辑
                          </button>
                        )}
                        {showManagement && (
                          <button
                            className="font-medium text-primary transition-colors hover:text-primary/70 hover:underline"
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleViewLogs(rule);
                            }}
                          >
                            查看日志
                          </button>
                        )}
                        {showManagement && (
                          <button
                            className="flex items-center gap-1 font-medium text-primary transition-colors hover:text-primary/70 hover:underline"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleTestRule(rule);
                            }}
                          >
                            <Terminal className="h-3 w-3" />
                            测试规则
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}

          {!loading && !error && total > limit && (
            <div className="flex items-center justify-center gap-4 py-4">
              <button
                className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={page <= 1}
                onClick={() => handleFilterChange("page", page - 1)}
              >
                上一页
              </button>
              <span className="text-sm text-muted-foreground">
                第 {page} / {Math.ceil(total / limit)} 页
              </span>
              <button
                className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={page >= Math.ceil(total / limit)}
                onClick={() => handleFilterChange("page", page + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>

      {showCreatePanel && !effectiveSelectionMode && (
        <RuleCreatePanel
          onClose={() => setShowCreatePanel(false)}
          onCreated={handleRuleCreated}
          dictionaries={dictionaries}
        />
      )}

      {selectedRule && !effectiveSelectionMode && !showCreatePanel && (
        <RuleDetail
          rule={selectedRule}
          onClose={() => setSelectedRuleId(null)}
          onUpdate={handleRuleUpdated}
          onDelete={handleRuleDeletedInPanel}
          onTestRule={() => handleTestRule(selectedRule)}
          onViewLogs={() => {
            void handleViewLogs(selectedRule);
          }}
          readOnly={readOnly || !showManagement}
          dictionaries={dictionaries}
        />
      )}

      {showSeedManager && seedStatus && (
        <SeedDataManager
          status={seedStatus}
          onImport={handleImportSeed}
          onClose={() => {
            setShowSeedManager(false);
            refresh();
          }}
        />
      )}

      {logsModalRule && (
        <RuleLogsViewer
          logs={logs}
          statistics={logStatistics ?? undefined}
          loading={loadingLogs}
          onClose={handleCloseLogs}
        />
      )}

      {testModalRule && (
        <RuleTestModal
          ruleId={testModalRule.ruleId}
          ruleName={testModalRule.name}
          onClose={handleCloseTest}
        />
      )}
    </div>
  );
}
