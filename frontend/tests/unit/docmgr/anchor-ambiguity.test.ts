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
