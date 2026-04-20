import test from "node:test";
import assert from "node:assert/strict";

const { mapRuleImportResponse } = await import("./rule-import-utils.ts");

test("mapRuleImportResponse maps error_messages to errorMessages", () => {
  const result = mapRuleImportResponse({
    success: true,
    total: 10,
    created: 2,
    updated: 3,
    skipped: 5,
    errors: 1,
    error_messages: ["CSR-001 导入失败"],
  });

  assert.deepEqual(result.errorMessages, ["CSR-001 导入失败"]);
  assert.equal(result.errors, 1);
});
