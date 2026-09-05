import { expect, test } from "@rstest/core";

import { normalizeLatexForKatex } from "@/core/streamdown/latexNormalize";

// ── Bug 回归: bug-2222 docmgr 导入吃掉 \_ → KaTeX text-mode 裸 _ 报错 ──
// 渲染层兜底:\text{} 内裸 _ 补 \_;数学模式 Q_w 不动。
test("normalizeLatexForKatex: \\text{} 内裸 _ 补 \\_(治存量坏 latex)", () => {
  expect(
    normalizeLatexForKatex("Q_w = Q \\times \\text{drift_rate}"),
  ).toBe("Q_w = Q \\times \\text{drift\\_rate}");
});

test("normalizeLatexForKatex: 已转义 \\_ 不重复补", () => {
  const input = "Q_w = Q \\times \\text{drift\\_rate}";
  expect(normalizeLatexForKatex(input)).toBe(input);
});

test("normalizeLatexForKatex: 连续 __ 逐个补、开头 _ 也补", () => {
  expect(normalizeLatexForKatex("\\text{a__b}")).toBe("\\text{a\\_\\_b}");
  expect(normalizeLatexForKatex("\\text{_start}")).toBe("\\text{\\_start}");
});

test("normalizeLatexForKatex: 数学下标/命令不受影响", () => {
  const input = "Q_e = Q \\times K_{ZF} \\times \\Delta t";
  expect(normalizeLatexForKatex(input)).toBe(input);
});

// ── 既有行为回归(改动前就有的归一逻辑) ─────────────────────────────────
test("normalizeLatexForKatex: \\text{} 尾部 ℃/上标搬移仍生效", () => {
  expect(normalizeLatexForKatex("\\text{25℃}")).toBe("\\text{25}^{\\circ}C");
  expect(normalizeLatexForKatex("\\text{面积m²}")).toBe(
    "\\text{面积m}^{2}",
  );
});

test("normalizeLatexForKatex: 双写命令折叠后走 \\text{} 补转义(组合)", () => {
  expect(normalizeLatexForKatex("\\\\text{drift_rate}")).toBe(
    "\\text{drift\\_rate}",
  );
});
