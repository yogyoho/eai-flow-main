import { describe, expect, test } from "@rstest/core";

import { diffLines } from "@/extensions/docmgr/sectionDiff";

describe("diffLines（行级 LCS diff, 全文操作 v2）", () => {
  test("完全相同 → 全 ctx", () => {
    expect(diffLines("a\nb\nc", "a\nb\nc")).toEqual([
      { type: "ctx", text: "a" },
      { type: "ctx", text: "b" },
      { type: "ctx", text: "c" },
    ]);
  });

  test("整行替换 → del+ins", () => {
    expect(diffLines("a\nold\nc", "a\nnew\nc")).toEqual([
      { type: "ctx", text: "a" },
      { type: "del", text: "old" },
      { type: "ins", text: "new" },
      { type: "ctx", text: "c" },
    ]);
  });

  test("中间插入 → ctx ins ctx", () => {
    expect(diffLines("a\nc", "a\nb\nc")).toEqual([
      { type: "ctx", text: "a" },
      { type: "ins", text: "b" },
      { type: "ctx", text: "c" },
    ]);
  });

  test("中间删除 → ctx del ctx", () => {
    expect(diffLines("a\nb\nc", "a\nc")).toEqual([
      { type: "ctx", text: "a" },
      { type: "del", text: "b" },
      { type: "ctx", text: "c" },
    ]);
  });

  test("空旧文本 → 全 ins（空串按 0 行计,不产 del 空行）", () => {
    expect(diffLines("", "a\nb")).toEqual([
      { type: "ins", text: "a" },
      { type: "ins", text: "b" },
    ]);
  });

  test("双空 → 空输出", () => {
    expect(diffLines("", "")).toEqual([]);
  });

  test(">500 行护栏：跳过 LCS，退化为整段 del+ins（不崩、形状正确）", () => {
    const old = Array.from({ length: 501 }, (_, i) => `old${i}`).join("\n");
    const next = Array.from({ length: 20 }, (_, i) => `new${i}`).join("\n");
    const lines = diffLines(old, next);
    expect(lines).toHaveLength(521);
    expect(lines.every((l) => l.type !== "ctx")).toBe(true);
    expect(lines[0]).toEqual({ type: "del", text: "old0" });
    expect(lines[500]).toEqual({ type: "del", text: "old500" });
    expect(lines[501]).toEqual({ type: "ins", text: "new0" });
    expect(lines[520]).toEqual({ type: "ins", text: "new19" });
  });

  test("护栏不误伤：恰 500 行走 LCS（相同文本仍全 ctx）", () => {
    const text = Array.from({ length: 500 }, (_, i) => `l${i}`).join("\n");
    const lines = diffLines(text, text);
    expect(lines).toHaveLength(500);
    expect(lines.every((l) => l.type === "ctx")).toBe(true);
  });
});
