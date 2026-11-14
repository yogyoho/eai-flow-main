import { describe, expect, it } from "@rstest/core";

import {
  AST_ENUM_VALUES,
  AST_MARK_TYPES,
  AST_NODE_COUNT,
  AST_NODE_TYPES,
  AST_SCHEMA_VERSION,
  bidWriteSchema,
} from "@/extensions/bid-write/editor/schema.gen";

describe("bid-write editor schema.gen", () => {
  it("15 项口径:13 节点 + 2 mark", () => {
    expect(AST_NODE_COUNT).toBe(15);
    expect(AST_NODE_TYPES).toHaveLength(13);
    expect(AST_MARK_TYPES).toHaveLength(2);
    expect(Object.keys(bidWriteSchema.nodes)).toHaveLength(13);
    expect(Object.keys(bidWriteSchema.marks)).toHaveLength(2);
  });

  it("关键节点在位且 attrs 默认正确", () => {
    expect(AST_NODE_TYPES).toContain("locked_paragraph");
    expect(AST_NODE_TYPES).toContain("amount_cell");
    // PM typings 新版只在 spec 上暴露 attrs(NodeType.attrs 运行时存在但 d.ts 未列)
    const amount = bidWriteSchema.nodes.amount_cell;
    expect(amount.spec.attrs?.readonly?.default).toBe(true);
    expect(
      bidWriteSchema.nodes.locked_paragraph.spec.attrs?.similarity_floor
        ?.default,
    ).toBe(0.98);
    expect(bidWriteSchema.nodes.section.spec.attrs?.level?.default).toBe(1);
  });

  it("toDOM 类名按 yaml 落位", () => {
    const doc = bidWriteSchema.nodeFromJSON({
      type: "doc",
      content: [
        {
          type: "section",
          attrs: { level: 1, title: "一、投标函", section_id: "S1" },
          content: [{ type: "para", content: [{ type: "text", text: "正文" }] }],
        },
      ],
    });
    const section = doc.firstChild;
    const dom = section?.type.spec.toDOM?.(section);
    expect(JSON.stringify(dom)).toContain("bwe-section");
    expect(JSON.stringify(dom)).toContain("data-title");
  });

  it("AST_ENUM_VALUES 收敛 yaml enum 候选", () => {
    expect(AST_ENUM_VALUES.table_type).toContain("price");
    expect(AST_ENUM_VALUES.role).toContain("amount");
  });

  it("版本常量随 yaml", () => {
    expect(AST_SCHEMA_VERSION).toBe("0.1.0");
  });
});
