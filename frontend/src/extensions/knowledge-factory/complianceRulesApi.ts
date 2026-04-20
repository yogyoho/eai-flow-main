import { mapRuleImportResponse } from "./rule-import-utils";
import { mapRuleOverviewResponse } from "./rule-overview-utils";
import {
  buildRuleTestRequestBody,
  type RuleTestPayload,
} from "./rule-test-utils";
import type {
  ComplianceRule,
  ComplianceRuleCreate,
  ComplianceRuleUpdate,
  ComplianceRuleListResponse,
  ComplianceRuleImportResponse,
  ComplianceRuleOverview,
  RuleDictionaries,
  ComplianceRuleStatus,
  ComplianceRuleStatistics,
  RuleFilterParams,
} from "@/extensions/knowledge-factory/types";

const API_BASE = "/api/kf";

export async function fetchRuleDictionaries(): Promise<RuleDictionaries> {
  const response = await fetch(`${API_BASE}/rule-dictionaries`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则字典失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    industries: (data.industries as RuleDictionaries["industries"]) ?? [],
    reportTypes: (data.report_types as RuleDictionaries["reportTypes"]) ?? [],
    regions: (data.regions as RuleDictionaries["regions"]) ?? [],
  };
}

/**
 * 获取规则列表
 */
export async function fetchRules(params: RuleFilterParams = {}): Promise<ComplianceRuleListResponse> {
  const searchParams = new URLSearchParams();

  if (params.industry) searchParams.set("industry", params.industry);
  if (params.reportType) searchParams.set("report_type", params.reportType);
  if (params.region) searchParams.set("region", params.region);
  if (params.type) searchParams.set("type", params.type);
  if (params.severity) searchParams.set("severity", params.severity);
  if (params.enabled !== undefined) searchParams.set("enabled", String(params.enabled));
  if (params.page) searchParams.set("page", String(params.page));
  if (params.limit) searchParams.set("limit", String(params.limit));

  const query = searchParams.toString();
  const response = await fetch(`${API_BASE}/rules${query ? `?${query}` : ""}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则列表失败: ${response.statusText}`);
  }

  const data = await response.json();

  // 转换 snake_case 到 camelCase
  return {
    rules: data.rules.map(transformRule),
    total: data.total,
    page: data.page,
    limit: data.limit,
  };
}

/**
 * 获取单个规则
 */
export async function fetchRule(ruleId: string): Promise<ComplianceRule> {
  const response = await fetch(`${API_BASE}/rules/${ruleId}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则详情失败: ${response.statusText}`);
  }

  const data = await response.json();
  return transformRule(data);
}

/**
 * 创建规则
 */
export async function createRule(rule: ComplianceRuleCreate): Promise<ComplianceRule> {
  const response = await fetch(`${API_BASE}/rules`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(transformRuleToSnakeCase(rule)),
  });

  if (!response.ok) {
    throw new Error(`创建规则失败: ${response.statusText}`);
  }

  const data = await response.json();
  return transformRule(data);
}

/**
 * 更新规则
 */
export async function updateRule(
  ruleId: string,
  updates: ComplianceRuleUpdate
): Promise<ComplianceRule> {
  const response = await fetch(`${API_BASE}/rules/${ruleId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(transformRuleToSnakeCase(updates)),
  });

  if (!response.ok) {
    throw new Error(`更新规则失败: ${response.statusText}`);
  }

  const data = await response.json();
  return transformRule(data);
}

/**
 * 删除规则
 */
export async function deleteRule(ruleId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/rules/${ruleId}`, {
    method: "DELETE",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`删除规则失败: ${response.statusText}`);
  }
}

/**
 * 导入种子数据
 */
export async function importSeedRules(forceUpdate = false): Promise<ComplianceRuleImportResponse> {
  const response = await fetch(`${API_BASE}/rules/import-seed?force_update=${forceUpdate}`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`导入种子数据失败: ${response.statusText}`);
  }

  const data = await response.json();
  return mapRuleImportResponse(data);
}

/**
 * 获取种子数据状态
 */
