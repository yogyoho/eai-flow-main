/**
 * 合规规则管理组件
 */

import {
  ShieldCheck,
  RefreshCw,
  Database,
  AlertCircle,
  Plus,
  Search,
  ChevronRight,
  Terminal,
} from "lucide-react";
import React, { useState, useCallback, useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchRules,
  fetchRuleStatistics,
  fetchSeedStatus,
  importSeedRules,
  toggleRuleEnabled,
  fetchRuleLogs,
  fetchRuleExecutionStatistics,
  fetchTriggerStatistics,
  type RuleExecutionLog,
  type RuleExecutionStatistics,
  type TriggerStatistics,
} from "@/extensions/knowledge-factory/complianceRulesApi";
import { RuleCard } from "./RuleCard";
import { RuleDetail } from "./RuleDetail";
import { SeedDataManager } from "./SeedDataManager";
import { RuleLogsViewer } from "./RuleLogsViewer";
import { RuleTestModal } from "./RuleTestModal";
import {
  type ComplianceRule,
  type ComplianceRuleListResponse,
  type ComplianceRuleStatistics,
  type ComplianceRuleStatus,
  type RuleFilterParams,
  RULE_TYPES,
  SEVERITY_LEVELS,
  INDUSTRIES,
  REPORT_TYPES,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface ComplianceRulesProps {
  /** 是否显示管理功能（如导入、编辑、删除） */
  showManagement?: boolean;
  /** 只读模式 */
  readOnly?: boolean;
  /** 选择模式 */
  selectionMode?: boolean;
  /** 选中的规则ID列表 */
  selectedRules?: string[];
  /** 选中规则回调 */
  onSelectionChange?: (ruleIds: string[]) => void;
  /** 初始筛选参数 */
  initialFilters?: RuleFilterParams;
}

export function ComplianceRules({
  showManagement = true,
  readOnly = false,
  selectionMode = false,
  selectedRules: initialSelectedRules = [],
  onSelectionChange,
  initialFilters,
}: ComplianceRulesProps) {
  // 状态
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [selectedRules, setSelectedRules] = useState<string[]>(initialSelectedRules);
  const [showSeedManager, setShowSeedManager] = useState(false);

  // 日志弹窗状态
  const [logsModalRule, setLogsModalRule] = useState<ComplianceRule | null>(null);
  const [logs, setLogs] = useState<RuleExecutionLog[]>([]);
  const [logStatistics, setLogStatistics] = useState<RuleExecutionStatistics | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);

  // 测试弹窗状态
  const [testModalRule, setTestModalRule] = useState<ComplianceRule | null>(null);

  // 统计数据
  const [statistics, setStatistics] = useState<ComplianceRuleStatistics | null>(null);
  const [seedStatus, setSeedStatus] = useState<ComplianceRuleStatus | null>(null);
  const [triggerStats, setTriggerStats] = useState<TriggerStatistics | null>(null);

  // 筛选状态
  const [filters, setFilters] = useState<RuleFilterParams>({
    ...initialFilters,
    page: 1,
    limit: 20,
  });

  // 加载规则列表
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

  // 加载统计数据
  const loadStatistics = useCallback(async () => {
    try {
      const stats = await fetchRuleStatistics();
      setStatistics(stats);
      // 同时加载触发统计
      const triggers = await fetchTriggerStatistics();
      setTriggerStats(triggers);
    } catch (err) {
      console.error("加载统计数据失败:", err);
    }
  }, []);

  // 加载规则执行日志
  const loadRuleLogs = useCallback(async (ruleId: string) => {
    setLoadingLogs(true);
    try {
      const [logsData, statsData] = await Promise.all([
        fetchRuleLogs(ruleId),
        fetchRuleExecutionStatistics(ruleId),
      ]);
      setLogs(logsData.logs);
      setLogStatistics(statsData);
    } catch (err) {
      console.error("加载规则日志失败:", err);
    } finally {
      setLoadingLogs(false);
    }
  }, []);

  // 查看日志
  const handleViewLogs = async (rule: ComplianceRule) => {
    if (!rule.ruleId) return;
    setLogsModalRule(rule);
    await loadRuleLogs(rule.ruleId);
  };

  // 关闭日志弹窗
  const handleCloseLogs = () => {
    setLogsModalRule(null);
    setLogs([]);
    setLogStatistics(null);
  };

  // 测试规则
  const handleTestRule = (rule: ComplianceRule) => {
    setTestModalRule(rule);
  };

  // 关闭测试弹窗
  const handleCloseTest = () => {
    setTestModalRule(null);
  };

  // 加载种子数据状态
  const loadSeedStatus = useCallback(async () => {
    try {
      const status = await fetchSeedStatus();
      setSeedStatus(status);
    } catch (err) {
      console.error("加载种子数据状态失败:", err);
    }
  }, []);

  // 初始加载
  useEffect(() => {
    loadRules();
    if (showManagement) {
      loadStatistics();
      loadSeedStatus();
    }
  }, [loadRules, loadStatistics, loadSeedStatus, showManagement]);

  // 切换筛选条件
  const handleFilterChange = (key: keyof RuleFilterParams, value: string | boolean | number | undefined) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      page: 1, // 重置页码
    }));
  };

  // 清除筛选
  const clearFilters = () => {
    setFilters({
      page: 1,
      limit: 20,
    });
  };

  // 刷新列表
  const handleRefresh = () => {
    loadRules();
    loadStatistics();
    loadSeedStatus();
  };

  // 选择规则
  const handleSelectRule = (ruleId: string) => {
    setSelectedRuleId(ruleId);
  };

  // 关闭详情
  const handleCloseDetail = () => {
    setSelectedRuleId(null);
  };

  // 规则更新回调
  const handleRuleUpdated = () => {
    handleRefresh();
    setSelectedRuleId(null);
  };

  // 规则删除回调
  const handleRuleDeleted = (ruleId: string) => {
    setRules((prev) => prev.filter((r) => r.id !== ruleId));
    setSelectedRuleId(null);
    loadStatistics();
  };

  // 切换选中规则（选择模式）
  const handleToggleRuleSelection = (ruleId: string) => {
    const newSelection = selectedRules.includes(ruleId)
      ? selectedRules.filter((id) => id !== ruleId)
      : [...selectedRules, ruleId];
    setSelectedRules(newSelection);
    onSelectionChange?.(newSelection);
  };

  // 全选/取消全选
  const handleSelectAll = () => {
    if (selectedRules.length === rules.length) {
      setSelectedRules([]);
      onSelectionChange?.([]);
    } else {
      const allIds = rules.map((r) => r.id);
      setSelectedRules(allIds);
      onSelectionChange?.(allIds);
    }
  };

  // 导入种子数据
  const handleImportSeed = async (forceUpdate: boolean) => {
    try {
      const result = await importSeedRules(forceUpdate);
      if (result.success) {
        handleRefresh();
      }
      return result;
    } catch (err) {
      throw err;
    }
  };

  // 获取当前选中的规则
  const selectedRule = selectedRuleId
    ? rules.find((r) => r.id === selectedRuleId)
    : null;

  // 计算是否有活跃筛选
  const hasActiveFilters = !!(
    filters.industry ||
    filters.reportType ||
    filters.type ||
    filters.severity ||
    filters.enabled !== undefined
  );

  return (
    <div className="flex h-full flex-col">
      {/* 头部统计和操作栏 */}
      {showManagement && (
        <div className="shrink-0 border-b border-border bg-card p-4">
          <div className="flex items-center justify-between">
            {/* 统计卡片 */}
            <div className="flex gap-6">
              {statistics ? (
                <>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">总计</span>
                    <span className="text-xl font-bold text-foreground">
                      {statistics.total}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">启用</span>
                    <span className="text-xl font-bold text-emerald-600">
                      {statistics.enabled}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">禁用</span>
                    <span className="text-xl font-bold text-muted-foreground">
                      {statistics.disabled}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex gap-4">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex flex-col">
                      <Skeleton className="h-3 w-12 mb-1" />
                      <Skeleton className="h-6 w-8" />
                    </div>
                  ))}
                </div>
              )}
              {triggerStats && (
                <>
                  <div className="ml-4 flex flex-col">
                    <span className="text-xs text-muted-foreground">本月触发</span>
                    <span className="text-xl font-bold text-primary">
                      {triggerStats.monthTriggers.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">拦截问题</span>
                    <span className="text-xl font-bold text-destructive">
                      {triggerStats.monthBlocked}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleRefresh}>
                <RefreshCw className="mr-1.5 h-4 w-4" />
                刷新
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowSeedManager(true)}
              >
                <Database className="mr-1.5 h-4 w-4" />
                种子数据
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 筛选栏 */}
      <div className="shrink-0 border-b border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={filters.industry || "all"}
            onValueChange={(value) =>
              handleFilterChange("industry", value === "all" ? undefined : value)
            }
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="全部行业" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部行业</SelectItem>
              {INDUSTRIES.map((ind) => (
                <SelectItem key={ind.value} value={ind.value}>
                  {ind.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={filters.type || "all"}
            onValueChange={(value) =>
              handleFilterChange("type", value === "all" ? undefined : value)
            }
          >
            <SelectTrigger className="w-36">
              <SelectValue placeholder="全部类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              {RULE_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={filters.severity || "all"}
            onValueChange={(value) =>
              handleFilterChange("severity", value === "all" ? undefined : value)
            }
          >
            <SelectTrigger className="w-32">
              <SelectValue placeholder="全部级别" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部级别</SelectItem>
              {SEVERITY_LEVELS.map((sev) => (
                <SelectItem key={sev.value} value={sev.value}>
                  {sev.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={filters.reportType || "all"}
            onValueChange={(value) =>
              handleFilterChange("reportType", value === "all" ? undefined : value)
            }
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="全部报告类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部报告类型</SelectItem>
              {REPORT_TYPES.map((rt) => (
                <SelectItem key={rt.value} value={rt.value}>
                  {rt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={
              filters.enabled === undefined
                ? "all"
                : filters.enabled
                ? "true"
                : "false"
            }
            onValueChange={(value) => {
              if (value === "all") {
                handleFilterChange("enabled", undefined);
              } else {
                handleFilterChange("enabled", value === "true");
              }
            }}
          >
            <SelectTrigger className="w-28">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="true">已启用</SelectItem>
              <SelectItem value="false">已禁用</SelectItem>
            </SelectContent>
          </Select>

          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索规则..."
              className="pl-10"
              value={filters.keyword || ""}
              onChange={(e) => handleFilterChange("keyword", e.target.value || undefined)}
            />
          </div>

          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              清除筛选
            </Button>
          )}

          <span className="ml-auto text-sm text-muted-foreground">
            共 {total} 条规则
          </span>
        </div>
      </div>

      {/* 内容区域 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 规则列表 */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* 选择模式头部 */}
          {selectionMode && (
            <div className="mb-4 flex items-center justify-between rounded-xl border border-border bg-muted p-4">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedRules.length === rules.length && rules.length > 0}
                  onChange={handleSelectAll}
                  className="h-4 w-4"
                />
                <span className="text-sm font-medium">全选</span>
              </label>
              <span className="text-sm text-muted-foreground">
                已选择 {selectedRules.length} 条规则
              </span>
            </div>
          )}

          {/* 加载状态 */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <RefreshCw className="mb-4 h-8 w-8 animate-spin" />
              <span>加载中...</span>
            </div>
          )}

          {/* 错误状态 */}
          {error && (
            <div className="flex flex-col items-center justify-center py-16 text-destructive">
              <AlertCircle className="mb-4 h-8 w-8" />
              <span className="mb-2 text-lg font-medium">{error}</span>
              <Button variant="outline" size="sm" onClick={loadRules}>
                重试
              </Button>
            </div>
          )}

          {/* 空状态 */}
          {!loading && !error && rules.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <span className="mb-4 text-4xl">📋</span>
              <span className="mb-2 text-lg">
                {hasActiveFilters ? "没有符合条件的规则" : "暂无规则"}
              </span>
              {hasActiveFilters && (
                <Button variant="link" size="sm" onClick={clearFilters}>
                  清除筛选
                </Button>
              )}
            </div>
          )}

          {/* 规则卡片列表 */}
          {!loading && !error && rules.length > 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {rules.map((rule) => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  selected={selectedRuleId === rule.id}
                  selectionMode={selectionMode}
                  checked={selectedRules.includes(rule.id)}
                  onSelect={() => handleSelectRule(rule.id)}
                  onToggleSelect={() => handleToggleRuleSelection(rule.id)}
                  readOnly={readOnly}
                  onToggleEnabled={
                    showManagement && !readOnly
                      ? async (enabled) => {
                          await toggleRuleEnabled(rule.id, enabled);
                          handleRefresh();
                        }
                      : undefined
                  }
                  onViewLogs={showManagement ? () => handleViewLogs(rule) : undefined}
                  onTestRule={showManagement ? () => handleTestRule(rule) : undefined}
                />
              ))}
            </div>
          )}

          {/* 分页 */}
          {!loading && !error && total > limit && (
            <div className="flex items-center justify-center gap-4 py-4">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => handleFilterChange("page", page - 1)}
              >
                上一页
              </Button>
              <span className="text-sm text-muted-foreground">
                第 {page} / {Math.ceil(total / limit)} 页
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= Math.ceil(total / limit)}
                onClick={() => handleFilterChange("page", page + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </div>

        {/* 规则详情侧边栏 */}
        {selectedRule && !selectionMode && (
          <RuleDetail
            rule={selectedRule}
            onClose={handleCloseDetail}
            onUpdate={handleRuleUpdated}
            onDelete={handleRuleDeleted}
            onTestRule={() => handleTestRule(selectedRule)}
            onViewLogs={() => handleViewLogs(selectedRule)}
            readOnly={readOnly || !showManagement}
          />
        )}
      </div>

      {/* 种子数据管理弹窗 */}
      {showSeedManager && seedStatus && (
        <SeedDataManager
          status={seedStatus}
          onImport={handleImportSeed}
          onClose={() => {
            setShowSeedManager(false);
            handleRefresh();
          }}
        />
      )}

      {/* 执行日志弹窗 */}
      {logsModalRule && (
        <RuleLogsViewer
          logs={logs}
          statistics={logStatistics || undefined}
          loading={loadingLogs}
          onClose={handleCloseLogs}
        />
      )}

      {/* 测试规则弹窗 */}
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
