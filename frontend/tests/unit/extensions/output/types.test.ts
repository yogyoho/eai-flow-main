import { expect, test, describe } from "vitest";

import { WATERMARK_LABELS } from "@/extensions/output/types";

describe("Output type labels", () => {
  test("WATERMARK_LABELS has all watermark types", () => {
    expect(WATERMARK_LABELS).toEqual({
      draft: "初稿",
      review: "送审稿",
      final: "正式稿",
    });
  });

  test("watermark labels are all Chinese", () => {
    for (const label of Object.values(WATERMARK_LABELS)) {
      expect(label).toMatch(/[一-鿿]/);
    }
  });
});