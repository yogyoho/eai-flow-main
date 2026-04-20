import assert from "node:assert/strict";
import test from "node:test";

const { buildRuleTestRequestBody, parseRuleTestInput } = await import(
  new URL("./rule-test-utils.ts", import.meta.url).href
);

void test("maps JSON input to report_data payload", () => {
  const parsed = parseRuleTestInput(`{
    "sections": {
      "sec_03_工程分析": {
        "SO2排放量": "2.3"
      }
    }
  }`);

  const payload = buildRuleTestRequestBody(parsed);

  assert.deepEqual(payload, {
    report_data: {
      sections: {
        sec_03_工程分析: {
          SO2排放量: "2.3",
        },
      },
    },
    extracted_fields: {},
  });
});

void test("maps plain text input to raw_text payload", () => {
  const parsed = parseRuleTestInput(
    "工程分析中 SO2排放量为 2.3 t/a，环境影响预测中 SO2排放量为 2.5 t/a"
  );

  const payload = buildRuleTestRequestBody(parsed);

  assert.deepEqual(payload, {
    raw_text: "工程分析中 SO2排放量为 2.3 t/a，环境影响预测中 SO2排放量为 2.5 t/a",
    extracted_fields: {},
  });
});
