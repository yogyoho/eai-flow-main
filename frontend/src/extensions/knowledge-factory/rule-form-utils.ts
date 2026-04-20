import {
  DEFAULT_RULE_DICTIONARIES,
  RULE_TYPES,
  SEVERITY_LEVELS,
  type ComplianceRuleCreate,
  type RuleDictionaries,
} from "@/extensions/knowledge-factory/types";

export function createEmptyRuleDraft(
  dictionaries: RuleDictionaries = DEFAULT_RULE_DICTIONARIES
): ComplianceRuleCreate {
  const defaultType = RULE_TYPES.at(0);
  const defaultSeverity = SEVERITY_LEVELS.at(0);
  const defaultIndustry = dictionaries.industries.at(0);
  const defaultReportType = dictionaries.reportTypes.at(0);
  const defaultRegion = dictionaries.regions.at(0) ?? { value: "nationwide", label: "全国" };

  return {
    ruleId: "",
    name: "",
    type: defaultType?.value ?? "content",
    typeName: defaultType?.label ?? "",
    severity: defaultSeverity?.value ?? "error",
    severityName: defaultSeverity?.label ?? "",
    enabled: true,
    description: "",
    industry: defaultIndustry?.value ?? "",
    industryName: defaultIndustry?.label ?? "",
    reportTypes: [defaultReportType?.value ?? ""],
    applicableRegions: [defaultRegion.value],
    nationalLevel: true,
    sourceSections: [],
    targetSections: [],
    validationConfig: {
      fields: [],
      comparisonType: "exact_match",
    },
    errorMessage: "",
    autoFixSuggestion: "",
  };
}

export function parseCommaSeparatedInput(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function buildRuleCreatePayload(
  draft: ComplianceRuleCreate,
  sourceSectionsInput: string,
  targetSectionsInput: string,
  dictionaries: RuleDictionaries = DEFAULT_RULE_DICTIONARIES
): ComplianceRuleCreate {
  const typeName =
    RULE_TYPES.find((item) => item.value === draft.type)?.label ?? draft.typeName;
  const severityName =
    SEVERITY_LEVELS.find((item) => item.value === draft.severity)?.label ??
    draft.severityName;
  const industryName =
    dictionaries.industries.find((item) => item.value === draft.industry)?.label ??
    draft.industryName;

  const applicableRegions = draft.nationalLevel
    ? ["nationwide"]
    : draft.applicableRegions.filter((region) => region !== "nationwide");

  return {
    ...draft,
    ruleId: draft.ruleId.trim(),
    name: draft.name.trim(),
    description: draft.description?.trim() ?? "",
    typeName,
    severityName,
    industryName,
    applicableRegions,
    sourceSections: parseCommaSeparatedInput(sourceSectionsInput),
    targetSections: parseCommaSeparatedInput(targetSectionsInput),
    errorMessage: draft.errorMessage?.trim() ?? "",
    autoFixSuggestion: draft.autoFixSuggestion?.trim() ?? "",
  };
}

export function validateRuleDraft(draft: ComplianceRuleCreate): string[] {
  const errors: string[] = [];

  if (!draft.ruleId.trim()) {
    errors.push("规则ID不能为空");
  }
  if (!draft.name.trim()) {
    errors.push("规则名称不能为空");
  }
  if (!draft.type) {
    errors.push("规则类型不能为空");
  }
  if (!draft.severity) {
    errors.push("严重级别不能为空");
  }
  if (!draft.industry) {
    errors.push("行业不能为空");
  }
  if (draft.reportTypes.length === 0) {
    errors.push("至少选择一个报告类型");
  }
  if (!draft.nationalLevel && draft.applicableRegions.length === 0) {
    errors.push("地方规则至少选择一个适用地区");
  }

  return errors;
}
