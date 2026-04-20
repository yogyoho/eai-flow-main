import assert from "node:assert/strict";
import test from "node:test";

const { buildRuleUpdatePayload, formatValidationConfig, getRegionLabel } =
  await import("./rule-detail-utils.ts");

test("buildRuleUpdatePayload normalizes nationwide, sections, and validation config", () => {
  const payload = buildRuleUpdatePayload({
    rule: {
      id: "1",
      ruleId: "CSR-001",
      name: " Rule Name ",
      type: "standard_check",
      typeName: "",
      severity: "critical",
      severityName: "",
      enabled: true,
      description: " desc ",
      industry: "environmental",
      industryName: "",
      reportTypes: ["coal_mining_project_eia"],
      applicableRegions: ["jilin"],
      nationalLevel: true,
      sourceSections: [],
      targetSections: [],
      validationConfig: { fields: [], comparisonType: "exact_match" },
      errorMessage: " error ",
      autoFixSuggestion: " fix ",
      seedVersion: "1.0.0",
      createdAt: "2026-04-05T00:00:00Z",
      updatedAt: "2026-04-05T00:00:00Z",
    },
    sourceSectionsInput: "A, B",
    targetSectionsInput: "C",
    validationConfigText: JSON.stringify({
      fields: [{ fieldName: "SO2", limit: 10 }],
      comparisonType: "max_limit",
    }),
  });

  assert.equal(payload.typeName, "标准达标检查");
  assert.equal(payload.severityName, "严重");
  assert.equal(payload.industryName, "环境保护");
  assert.deepEqual(payload.applicableRegions, ["nationwide"]);
  assert.deepEqual(payload.sourceSections, ["A", "B"]);
  assert.deepEqual(payload.targetSections, ["C"]);
  assert.equal(payload.validationConfig?.comparisonType, "max_limit");
  assert.equal(payload.description, "desc");
});

test("buildRuleUpdatePayload removes nationwide for local rules", () => {
  const payload = buildRuleUpdatePayload({
    rule: {
      id: "1",
      ruleId: "CSR-002",
      name: "Local Rule",
      type: "standard_check",
      typeName: "标准达标检查",
      severity: "warning",
      severityName: "警告",
      enabled: true,
      description: "",
      industry: "environmental",
      industryName: "环境保护",
      reportTypes: ["coal_mining_project_eia"],
      applicableRegions: ["nationwide", "jilin"],
      nationalLevel: false,
      sourceSections: [],
      targetSections: [],
      validationConfig: { fields: [], comparisonType: "exact_match" },
      errorMessage: "",
      autoFixSuggestion: "",
      seedVersion: undefined,
      createdAt: "2026-04-05T00:00:00Z",
      updatedAt: "2026-04-05T00:00:00Z",
    },
    sourceSectionsInput: "",
    targetSectionsInput: "",
    validationConfigText: JSON.stringify({
      fields: [],
      comparisonType: "exact_match",
    }),
  });

  assert.deepEqual(payload.applicableRegions, ["jilin"]);
});

test("buildRuleUpdatePayload rejects invalid validation config json", () => {
  assert.throws(
    () =>
      buildRuleUpdatePayload({
        rule: {
          id: "1",
          ruleId: "CSR-003",
          name: "Rule",
          type: "standard_check",
          typeName: "标准达标检查",
          severity: "warning",
          severityName: "警告",
          enabled: true,
          description: "",
          industry: "environmental",
          industryName: "环境保护",
          reportTypes: ["coal_mining_project_eia"],
          applicableRegions: ["jilin"],
          nationalLevel: false,
          sourceSections: [],
          targetSections: [],
          validationConfig: { fields: [], comparisonType: "exact_match" },
          errorMessage: "",
          autoFixSuggestion: "",
          seedVersion: undefined,
          createdAt: "2026-04-05T00:00:00Z",
          updatedAt: "2026-04-05T00:00:00Z",
        },
        sourceSectionsInput: "",
        targetSectionsInput: "",
        validationConfigText: "{bad json}",
      }),
    /合法/
  );
});

test("formatValidationConfig pretty prints json", () => {
  assert.match(
    formatValidationConfig({ fields: [], comparisonType: "exact_match" }),
    /\n/
  );
});

test("getRegionLabel resolves known region labels", () => {
  assert.equal(getRegionLabel("jilin"), "吉林");
  assert.equal(getRegionLabel("unknown"), "unknown");
});
