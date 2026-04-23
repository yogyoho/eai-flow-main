/**
 * 合规性检查 API
 */

import type {
  ComplianceCheckRequest,
  ComplianceCheckResponse,
  ValidationIssue,
} from "@/extensions/knowledge-factory/types";
import { authFetch } from "@/extensions/api/client";
import { buildLawLibraryUrl } from "./law-library-api";

/**
 * 执行合规性检查
 */
export async function checkCompliance(
  request: ComplianceCheckRequest
): Promise<ComplianceCheckResponse> {
  const url = buildLawLibraryUrl("/kf/rules/check");
  return authFetch<ComplianceCheckResponse>(url, {
    method: "POST",
    body: JSON.stringify(request),
  }, "");
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
  const params = new URLSearchParams({ rule_id: ruleId });
  const url = buildLawLibraryUrl(`/kf/rules/check-single?${params}`);

  return authFetch<{
    success: boolean;
    issues: ValidationIssue[];
    duration_ms: number;
  }>(url, {
    method: "POST",
    body: JSON.stringify({
      report_data: reportData,
      extracted_fields: extractedFields || {},
    }),
  }, "");
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
  const url = buildLawLibraryUrl(`/kf/rules/validate/${ruleId}`);
  return authFetch<{
    rule_id: string;
    type: string;
    validator_registered: boolean;
    validation_config: Record<string, unknown>;
    enabled: boolean;
  }>(url, undefined, "");
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