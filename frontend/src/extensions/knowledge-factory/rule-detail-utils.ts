import { parseCommaSeparatedInput } from "./rule-form-utils";
import {
  DEFAULT_RULE_DICTIONARIES,
  RULE_TYPES,
  SEVERITY_LEVELS,
  type ComplianceRule,
  type ComplianceRuleUpdate,
  type RuleDictionaries,
  type ValidationConfig,
} from "@/extensions/knowledge-factory/types";

export function formatValidationConfig(config?: ValidationConfig): string {
  return JSON.stringify(config ?? {}, null, 2);
}

export function getRegionLabel(
  region: string,
  dictionaries: RuleDictionaries = DEFAULT_RULE_DICTIONARIES
): string {
  return dictionaries.regions.find((item) => item.value === region)?.label ?? region;
}

export function buildRuleUpdatePayload(options: {
  rule: ComplianceRule;
  sourceSectionsInput: string;
  targetSectionsInput: string;
  validationConfigText: string;
  dictionaries?: RuleDictionaries;
}): ComplianceRuleUpdate {
  const {
    rule,
    sourceSectionsInput,
    targetSectionsInput,
    validationConfigText,
    dictionaries = DEFAULT_RULE_DICTIONARIES,
  } = options;

  let validationConfig: ValidationConfig;
  try {
    validationConfig = JSON.parse(validationConfigText) as ValidationConfig;
  } catch {
    throw new Error("验证配置不是合法的 JSON");
  }

  if (!validationConfig || !Array.isArray(validationConfig.fields) || typeof validationConfig.comparisonType !== "string") {
    throw new Error("验证配置缺少 fields 或 comparisonType");
  }

  const typeName = RULE_TYPES.find((item) => item.value === rule.type)?.label ?? rule.typeName;
  const severityName =
    SEVERITY_LEVELS.find((item) => item.value === rule.severity)?.label ?? rule.severityName;
  const industryName =
    dictionaries.industries.find((item) => item.value === rule.industry)?.label ?? rule.industryName;

  const applicableRegions = rule.nationalLevel
    ? ["nationwide"]
    : (rule.applicableRegions ?? []).filter((region) => region !== "nationwide");

  return {
    name: rule.name.trim(),
    type: rule.type,
    typeName,
    severity: rule.severity,
    severityName,
    enabled: rule.enabled,
    description: rule.description?.trim() ?? "",
    industry: rule.industry,
    industryName,
    reportTypes: rule.reportTypes,
    applicableRegions,
    nationalLevel: rule.nationalLevel,
    sourceSections: parseCommaSeparatedInput(sourceSectionsInput),
    targetSections: parseCommaSeparatedInput(targetSectionsInput),
    validationConfig,
    errorMessage: rule.errorMessage?.trim() ?? "",
    autoFixSuggestion: rule.autoFixSuggestion?.trim() ?? "",
  };
}
