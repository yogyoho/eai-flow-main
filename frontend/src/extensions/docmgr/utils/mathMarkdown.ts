// ponytail: 边界预处理/后处理 —— markdown 数学语法 ($...$ / $$...$$) ⇄ HTML 占位标签。
// 让 tiptap-markdown(html:true 已开)携带公式节点往返,不依赖其 token 映射(文档少、v3 不稳)。
// 已知 ceiling: 行内 $...$ 正则是启发式(首尾紧邻非空格),极端嵌套可能误判 —— 靠单测覆盖常见用例。

const ESC: Array<[RegExp, string]> = [
  [/&/g, "&amp;"],
  [/"/g, "&quot;"],
  [/</g, "&lt;"],
];
const UNESC: Array<[RegExp, string]> = [
  [/&lt;/g, "<"],
  [/&quot;/g, '"'],
  [/&amp;/g, "&"],
];

function escapeAttr(s: string): string {
  let r = s;
  for (const [re, rep] of ESC) r = r.replace(re, rep);
  return r;
}

function unescapeAttr(s: string): string {
  let r = s;
  for (const [re, rep] of UNESC) r = r.replace(re, rep);
  return r;
}

export function encodeMath(md: string): string {
  // 先块级 $$...$$(可跨行),再行内 $...$(不跨行;首尾须紧邻非空格,避开货币与 $$ 残留)
  return md
    .replace(
      /\$\$([\s\S]+?)\$\$/g,
      (_m, latex: string) =>
        `<div data-math-block data-latex="${escapeAttr(latex)}"></div>`,
    )
    .replace(
      /(^|[^$\n\\])\$([^\s$][^\n$]*?[^\s$]|[^\s$])\$(?=$|[^$\n])/g,
      (_m, pre: string, latex: string) =>
        `${pre}<span data-math-inline data-latex="${escapeAttr(latex)}"></span>`,
    );
}

export function decodeMath(md: string): string {
  // 容忍 data-math-x 与 data-math-x="" 、属性两种顺序(正序 + 反序各一轮)
  const block = (l: string) => `$$${unescapeAttr(l)}$$`;
  const inline = (l: string) => `$${unescapeAttr(l)}$`;
  return md
    .replace(
      /<div\b[^>]*\bdata-math-block\b(?:="")?[^>]*\bdata-latex="([^"]*)"[^>]*><\/div>/g,
      (_m, l: string) => block(l),
    )
    .replace(
      /<div\b[^>]*\bdata-latex="([^"]*)"[^>]*\bdata-math-block\b(?:="")?[^>]*><\/div>/g,
      (_m, l: string) => block(l),
    )
    .replace(
      /<span\b[^>]*\bdata-math-inline\b(?:="")?[^>]*\bdata-latex="([^"]*)"[^>]*><\/span>/g,
      (_m, l: string) => inline(l),
    )
    .replace(
      /<span\b[^>]*\bdata-latex="([^"]*)"[^>]*\bdata-math-inline\b(?:="")?[^>]*><\/span>/g,
      (_m, l: string) => inline(l),
    );
}
