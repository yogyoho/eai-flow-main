import assert from "node:assert/strict";
import test from "node:test";

const { mergeRuleDictionaries, getDictionaryLabel } = await import("./rule-dictionary-utils.ts");

test("mergeRuleDictionaries falls back to defaults when remote dictionaries are incomplete", () => {
  const dictionaries = mergeRuleDictionaries({
    industries: [{ value: "custom_industry", label: "自定义行业" }],
    reportTypes: [],
  });

  assert.equal(dictionaries.industries[0]?.value, "custom_industry");
  assert.equal(dictionaries.reportTypes[0]?.value, "coal_mining_planning_eia");
  assert.equal(dictionaries.regions[0]?.value, "nationwide");
});

test("getDictionaryLabel falls back to raw value for unknown options", () => {
  assert.equal(
    getDictionaryLabel([{ value: "jilin", label: "吉林" }], "jilin"),
    "吉林"
  );
  assert.equal(getDictionaryLabel([], "unknown"), "unknown");
});
