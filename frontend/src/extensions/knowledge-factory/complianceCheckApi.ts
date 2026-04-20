/**
 * 合规性检查 API
 */

import type {
  ComplianceCheckRequest,
  ComplianceCheckResponse,
  ValidationIssue,
} from "@/extensions/knowledge-factory/types";

const API_BASE = "/api/kf";

/**
 * 执行合规性检查
 */
export async function checkCompliance(
  request: ComplianceCheckRequest
): Promise<ComplianceCheckResponse> {
  const response = await fetch(`${API_BASE}/rules/check`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`合规性检查失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 检查单条规则
 */
export async function checkSingleRule(
  ruleId: string,
  reportData: Record<string, unknown>,
  extractedFields?: Record<string, unknown>
): Promise<{
  success: boolean;
  issues: ValidationIssue[];
  duration_ms: number;
}> {
  const params = new URLSearchParams({
    rule_id: ruleId,
  });

  const response = await fetch(`${API_BASE}/rules/check-single?${params}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      report_data: reportData,
      extracted_fields: extractedFields || {},
    }),
  });

  if (!response.ok) {
    throw new Error(`单条规则检查失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 验证规则配置
 */
export async function validateRule(ruleId: string): Promise<{
  rule_id: string;
  type: string;
  validator_registered: boolean;
  validation_config: Record<string, unknown>;
  enabled: boolean;
}> {
  const response = await fetch(`${API_BASE}/rules/validate/${ruleId}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`验证规则失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 批量检查多条规则
 */
export async function checkMultipleRules(
  ruleIds: string[],
  reportData: Record<string, unknown>,
  extractedFields?: Record<string, unknown>
): Promise<ComplianceCheckResponse> {
  return checkCompliance({
    reportData: reportData,
    extractedFields: extractedFields || {},
    ruleIds: ruleIds,
    checkAll: false,
  });
}