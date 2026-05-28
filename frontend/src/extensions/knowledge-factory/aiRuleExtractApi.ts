import { authFetch, authFormFetch } from "@/extensions/api/client";

import { buildLawLibraryUrl } from "./law-library-api";
import type { ComplianceRule, ComplianceRuleCreate } from "./types";

export interface ExtractedRule {
  rule_id: string;
  name: string;
  type: string;
  severity: string;
  description: string;
  industry?: string;
  report_types?: string[];
  source_sections?: string[];
  validation_config?: Record<string, unknown>;
  error_message?: string;
  auto_fix_suggestion?: string;
}

export interface ExtractRulesResponse {
  rules: ExtractedRule[];
  total: number;
}

export interface BatchCreateResponse {
  created: number;
  skipped: number;
  errors: string[];
  created_rules: ComplianceRule[];
}

function mapExtractedToCreate(rule: ExtractedRule): ComplianceRuleCreate {
  return {
    ruleId: rule.rule_id,
    name: rule.name,
    type: rule.type,
    typeName: "",
    severity: rule.severity,
    severityName: "",
    enabled: true,
    description: rule.description ?? "",
    industry: rule.industry ?? "",
    industryName: "",
    reportTypes: rule.report_types ?? [],
    applicableRegions: [],
    nationalLevel: true,
    sourceSections: rule.source_sections ?? [],
    targetSections: [],
    validationConfig: (rule.validation_config as unknown as ComplianceRuleCreate["validationConfig"]) ?? { fields: [], comparisonType: "" },
    errorMessage: rule.error_message ?? "",
    autoFixSuggestion: rule.auto_fix_suggestion ?? "",
  };
}

export async function extractRulesFromDocument(
  file: File,
  industry?: string,
  reportTypes?: string[],
): Promise<ExtractRulesResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (industry) formData.append("industry", industry);
  if (reportTypes?.length) formData.append("report_types", reportTypes.join(","));

  return authFormFetch<ExtractRulesResponse>(
    buildLawLibraryUrl("/kf/rules/extract"),
    formData,
    "",
  );
}

export async function batchCreateRules(rules: ComplianceRuleCreate[]): Promise<BatchCreateResponse> {
  const snakeRules = rules.map((r) => ({
    rule_id: r.ruleId,
    name: r.name,
    type: r.type,
    type_name: r.typeName,
    severity: r.severity,
    severity_name: r.severityName,
    enabled: r.enabled,
    description: r.description,
    industry: r.industry,
    industry_name: r.industryName,
    report_types: r.reportTypes,
    applicable_regions: r.applicableRegions,
    national_level: r.nationalLevel,
    source_sections: r.sourceSections,
    target_sections: r.targetSections,
    validation_config: r.validationConfig,
    error_message: r.errorMessage,
    auto_fix_suggestion: r.autoFixSuggestion,
  }));

  return authFetch<BatchCreateResponse>(
    buildLawLibraryUrl("/kf/rules/batch"),
    { method: "POST", body: JSON.stringify({ rules: snakeRules }) },
    "",
  );
}

export { mapExtractedToCreate };
