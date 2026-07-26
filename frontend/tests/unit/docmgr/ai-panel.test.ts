import { expect, test, describe } from "vitest";

import { levenshteinDistance, findBlockByAnchor } from "@/extensions/docmgr/PersonalBlockNoteEditor";
import { buildPrompt, parseOperations } from "@/extensions/docmgr/DocAIAgentPanel";

// ─── levenshteinDistance ──────────────────────────────────────────────

describe("levenshteinDistance", () => {
  test("identical strings → 0", () => {
    expect(levenshteinDistance("hello", "hello")).toBe(0);
  });

  test("empty vs non-empty", () => {
    expect(levenshteinDistance("", "abc")).toBe(3);
    expect(levenshteinDistance("abc", "")).toBe(3);
  });

  test("both empty → 0", () => {
    expect(levenshteinDistance("", "")).toBe(0);
  });

  test("single substitution", () => {
    expect(levenshteinDistance("kitten", "sitten")).toBe(1);
  });

  test("multiple edits", () => {
    // kitten → sitting = 3 (k→s, e→i, +g)
    expect(levenshteinDistance("kitten", "sitting")).toBe(3);
  });

  test("CJK characters", () => {
    expect(levenshteinDistance("设计参数", "设计参数分析")).toBe(2);
    expect(levenshteinDistance("设计参数", "实际参数")).toBe(2); // 设→实 + 计→际
  });

  test("long text — still computes correctly", () => {
    const a = "根据 GB/T 50746-2012 表3.3.3";
    const b = "根据 GB/T 50746-2012 表3.3.3，蒸发损失系数";
    const dist = levenshteinDistance(a, b);
    // b is a + suffix, so distance = suffix length
    expect(dist).toBe(b.length - a.length);
  });
});

// ─── findBlockByAnchor ────────────────────────────────────────────────

/** Helper: create a mock BlockNote block. */
function block(type: string, id: string, text: string) {
  return { type, id, content: [{ type: "text", text, styles: {} }], children: [], props: {} };
}

// ponytail: minimal document fixture matching spec §7 matching levels.
const sampleDoc = [
  block("heading", "h1", "## 设计参数分析"),
  block("paragraph", "p1", "根据 GB/T 50746-2012 表3.3.3，蒸发损失系数计算公式如下："),
  block("heading", "h2", "### 计算公式"),
  block("paragraph", "p2", "$$K_{ZF} = 0.001461$$"),
  block("paragraph", "p3", "其中 K_{ZF} 为蒸发损失系数。"),
  block("bulletListItem", "li1", "参数列表项目"),
];

describe("findBlockByAnchor", () => {
  test("exact match (level 1)", () => {
    const result = findBlockByAnchor(sampleDoc, "## 设计参数分析");
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("h1");
    expect(result!.blockIndex).toBe(0);
  });

  test("prefix match (level 2)", () => {
    const result = findBlockByAnchor(sampleDoc, "根据 GB/T 50746-2012");
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("p1");
    expect(result!.blockIndex).toBe(1);
  });

  test("contains match — unique (level 3)", () => {
    const result = findBlockByAnchor(sampleDoc, "蒸发损失系数计算公式");
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("p1");
  });

  test("contains match — ambiguous returns null", () => {
    // "K_{ZF}" appears in both p2 and p3
    const result = findBlockByAnchor(sampleDoc, "K_{ZF}");
    expect(result).toBeNull();
  });

  test("fuzzy match (level 4)", () => {
    const result = findBlockByAnchor(sampleDoc, "设计参数分折"); // typo: 折 instead of 析
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("h1");
  });

  test("no match → null (level 5)", () => {
    const result = findBlockByAnchor(sampleDoc, "完全不存在的文本XYZ");
    expect(result).toBeNull();
  });

  test("empty anchor → null", () => {
    expect(findBlockByAnchor(sampleDoc, "")).toBeNull();
    expect(findBlockByAnchor(sampleDoc, "   ")).toBeNull();
  });

  test("anchor too short for fuzzy → null", () => {
    // < 5 chars, no exact/prefix/contains match
    const result = findBlockByAnchor(sampleDoc, "XYZ");
    expect(result).toBeNull();
  });

  test("finds in bulletListItem (non-paragraph block)", () => {
    const result = findBlockByAnchor(sampleDoc, "参数列表项目");
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("li1");
  });

  test("empty document → null", () => {
    expect(findBlockByAnchor([], "anything")).toBeNull();
  });
});

// ─── parseOperations ──────────────────────────────────────────────────

