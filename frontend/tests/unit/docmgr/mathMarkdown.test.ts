import { expect, test } from "vitest";

import { decodeMath, encodeMath } from "@/extensions/docmgr/utils/mathMarkdown";

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
