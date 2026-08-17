import { expect, test } from "@rstest/core";
import MarkdownIt from "markdown-it";

import { mathMarkdownIt } from "@/extensions/docmgr/extensions/mathMarkdownIt";

// ponytail: markdown-it 是 tiptap-markdown 的传递依赖，pnpm 下可直接 import
// 如果 import 失败，在 package.json devDependencies 加 "markdown-it": "^14.0.0"

function makeMd() {
  const md = new MarkdownIt({ html: true });
  md.use(mathMarkdownIt);
  return md;
}

test("行内 $...$ → <span data-math-inline>", () => {
  const html = makeMd().render("公式 $E=mc^2$ 测试");
  expect(html).toContain("data-math-inline");
  expect(html).toContain('data-latex="E=mc^2"');
});

test("块级 $$...$$ → <div data-math-block>", () => {
  const html = makeMd().render("$$\\frac{a}{b}$$");
  expect(html).toContain("data-math-block");
  expect(html).toContain('data-latex="\\frac{a}{b}"');
});

test("多行块级 $$...$$", () => {
  const html = makeMd().render("$$\n\\frac{a}{b}\n$$");
  expect(html).toContain("data-math-block");
  expect(html).toContain('data-latex="\\frac{a}{b}"');
});

test("不误伤货币符号 $5", () => {
  const html = makeMd().render("价格 $5 不算");
  expect(html).not.toContain("data-math-inline");
});

test("代码块里的 $ 不被误切", () => {
  const html = makeMd().render("```\n$5 + $3 = $8\n```");
  expect(html).not.toContain("data-math-inline");
});

test("行内代码里的 $ 不被误切", () => {
  const html = makeMd().render("用 `$x$` 表示变量");
  expect(html).not.toContain("data-math-inline");
});

test("latex 内容 HTML 转义", () => {
  const html = makeMd().render("$a < b \\text{且} c > d$");
  expect(html).toContain('data-latex="a &lt; b \\text{且} c &gt; d"');
});

test("中文紧邻 $ 不误判", () => {
  const html = makeMd().render("流量：$Q = Av$ 成立");
  expect(html).toContain("data-math-inline");
});
