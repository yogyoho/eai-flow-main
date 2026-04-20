import type { RuleFilterParams } from "@/extensions/knowledge-factory/types";

export function updateRuleFilters(
  prev: RuleFilterParams,
  key: keyof RuleFilterParams,
  value: string | boolean | number | undefined
): RuleFilterParams {
  if (key === "page") {
    return {
      ...prev,
      page: typeof value === "number" ? value : 1,
    };
  }

  if (key === "limit") {
    return {
      ...prev,
      limit: typeof value === "number" ? value : prev.limit,
      page: 1,
    };
  }

  return {
    ...prev,
    [key]: value,
    page: 1,
  };
}
