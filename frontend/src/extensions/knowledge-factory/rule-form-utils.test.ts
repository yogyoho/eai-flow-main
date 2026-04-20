import test from "node:test";
import assert from "node:assert/strict";

const {
  buildRuleCreatePayload,
  createEmptyRuleDraft,
  parseCommaSeparatedInput,
  validateRuleDraft,
} = await import("./rule-form-utils.ts");

test("buildRuleCreatePayload normalizes names and nationwide region", () => {
  const draft = createEmptyRuleDraft();
  draft.ruleId = " CSR-100 ";
  draft.name = " 新规则 ";
  draft.nationalLevel = true;
  draft.applicableRegions = ["jilin"];

  const payload = buildRuleCreatePayload(draft, "sec_01, sec_02", "sec_03");

  assert.equal(payload.ruleId, "CSR-100");
  assert.equal(payload.name, "新规则");
  assert.deepEqual(payload.sourceSections, ["sec_01", "sec_02"]);
  assert.deepEqual(payload.targetSections, ["sec_03"]);
  assert.deepEqual(payload.applicableRegions, ["nationwide"]);
});

test("validateRuleDraft requires local rules to pick regions", () => {
  const draft = createEmptyRuleDraft();
  draft.ruleId = "CSR-200";
  draft.name = "地方规则";
  draft.nationalLevel = false;
  draft.applicableRegions = [];

  const errors = validateRuleDraft(draft);

  assert.deepEqual(errors, ["地方规则至少选择一个适用地区"]);
});

test("parseCommaSeparatedInput removes empty items", () => {
  assert.deepEqual(parseCommaSeparatedInput("sec_01, ，\n sec_02"), [
    "sec_01",
    "sec_02",
  ]);
});
