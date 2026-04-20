import test from "node:test";
import assert from "node:assert/strict";

const { mapRuleOverviewResponse } = await import("./rule-overview-utils.ts");

test("mapRuleOverviewResponse maps nested snake_case payload to camelCase", () => {
  const overview = mapRuleOverviewResponse({
    statistics: {
      total: 10,
      enabled: 8,
      disabled: 2,
      from_seed: 7,
      type_distribution: { data_consistency: 5 },
      severity_distribution: { critical: 4 },
      industry_distribution: { environmental: 10 },
    },
    seed_status: {
      seed_version: "2026.04",
      seed_total: 12,
      db_total: 10,
      db_enabled: 8,
      db_disabled: 2,
      in_seed_not_in_db: ["CSR-009"],
      in_db_not_in_seed: ["CSR-LOCAL-001"],
      up_to_date: false,
    },
    trigger_statistics: {
      total_triggers: 99,
      blocked_triggers: 20,
      month_triggers: 30,
      month_blocked: 6,
      pass_rate: 79.8,
    },
  });

  assert.equal(overview.statistics.fromSeed, 7);
  assert.equal(overview.seedStatus.seedVersion, "2026.04");
  assert.equal(overview.triggerStatistics.monthBlocked, 6);
  assert.deepEqual(overview.statistics.industryDistribution, { environmental: 10 });
});
