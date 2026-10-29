import { describe, expect, test } from "@rstest/core";

import { findBlockByAnchor } from "@/extensions/docmgr/PersonalBlockNoteEditor";

const heading = (id: string, text: string, level = 2) => ({
  id,
  type: "heading",
  props: { level },
  content: [{ type: "text", text }],
});
const para = (id: string, text: string) => ({
  id,
  type: "paragraph",
  content: [{ type: "text", text }],
});

describe("findBlockByAnchor 歧义加固（重复标题静默错配→安全失败）", () => {
  const doc = [
    heading("h1", "概述", 1),
    para("p1", "正文一"),
    heading("h2", "概述", 2),
    para("p2", "正文二"),
  ];

  test("exact 重复标题 → null", () => {
    expect(findBlockByAnchor(doc, "概述")).toBeNull();
  });

  test("prefix 重复前缀 → null", () => {
    expect(findBlockByAnchor(doc, "概")).toBeNull();
  });

  test("唯一标题正常命中", () => {
    const doc2 = [heading("h1", "概述", 1), para("p1", "正文")];
    expect(findBlockByAnchor(doc2, "概述")?.blockId).toBe("h1");
  });

  test("不同标题各自唯一仍命中", () => {
    expect(findBlockByAnchor(doc, "正文一")?.blockId).toBe("p1");
  });
});

describe("findBlockByAnchor heading 优先裁决（TOC 列表项撞标题, 终审 I-1a）", () => {
  const listItem = (id: string, text: string) => ({
    id,
    type: "bulletListItem",
    content: [{ type: "text", text }],
  });

  test("exact 歧义中恰一 heading → heading 胜出（listItem 撞标题）", () => {
    const doc2 = [
      listItem("li1", "施工组织设计"),
      heading("h1", "施工组织设计", 2),
    ];
    expect(findBlockByAnchor(doc2, "施工组织设计")?.blockId).toBe("h1");
  });

  test("exact 歧义中恰一 heading → heading 胜出（paragraph 撞标题）", () => {
    const doc3 = [heading("h1", "概述", 2), para("p1", "概述")];
    expect(findBlockByAnchor(doc3, "概述")?.blockId).toBe("h1");
  });

  test("prefix 歧义中恰一 heading → heading 胜出", () => {
    const doc4 = [para("p1", "概述正文补遗"), heading("h2", "概述", 2)];
    expect(findBlockByAnchor(doc4, "概")?.blockId).toBe("h2");
  });

  test("多 heading 歧义仍 null（不放宽重复标题纪律）", () => {
    const doc5 = [
      heading("h1", "概述", 1),
      listItem("li1", "概述"),
      heading("h2", "概述", 2),
    ];
    expect(findBlockByAnchor(doc5, "概述")).toBeNull();
  });
});
