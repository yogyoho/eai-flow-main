export interface RuleTestPayload {
  reportData?: Record<string, unknown>;
  rawText?: string;
  extractedFields?: Record<string, unknown>;
}

export interface RuleTestRequestBody {
  report_data?: Record<string, unknown>;
  raw_text?: string;
  extracted_fields: Record<string, unknown>;
}

export function parseRuleTestInput(input: string): RuleTestPayload {
  const trimmedInput = input.trim();

  if (!trimmedInput) {
    return { extractedFields: {} };
  }

  try {
    return {
      reportData: JSON.parse(trimmedInput) as Record<string, unknown>,
      extractedFields: {},
    };
  } catch {
    return {
      rawText: trimmedInput,
      extractedFields: {},
    };
  }
}

export function buildRuleTestRequestBody(
  testData: RuleTestPayload
): RuleTestRequestBody {
  const body: RuleTestRequestBody = {
    extracted_fields: testData.extractedFields ?? {},
  };

  if (testData.reportData && Object.keys(testData.reportData).length > 0) {
    body.report_data = testData.reportData;
  }

  if (testData.rawText?.trim()) {
    body.raw_text = testData.rawText.trim();
  }

  return body;
}
