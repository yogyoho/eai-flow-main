import { describe, expect, test } from "@rstest/core";

import { findSectionRange } from "@/extensions/docmgr/PersonalBlockNoteEditor";

const h = (id: string, text: string, level: number) => ({
  id,
  type: "heading",
  props: { level },
  content: [{ type: "text", text }],
});
const p = (id: string, text: string) => ({
  id,
  type: "paragraph",
  content: [{ type: "text", text }],
});

describe("findSectionRange（replace_section 节边界）", () => {
  const doc = [
    h("a", "一", 1),
    p("a1", "甲"),
    h("b", "二", 2),
    p("b1", "乙"),
    p("b2", "丙"),
    h("c", "三", 2),
    p("c1", "丁"),
    h("d", "四", 1),
    p("d1", "戊"),
  ];

  test("同级标题截断", () => {
    expect(findSectionRange(doc, 2)).toEqual({
      blockIds: ["b", "b1", "b2"],
      startIndex: 2,
      endIndex: 4,
    });
  });

  test("低级标题不截断高级节", () => {
    // 「一」(level 1) 的节吃到 level 2 的「二」之前
    expect(findSectionRange(doc, 0)).toEqual({
      blockIds: ["a", "a1"],
      startIndex: 0,
      endIndex: 1,
    });
  });

  test("文末无边界 → 扫到底", () => {
    expect(findSectionRange(doc, 7)?.blockIds).toEqual(["d", "d1"]);
  });

  test("锚点非标题 → null", () => {
    expect(findSectionRange(doc, 1)).toBeNull();
    expect(findSectionRange(doc, 99)).toBeNull();
  });
});
