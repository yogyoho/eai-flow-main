import assert from "node:assert/strict";
import test from "node:test";

import {
  areAllRulesSelected,
  getAllSelectedRuleIds,
  toggleRuleSelection,
} from "./rule-selection-utils";

void test("toggleRuleSelection adds unselected rule id", () => {
  assert.deepEqual(toggleRuleSelection(["a"], "b"), ["a", "b"]);
});

void test("toggleRuleSelection removes selected rule id", () => {
  assert.deepEqual(toggleRuleSelection(["a", "b"], "b"), ["a"]);
});

void test("getAllSelectedRuleIds adds all current rule ids when not fully selected", () => {
  assert.deepEqual(getAllSelectedRuleIds(["a", "b"], ["a"]), ["a", "b"]);
});

void test("getAllSelectedRuleIds removes current rule ids when already fully selected", () => {
  assert.deepEqual(getAllSelectedRuleIds(["a", "b"], ["a", "b", "c"]), ["c"]);
});

void test("areAllRulesSelected returns true only when all current ids are selected", () => {
  assert.equal(areAllRulesSelected(["a", "b"], ["a", "b", "c"]), true);
  assert.equal(areAllRulesSelected(["a", "b"], ["a"]), false);
});
