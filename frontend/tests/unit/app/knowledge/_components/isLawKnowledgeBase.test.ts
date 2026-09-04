import { describe, expect, it } from "@rstest/core";

import { isLawKnowledgeBase } from "@/app/knowledge/_components/isLawKnowledgeBase";

describe("isLawKnowledgeBase", () => {
  it("matches seeded law KB display names", () => {
    // 两个种子名与 backend config.py → law.dataset_display_info 一致
    expect(isLawKnowledgeBase("法规标准库 — 法律/法规/规章")).toBe(true);
    expect(isLawKnowledgeBase("法规标准库 — 标准/规范")).toBe(true);
    expect(isLawKnowledgeBase("法规标准库收集")).toBe(true);
  });

  it("does not match ordinary KB names", () => {
    expect(isLawKnowledgeBase("我的知识库")).toBe(false);
    expect(isLawKnowledgeBase("合同模板库")).toBe(false);
    expect(isLawKnowledgeBase("")).toBe(false);
  });
});
