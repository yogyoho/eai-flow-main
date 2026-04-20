import type { ComplianceRuleImportResponse } from "@/extensions/knowledge-factory/types";

export function mapRuleImportResponse(
  data: Record<string, unknown>
): ComplianceRuleImportResponse {
  return {
    success: data.success as boolean,
    total: data.total as number,
    created: data.created as number,
    updated: data.updated as number,
    skipped: data.skipped as number,
    errors: data.errors as number,
    errorMessages: (data.error_messages as string[]) ?? [],
  };
}
