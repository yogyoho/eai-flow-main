import {
  DEFAULT_RULE_DICTIONARIES,
  type RuleDictionaries,
  type RuleDictionaryOption,
} from "@/extensions/knowledge-factory/types";

function sanitizeOptions(
  options: RuleDictionaryOption[] | undefined,
  fallback: RuleDictionaryOption[]
): RuleDictionaryOption[] {
  if (!options || options.length === 0) {
    return [...fallback];
  }

  return options
    .filter((item) => typeof item?.value === "string" && item.value.length > 0)
    .map((item) => ({
      value: item.value,
      label: typeof item.label === "string" && item.label.length > 0 ? item.label : item.value,
    }));
}

export function mergeRuleDictionaries(
  dictionaries?: Partial<RuleDictionaries> | null
): RuleDictionaries {
  return {
    industries: sanitizeOptions(dictionaries?.industries, DEFAULT_RULE_DICTIONARIES.industries),
    reportTypes: sanitizeOptions(dictionaries?.reportTypes, DEFAULT_RULE_DICTIONARIES.reportTypes),
    regions: sanitizeOptions(dictionaries?.regions, DEFAULT_RULE_DICTIONARIES.regions),
  };
}

export function getDictionaryLabel(
  options: RuleDictionaryOption[],
  value: string
): string {
  return options.find((item) => item.value === value)?.label ?? value;
}