export async function fetchSeedStatus(): Promise<ComplianceRuleStatus> {
  const response = await fetch(`${API_BASE}/rules/seed-status`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取种子数据状态失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    seedVersion: data.seed_version,
    seedTotal: data.seed_total,
    dbTotal: data.db_total,
    dbEnabled: data.db_enabled,
    dbDisabled: data.db_disabled,
    inSeedNotInDb: data.in_seed_not_in_db,
    inDbNotInSeed: data.in_db_not_in_seed,
    upToDate: data.up_to_date,
  };
}

/**
 * 获取规则引擎页面总览
 */
export async function fetchRuleOverview(): Promise<ComplianceRuleOverview> {
  const response = await fetch(`${API_BASE}/rules/overview`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则总览失败: ${response.statusText}`);
  }

  const data = await response.json();
  return mapRuleOverviewResponse(data);
}

/**
 * 获取规则统计
 */
export async function fetchRuleStatistics(): Promise<ComplianceRuleStatistics> {
  const response = await fetch(`${API_BASE}/rules/statistics`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则统计失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    total: data.total,
    enabled: data.enabled,
    disabled: data.disabled,
    fromSeed: data.from_seed,
    typeDistribution: data.type_distribution,
    severityDistribution: data.severity_distribution,
    industryDistribution: data.industry_distribution,
  };
}

/**
 * 切换规则启用状态
 */
export async function toggleRuleEnabled(ruleId: string, enabled: boolean): Promise<ComplianceRule> {
  return updateRule(ruleId, { enabled });
}

/**
 * 转换后端规则数据 (snake_case) 到前端格式 (camelCase)
 */
function transformRule(data: Record<string, unknown>): ComplianceRule {
  return {
    id: data.id as string,
    ruleId: data.rule_id as string,
    name: data.name as string,
    type: data.type as string,
    typeName: data.type_name as string || "",
    severity: data.severity as string,
    severityName: data.severity_name as string || "",
    enabled: data.enabled as boolean,
    description: (data.description as string) || "",
    industry: (data.industry as string) || "",
    industryName: data.industry_name as string || "",
    reportTypes: (data.report_types as string[]) || [],
    applicableRegions: (data.applicable_regions as string[]) || [],
    nationalLevel: data.national_level as boolean,
    sourceSections: (data.source_sections as string[]) || [],
    targetSections: (data.target_sections as string[]) || [],
    validationConfig: (data.validation_config as ComplianceRule["validationConfig"]) || { fields: [], comparisonType: "" },
    errorMessage: (data.error_message as string) || "",
    autoFixSuggestion: (data.auto_fix_suggestion as string) || "",
    seedVersion: (data.seed_version as string) || "",
    createdAt: data.created_at as string,
    updatedAt: data.updated_at as string,
  };
}

/**
 * 转换前端规则数据 (camelCase) 到后端格式 (snake_case)
 */
function transformRuleToSnakeCase(
  data: ComplianceRuleCreate | Partial<ComplianceRuleCreate>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  const fieldMap: Record<string, string> = {
    ruleId: "rule_id",
    typeName: "type_name",
    severityName: "severity_name",
    reportTypes: "report_types",
    applicableRegions: "applicable_regions",
    nationalLevel: "national_level",
    sourceSections: "source_sections",
    targetSections: "target_sections",
    validationConfig: "validation_config",
    errorMessage: "error_message",
    autoFixSuggestion: "auto_fix_suggestion",
    seedVersion: "seed_version",
    createdAt: "created_at",
    updatedAt: "updated_at",
  };

  for (const [key, value] of Object.entries(data)) {
    if (fieldMap[key]) {
      result[fieldMap[key]] = value;
    } else {
      result[key] = value;
    }
  }

  return result;
}

/**
 * 加载种子数据文件（前端直接从 JSON 文件加载）
 */
export async function loadSeedDataFromFile(): Promise<ComplianceRule[]> {
  try {
    const response = await fetch("/extensions/knowledge-factory/data/compliance_rules_seed.json");
    if (!response.ok) {
      throw new Error(`加载种子数据文件失败: ${response.statusText}`);
    }
    const data = await response.json();
    return data.rules ?? [];
  } catch (error) {
    console.error("加载种子数据文件失败:", error);
    return [];
  }
}


// ============== 日志和统计 API ==============

/** 规则执行日志 */
export interface RuleExecutionLog {
  id: string;
  checkResult: string;
  checkDetails: Record<string, unknown>;
  errorInfo: string | null;
  threadId: string | null;
  documentId: string | null;
  executedAt: string;
}

/** 规则执行统计 */
export interface RuleExecutionStatistics {
  ruleId: string;
  ruleName: string;
  totalExecutions: number;
  passCount: number;
  failCount: number;
  warningCount: number;
  errorCount: number;
  lastExecutedAt: string | null;
  lastFailedAt: string | null;
}

/** 全局触发统计 */
export interface TriggerStatistics {
  totalTriggers: number;
  blockedTriggers: number;
  monthTriggers: number;
  monthBlocked: number;
  passRate: number;
}

/**
 * 获取规则执行日志
 */
export async function fetchRuleLogs(
  ruleId: string,
  limit = 50,
  offset = 0
): Promise<{
  ruleId: string;
  total: number;
  logs: RuleExecutionLog[];
}> {
  const response = await fetch(
    `${API_BASE}/rules/${ruleId}/logs?limit=${limit}&offset=${offset}`,
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error(`获取规则日志失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    ruleId: data.rule_id,
    total: data.total,
    logs: (data.logs ?? []).map((log: Record<string, unknown>) => ({
      id: log.id as string,
      checkResult: log.check_result as string,
      checkDetails: (log.check_details as Record<string, unknown>) || {},
      errorInfo: log.error_info as string | null,
      threadId: log.thread_id as string | null,
      documentId: log.document_id as string | null,
      executedAt: log.executed_at as string,
    })),
  };
}

