import { expect, test, describe } from "vitest";

import {
  buildPrompt,
  parseOperations,
} from "@/extensions/docmgr/DocAIAgentPanel";
import {
  levenshteinDistance,
  findBlockByAnchor,
} from "@/extensions/docmgr/PersonalBlockNoteEditor";

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
  return {
    type,
    id,
    content: [{ type: "text", text, styles: {} }],
    children: [],
    props: {},
  };
}

// ponytail: minimal document fixture matching spec §7 matching levels.
const sampleDoc = [
  block("heading", "h1", "## 设计参数分析"),
  block(
    "paragraph",
    "p1",
    "根据 GB/T 50746-2012 表3.3.3，蒸发损失系数计算公式如下：",
  ),
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

  test("table anchor with pipe chars → normalized match", () => {
    // Simulate a table block with cell-style content
    const tableBlock = {
      type: "table",
      id: "t1",
      content: {
        type: "tableContent",
        rows: [
          {
            cells: [
              { content: [{ type: "text", text: "4", styles: {} }] },
              { content: [{ type: "text", text: "循环水场占地", styles: {} }] },
              { content: [{ type: "text", text: "m²", styles: {} }] },
            ],
          },
        ],
      },
      children: [],
      props: {},
    };
    // Agent anchor from markdown table format
    const result = findBlockByAnchor([tableBlock], "| 4 | 循环水场占地 | m² |");
    expect(result).not.toBeNull();
    expect(result!.blockId).toBe("t1");
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
[{"op":"replace","anchor":"实际参数","content":"## 设计参数分析"}]`;
    const result = parseOperations(input);
    expect(result.analysis).toBe("发现2处问题。");
    expect(result.parseError).toBeNull();
    expect(result.operations).not.toBeNull();
    expect(result.operations!.length).toBe(1);
    expect(result.operations![0]).toEqual({
      op: "replace",
      anchor: "实际参数",
      content: "## 设计参数分析",
    });
  });

  test("malformed JSON → parseError", () => {
    const input = "分析文本。\n\n---OPERATIONS---\n这不是JSON";
    const result = parseOperations(input);
    expect(result.analysis).toBe("分析文本。");
    expect(result.operations).toBeNull();
    expect(result.parseError).toBe("操作指令 JSON 解析失败");
  });

  test("bare object auto-wrapped in array", () => {
    const input =
      '---OPERATIONS---\n{"op":"replace","anchor":"test","content":"## new"}';
    const result = parseOperations(input);
    expect(result.parseError).toBeNull();
    expect(result.operations).not.toBeNull();
    expect(result.operations!.length).toBe(1);
    expect(result.operations![0]!.op).toBe("replace");
  });

  test("single quotes normalized to double quotes", () => {
    const input = "---OPERATIONS---\n[{'op':'delete','anchor':'test'}]";
    const result = parseOperations(input);
    expect(result.parseError).toBeNull();
    expect(result.operations![0]!.op).toBe("delete");
  });

  test("multiple operations", () => {
    const ops = [
      { op: "replace" as const, anchor: "旧标题", content: "## 新标题" },
      { op: "append" as const, content: "## 结论\n\n总结内容。" },
      { op: "delete" as const, anchor: "重复段落" },
    ];
    const input = "分析。\n\n---OPERATIONS---\n" + JSON.stringify(ops);
    const result = parseOperations(input);
    expect(result.parseError).toBeNull();
    expect(result.operations!.length).toBe(3);
    expect(result.operations![0]!.op).toBe("replace");
    expect(result.operations![1]!.op).toBe("append");
    expect(result.operations![2]!.op).toBe("delete");
  });

  test("operations parsed from JSON", () => {
    const ops = [
      { op: "replace" as const, anchor: "标题", content: "## 新" },
      { op: "append" as const, content: "## 加的内容" },
    ];
    const input = "文本。\n\n---OPERATIONS---\n" + JSON.stringify(ops);
    const result = parseOperations(input);
    expect(result.operations!.length).toBe(2);
    expect(result.operations![0]!.op).toBe("replace");
    expect(result.operations![1]!.op).toBe("append");
  });
});

// ─── buildPrompt ───────────────────────────────────────────────────────

describe("buildPrompt", () => {
  function b(mode: "ask" | "auto" | "plan", msg: string) {
    return buildPrompt({
      mode,
      docContent: "# 测试文档\n\n内容。",
      anchors: '[0] H1 "# 测试文档"',
      userMessage: msg,
    });
  }

  test("ask mode — includes document content", () => {
    expect(b("ask", "总结")).toContain("# 测试文档");
  });
  test("includes anchor index", () => {
    expect(b("ask", "操作")).toContain('[0] H1 "# 测试文档"');
  });
  test("includes user message", () => {
    expect(b("ask", "润色")).toContain("润色");
  });
  test("ask mode — includes operation format", () => {
    const p = b("ask", "test");
    expect(p).toContain("---OPERATIONS---");
    expect(p).toContain('"replace"');
  });
  test("ask mode — includes examples", () => {
    const p = b("ask", "test");
    expect(p).toContain("设计参数分析");
    expect(p).toContain("示例1");
  });
  test("plan mode — no operations format", () => {
    const p = b("plan", "分析");
    expect(p).not.toContain("---OPERATIONS---");
    expect(p).toContain("不要输出任何文档编辑操作");
  });
});
