import test from "node:test";
import assert from "node:assert/strict";

import { updateRuleFilters } from "./rule-filter-utils";

test("keeps requested page when updating page filter", () => {
  const next = updateRuleFilters(
    { industry: "environmental", page: 1, limit: 20 },
    "page",
    2
  );

  assert.equal(next.page, 2);
  assert.equal(next.industry, "environmental");
  assert.equal(next.limit, 20);
});

test("resets page to 1 when updating non-page filters", () => {
  const next = updateRuleFilters(
    { industry: "environmental", page: 3, limit: 20 },
    "severity",
    "critical"
  );

  assert.equal(next.page, 1);
  assert.equal(next.severity, "critical");
});
