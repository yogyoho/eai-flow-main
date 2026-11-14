import { describe, expect, it } from "@rstest/core";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import {
  docPlainText,
  hydrateAst,
  serializeDoc,
} from "@/extensions/bid-write/editor/doc";
import { type AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

/**
 * 规范化 JSON:键排序后逐字节比较。
 * PM TextNode.toJSON 键序为 {type, marks, text}(marks 先于 text),与手写
 * fixture 的 {type, text, marks} 键序不同;内容全等,故按方案 §十二「往返一致」
 * 口径取规范化字节比较。
 */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(
      ([a], [b]) => a.localeCompare(b),
    );
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

describe("AST ↔ PMdoc 往返", () => {
  it("演示文档 hydrate→serialize 规范化字节一致(方案 §十二 Schema 往返口径)", () => {
    const ast = demoWorkbenchAst();
    const doc = hydrateAst(ast);
    const back = serializeDoc(doc);
    expect(canonical(back)).toBe(canonical(ast));
  });

  it("往返幂等:二次往返不再变化", () => {
    const once = serializeDoc(hydrateAst(demoWorkbenchAst()));
    const twice = serializeDoc(hydrateAst(once));
    expect(canonical(twice)).toBe(canonical(once));
  });

  it("未知节点类型被 schema 拒绝", () => {
    const bad = { type: "bogus_node" } as unknown as AstJsonNode;
    expect(() => hydrateAst(bad)).toThrow();
  });

  it("文本投影剥离 marks(provenance/status 不进文本)", () => {
    const doc = hydrateAst(demoWorkbenchAst());
    const text = docPlainText(doc);
    expect(text).toContain("1,280,000.00");
    expect(text).not.toContain("B-014");
    expect(text).not.toContain("SK-PS-003");
  });
});
