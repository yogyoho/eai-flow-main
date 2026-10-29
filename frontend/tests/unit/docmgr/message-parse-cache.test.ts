import { describe, expect, test } from "@rstest/core";

import { createAIMessageParser } from "@/extensions/docmgr/DocAIAgentPanel";

describe("createAIMessageParser（bug-3301：解析结果按消息身份缓存）", () => {
  test("同 id 同内容 → 同一对象引用（重渲染不产新 ops 数组）", () => {
    const parse = createAIMessageParser();
    const content = '说明\n\n---OPERATIONS---\n[{"op":"append","content":"x"}]';
    const a = parse("m1", content);
    const b = parse("m1", content);
    expect(b).toBe(a);
    expect(b.ops).toHaveLength(1);
  });

  test("同 id 内容变化 → 重新解析（流式中内容增长）", () => {
    const parse = createAIMessageParser();
    const a = parse("m1", "前半");
    const b = parse("m1", "前半\n\n---OPERATIONS---\n[]");
    expect(b).not.toBe(a);
  });

  test("不同 id 各自缓存", () => {
    const parse = createAIMessageParser();
    const a = parse("m1", "AAA");
    const b = parse("m2", "AAA");
    expect(b).not.toBe(a);
    expect(parse("m1", "AAA")).toBe(a);
  });

  test("数组型 content 归一为文本再解析", () => {
    const parse = createAIMessageParser();
    const r = parse("m3", [
      {
        type: "text",
        text: '---OPERATIONS---\n[{"op":"append","content":"y"}]',
      },
    ]);
    expect(r.ops).toHaveLength(1);
  });
});
