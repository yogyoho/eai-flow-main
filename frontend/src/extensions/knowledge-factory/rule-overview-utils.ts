import type { ComplianceRuleOverview } from "@/extensions/knowledge-factory/types";

export function mapRuleOverviewResponse(data: Record<string, unknown>): ComplianceRuleOverview {
  const statistics = data.statistics as Record<string, unknown>;
  const seedStatus = data.seed_status as Record<string, unknown>;
  const triggerStatistics = data.trigger_statistics as Record<string, unknown>;

  return {
    statistics: {
      total: statistics.total as number,
      enabled: statistics.enabled as number,
      disabled: statistics.disabled as number,
      fromSeed: statistics.from_seed as number,
      typeDistribution: statistics.type_distribution as Record<string, number>,
      severityDistribution: statistics.severity_distribution as Record<string, number>,
      industryDistribution: statistics.industry_distribution as Record<string, number>,
    },
    seedStatus: {
      seedVersion: seedStatus.seed_version as string,
      seedTotal: seedStatus.seed_total as number,
      dbTotal: seedStatus.db_total as number,
      dbEnabled: seedStatus.db_enabled as number,
      dbDisabled: seedStatus.db_disabled as number,
      inSeedNotInDb: seedStatus.in_seed_not_in_db as string[],
      inDbNotInSeed: seedStatus.in_db_not_in_seed as string[],
      upToDate: seedStatus.up_to_date as boolean,
    },
    triggerStatistics: {
      totalTriggers: triggerStatistics.total_triggers as number,
      blockedTriggers: triggerStatistics.blocked_triggers as number,
      monthTriggers: triggerStatistics.month_triggers as number,
      monthBlocked: triggerStatistics.month_blocked as number,
      passRate: triggerStatistics.pass_rate as number,
    },
  };
}