/**
 * 获取规则执行统计
 */
export async function fetchRuleExecutionStatistics(
  ruleId: string
): Promise<RuleExecutionStatistics> {
  const response = await fetch(`${API_BASE}/rules/${ruleId}/statistics`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`获取规则统计失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    ruleId: data.rule_id,
    ruleName: data.rule_name,
    totalExecutions: data.total_executions,
    passCount: data.pass_count,
    failCount: data.fail_count,
    warningCount: data.warning_count,
    errorCount: data.error_count,
    lastExecutedAt: data.last_executed_at,
    lastFailedAt: data.last_failed_at,
  };
}

/**
 * 获取全局触发统计
 */
export async function fetchTriggerStatistics(
  startDate?: string,
  endDate?: string
): Promise<TriggerStatistics> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);

  const query = params.toString();
  const response = await fetch(
    `${API_BASE}/rules/trigger-statistics${query ? `?${query}` : ""}`,
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error(`获取触发统计失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    totalTriggers: data.total_triggers,
    blockedTriggers: data.blocked_triggers,
    monthTriggers: data.month_triggers,
    monthBlocked: data.month_blocked,
    passRate: data.pass_rate,
  };
}

/**
 * 测试规则
 */
export async function testRule(
  ruleId: string,
  testData: RuleTestPayload
): Promise<{
  success: boolean;
  ruleId: string;
  ruleName: string;
  totalRules: number;
  passed: number;
  failed: number;
  warnings: number;
  issues: Array<{
    ruleId: string;
    ruleName: string;
    severity: string;
    checkResult: string;
    message: string;
    fieldName?: string;
    suggestion?: string;
  }>;
  durationMs: number;
}> {
  const requestBody = buildRuleTestRequestBody(testData);

  const response = await fetch(`${API_BASE}/rules/${ruleId}/test`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    throw new Error(`测试规则失败: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    success: data.success,
    ruleId: data.rule_id,
    ruleName: data.rule_name,
    totalRules: data.total_rules,
    passed: data.passed,
    failed: data.failed,
    warnings: data.warnings,
    issues: data.issues ?? [],
    durationMs: data.duration_ms,
  };
}
