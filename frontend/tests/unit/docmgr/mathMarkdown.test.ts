import { expect, test } from "vitest";

import { decodeMath, encodeMath, sanitizeMarkdownForEditor } from "@/extensions/docmgr/utils/mathMarkdown";

test("encodeMath: inline $...$ → span 占位", () => {
  expect(encodeMath("$E=mc^2$")).toBe(
    '<span data-math-inline data-latex="E=mc^2"></span>',
  );
});

test("encodeMath: block $$...$$ → div 占位", () => {
  expect(encodeMath("$$\\frac{a}{b}$$")).toBe(
    '<div data-math-block data-latex="\\frac{a}{b}"></div>',
  );
});

test("encodeMath: 不误伤货币符号", () => {
  expect(encodeMath("价格 $5 不算")).toBe("价格 $5 不算");
  expect(encodeMath("$10 和 $20")).toBe("$10 和 $20");
});

test("encodeMath: 段中行内公式保留前缀", () => {
  expect(encodeMath("a $x$ b")).toBe(
    'a <span data-math-inline data-latex="x"></span> b',
  );
});

test("decodeMath: 容忍属性重排与空值", () => {
  expect(decodeMath('<span data-math-inline data-latex="x"></span>')).toBe("$x$");
  expect(decodeMath('<span data-math-inline="" data-latex="x"></span>')).toBe("$x$");
  expect(decodeMath('<span data-latex="x" data-math-inline=""></span>')).toBe("$x$");
  expect(decodeMath('<div data-math-block data-latex="\\frac{a}{b}"></div>')).toBe(
    "$$\\frac{a}{b}$$",
  );
});

test("往返一致 decode(encode(x)) === x", () => {
  const samples = [
    "$E=mc^2$",
    "$$\\frac{a}{b}$$",
    "a $x$ b",
    "$a_1$ 然后 $b^2$",
    "$a & b$",
  ];
  for (const s of samples) {
    expect(decodeMath(encodeMath(s))).toBe(s);
  }
});

test("sanitizeMarkdownForEditor: 公式块后紧跟加粗/标题 → 补空行(HTML 块后 markdown 才能解析)", () => {
  // $$...$$ 后紧跟 **加粗**（无换行）→ 补空行
  expect(sanitizeMarkdownForEditor("$$a^2$$**气水比计算：**")).toBe("$$a^2$$\n\n**气水比计算：**");
  // 已有单换行也补成空行（单换行不足以让 HTML 块后 markdown 解析）
  expect(sanitizeMarkdownForEditor("$$a^2$$\n**气水比计算：**")).toBe("$$a^2$$\n\n**气水比计算：**");
  // 紧跟标题同理
  expect(sanitizeMarkdownForEditor("$$a^2$$### 标题")).toBe("$$a^2$$\n\n### 标题");
});

test("sanitizeMarkdownForEditor: 还原被错存的转义加粗 \\*\\* → **", () => {
  // AI/历史处理把加粗 ** 错存成 \*\*，加载时还原（部分转义也要修）
  expect(sanitizeMarkdownForEditor("*\\*数值代入（冬季工况）：\\*\\*")).toBe(
    "**数值代入（冬季工况）：**",
  );
  expect(sanitizeMarkdownForEditor("> \\*\\*结果：\\*\\* 水量 \\*\\*96.4 m³/h\\*\\*")).toBe(
    "> **结果：** 水量 **96.4 m³/h**",
  );
  // 2+ 反斜杠的旧损坏仍兼容
  expect(sanitizeMarkdownForEditor("\\\\*\\\\*粗体\\\\*\\\\*")).toBe("**粗体**");
});