describe("parseOperations", () => {
  test("no operations delimiter → analysis only", () => {
    const input = "文档分析完成，没有发现问题。";
    const result = parseOperations(input);
    expect(result.analysis).toBe(input);
    expect(result.operations).toBeNull();
    expect(result.parseError).toBeNull();
  });

  test("empty operations block → empty array", () => {
    const input = "这里是分析文本。\n\n---OPERATIONS---\n";
    const result = parseOperations(input);
    expect(result.analysis).toBe("这里是分析文本。");
    expect(result.operations).toEqual([]);
    expect(result.parseError).toBeNull();
  });

  test("valid operations → parsed correctly", () => {
    const input = `发现2处问题。

---OPERATIONS---
[{"op":"replace","anchor":"实际参数","content":"## 设计参数分析","autoApply":false}]`;
    const result = parseOperations(input);
    expect(result.analysis).toBe("发现2处问题。");
    expect(result.parseError).toBeNull();
    expect(result.operations).not.toBeNull();
    expect(result.operations!.length).toBe(1);
    expect(result.operations![0]).toEqual({
      op: "replace",
      anchor: "实际参数",
      content: "## 设计参数分析",
      autoApply: false,
    });
  });

  test("malformed JSON → parseError", () => {
    const input = "分析文本。\n\n---OPERATIONS---\n这不是JSON";
    const result = parseOperations(input);
    expect(result.analysis).toBe("分析文本。");
    expect(result.operations).toBeNull();
    expect(result.parseError).toBe("操作指令 JSON 解析失败");
  });

  test("non-array JSON → parseError", () => {
    const input = '---OPERATIONS---\n{"op":"replace"}';
    const result = parseOperations(input);
    expect(result.analysis).toBe("");
    expect(result.operations).toBeNull();
    expect(result.parseError).toBe("操作指令不是数组格式");
  });

  test("multiple operations", () => {
    const ops = [
      { op: "replace", anchor: "旧标题", content: "## 新标题", autoApply: false },
      { op: "append", content: "## 结论\n\n总结内容。", autoApply: false },
      { op: "delete", anchor: "重复段落", autoApply: true },
    ];
    const input = "分析。\n\n---OPERATIONS---\n" + JSON.stringify(ops);
    const result = parseOperations(input);
    expect(result.parseError).toBeNull();
    expect(result.operations!.length).toBe(3);
    expect(result.operations![0].op).toBe("replace");
    expect(result.operations![1].op).toBe("append");
    expect(result.operations![2].op).toBe("delete");
  });

  test("autoApply and manual operations mixed", () => {
    const ops = [
      { op: "replace" as const, anchor: "标题", content: "## 新", autoApply: false },
      { op: "replace" as const, anchor: "## 新", content: "## 新\n\n加空格", autoApply: true },
    ];
    const input = "文本。\n\n---OPERATIONS---\n" + JSON.stringify(ops);
    const result = parseOperations(input);
    expect(result.operations![0].autoApply).toBe(false);
    expect(result.operations![1].autoApply).toBe(true);
  });
});

// ─── buildPrompt ───────────────────────────────────────────────────────

describe("buildPrompt", () => {
  test("includes document content", () => {
    const prompt = buildPrompt({
      docContent: "# 测试文档\n\n内容。",
      anchors: '[0] H1 "# 测试文档"\n[1] P "内容。"',
      userMessage: "总结",
    });
    expect(prompt).toContain("# 测试文档");
    expect(prompt).toContain("内容。");
  });

  test("includes anchor index", () => {
    const prompt = buildPrompt({
      docContent: "doc",
      anchors: '[0] H1 "# 标题"\n[1] P "段落文本"',
      userMessage: "操作",
    });
    expect(prompt).toContain('[0] H1 "# 标题"');
    expect(prompt).toContain('[1] P "段落文本"');
  });

  test("includes user message", () => {
    const prompt = buildPrompt({
      docContent: "doc",
      anchors: "",
      userMessage: "请帮我润色这段文字",
    });
    expect(prompt).toContain("请帮我润色这段文字");
  });

  test("includes operation format instructions", () => {
    const prompt = buildPrompt({
      docContent: "doc",
      anchors: "",
      userMessage: "test",
    });
    expect(prompt).toContain("---OPERATIONS---");
    expect(prompt).toContain("replace");
    expect(prompt).toContain("insert_after");
    expect(prompt).toContain("delete");
    expect(prompt).toContain("prepend");
    expect(prompt).toContain("append");
    expect(prompt).toContain("autoApply");
  });

  test("includes few-shot examples", () => {
    const prompt = buildPrompt({
      docContent: "doc",
      anchors: "",
      userMessage: "test",
    });
    // New prompt has 3 examples with concrete operations
    expect(prompt).toContain("设计参数分析");
    expect(prompt).toContain("GB/T 50746-2012");
    expect(prompt).toContain("示例1");
    expect(prompt).toContain("示例2");
    expect(prompt).toContain("示例3");
  });
});
