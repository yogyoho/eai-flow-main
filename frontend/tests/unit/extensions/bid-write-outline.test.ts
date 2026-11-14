import { describe, expect, it } from "@rstest/core";

import {
  astSections,
  findSectionPos,
  sectionKey,
} from "@/extensions/bid-write/editor/outline";
import { bidWriteSchema } from "@/extensions/bid-write/editor/schema.gen";

const AST = {
  type: "doc",
  content: [
    { type: "toc_entry", attrs: { title: "目录" } },
    {
      type: "section",
      attrs: { level: 1, title: "一、投标函", section_id: "S-letter" },
      content: [{ type: "para", content: [{ type: "text", text: "正文" }] }],
    },
    {
      type: "section",
      attrs: { level: 1, title: "二、报价表" },
      content: [
        {
          type: "section",
          attrs: { level: 2, title: "2.1 分项报价" },
          content: [
            { type: "para", content: [{ type: "text", text: "子节" }] },
          ],
        },
      ],
    },
  ],
};

describe("bid-write 正文目录", () => {
  it("从 AST 提取 section,缺省 section_id 用正文顺序键", () => {
    const sections = astSections(AST);
    expect(sections.map((item) => item.title)).toEqual([
      "一、投标函",
      "二、报价表",
      "2.1 分项报价",
    ]);
    expect(sections[0]?.key).toBe("id:S-letter");
    expect(sections[1]?.key).toBe("index:1");
    expect(sections[2]?.level).toBe(2);
  });

  it("PM doc 中的定位键与 AST 目录一致", () => {
    const doc = bidWriteSchema.nodeFromJSON(AST);
    const sections = astSections(AST);
    for (const section of sections) {
      expect(findSectionPos(doc, section.key)).not.toBeNull();
    }
    expect(findSectionPos(doc, "missing")).toBeNull();
  });

  it("空 section_id 回退为顺序键,不伪造标题", () => {
    expect(sectionKey({ section_id: "  " }, 4)).toBe("index:4");
  });
});
