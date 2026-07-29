import { describe, expect, it } from "rstest";

import { BRAND_FOOTER, BRAND_NAME } from "@/brand";

describe("brand", () => {
  // 测试环境不注入 NEXT_PUBLIC_BRAND_NAME → 回落默认 "EAIFlow"
  it("BRAND_NAME 回落默认 EAIFlow（env 未注入时）", () => {
    expect(BRAND_NAME).toBe("EAIFlow");
  });

  it("BRAND_FOOTER 是字符串（允许空）", () => {
    expect(typeof BRAND_FOOTER).toBe("string");
  });
});
