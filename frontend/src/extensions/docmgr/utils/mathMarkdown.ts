// ponytail: 边界预处理/后处理 —— markdown 数学语法 ($...$ / $$...$$) ⇄ HTML 占位标签。
// 让 tiptap-markdown(html:true 已开)携带公式节点往返,不依赖其 token 映射(文档少、v3 不稳)。
// 已知 ceiling: 行内 $...$ 正则是启发式(首尾紧邻非空格),极端嵌套可能误判 —— 靠单测覆盖常见用例。

/**
 * 修复编辑器保存往返(getMarkdown→decodeMath)对 markdown 的累积损坏:
 *  - $$...$$ 块公式后换行丢失,与紧跟的标题/正文挤到一行 ($$...$$### / $$...$$\\### / $$...$$文字)
 *  - 数学里的 \frac 等命令被双反斜杠化 ($\\frac → $\frac)
 *  - **粗体** 被过度转义累积成 \\\*\\\*
 *  - ~ 被转义成 \~
 * 加载时(encodeMath 前)跑一遍即可自愈已损坏的文件;保守,只清明确的过度转义。
 */
export function sanitizeMarkdownForEditor(md: string): string {
  if (!md) return md;
  let s = md;
  // 0) 全局 HTML 实体转义修复: &gt; → >(编辑器保存往返会把 > 转成 &gt;)
  s = s.replace(/&gt;/g, ">");
  // 1) 数学内的双(多)反斜杠命令归一: $...$ / $$...$$ 里 \\frac → \frac
  //    (函数返回值是字面的,直接拼 $$ ;body 内层用字符串替换 "\\$1"→\X)
  const deDouble = (body: string) => body.replace(/\\{2,}([a-zA-Z])/g, "\\$1");
  s = s.replace(
    /\$\$([\s\S]+?)\$\$/g,
    (_m, body: string) => "$$" + deDouble(body) + "$$",
  );
  s = s.replace(
    /\$([^\$\n]+?)\$/g,
    (_m, body: string) => "$" + deDouble(body) + "$",
  );
  // 2) $$...$$ 块公式后紧跟内容(标题/加粗/文字)→ 在块后补空行(\n\n)
  //    关键: encodeMath 把 $$...$$ 转成 <div>(HTML 块),Markdown 规范要求 HTML 块后必须有空行
  //    才能解析后续 markdown(否则 **加粗** / ### 标题 会被当 HTML 块延续,字面显示)。
  //    只动闭合 $$ 的尾部;不碰开 $$,避免破坏单行 $$body$$。不消耗反斜杠(交给 step 3)。
  s = s.replace(/(\$\$[\s\S]+?\$\$)\n?(?=[^\n\r])/g, "$1\n\n");
  // 3) 过度转义的粗体/标题星号与井号: 反斜杠后跟 * 还原成 *（修复 AI/历史处理把加粗 ** 错存成 \*\* 导致渲染成字面星号）；2+ 反斜杠后跟 # 还原成 #
  s = s.replace(/\\+\*/g, "*");
  s = s.replace(/\\{2,}#/g, "#");
  // 4) \~ → ~(singleTilde:false 下 ~ 不特殊,无需转义)
  s = s.replace(/\\~/g, "~");
  // 5) 表格对齐标记双冒号修复: |::---:| → |:---:| / |::---| → |:---|
  s = s.replace(/\|:{2,}/g, "|:").replace(/:{2,}\|/g, ":|");
  // 6) 过度转义的引用标记: \\{2,}> 空间 → > 空间
  s = s.replace(/\\{2,}> /g, "> ");
  // 7) $$ 块内卷入了非数学文本(以 &gt; 或 > 开头的引用/粗体→被 AI 或编辑器错包进数学块) → 拆回 markdown
  //    7a) 有闭 $$ 的正常块
  s = s.replace(
    /\$\$&gt;([\s\S]*?)\$\$/g,
    (_m: string, content: string) =>
      "\n> " + content.replace(/\\\*/g, "*") + "\n",
  );
  s = s.replace(
    /\$\$>([\s\S]*?)\$\$/g,
    (_m: string, content: string) =>
      "\n> " + content.replace(/\\\*/g, "*") + "\n",
  );
  //    7b) 只有开 $$ 没有闭 $$/$,纯文字行尾的未闭合块(L226 的 96.4 m³/h 这条)
  //         (注意: step 0 全局 &gt;→> 已先跑,故此处匹配 $$> 而非 $$&gt;)
  s = s.replace(
    /^\$\$>([^\n]+)/gm,
    (_m: string, content: string) =>
      "> " + content.replace(/\\\*/g, "*").replace(/\\{2,}\*/g, "*"),
  );
  // 8) 表格行全部挤到一行(编辑器保存丢失换行) → 按分隔行 |:--- 作锚点,按列数拆分重组各行
  s = splitCollapsedTableLines(s);
  return s;
}

/**
 * 修复编辑器保存时表格换行全部丢失——整张表拼成一行。
 * 识别分隔行 `|:---` 或 `|---` 为锚点,按表头的管道数拆分行。
 */
function splitCollapsedTableLines(md: string): string {
  if (!/ \| \|:(?=-+)/.test(md) && !/ \| \|-(?=-+)/.test(md)) return md;
  return md.split("\n").map(splitOneTableLine).join("\n");
}

function splitOneTableLine(line: string): string {
  // 必须同时有普通表头 | xxx | 和紧随的分隔标记 |:---
  if (!/ \| \|:(?=-+)/.test(line) && !/ \| \|-(?=-+)/.test(line)) return line;
  // 找到分隔行起始 (|: 或 |- 紧跟在表头闭管后面,中间隔着一个 space-pipe-space)
  const sepStart = line.search(/ \| \|:(-+)/);
  if (sepStart < 0) return line;
  const header = line.slice(0, sepStart + 1); // 含表头闭管 |
  // 跳过 " |" (header row-boundary), rest 从分隔行开头的 |: 开始
  const rest = line.slice(sepStart + 3); // +1=闭管, +2=空格, +3=分隔行第一个 |
  // 表头管道总数(含首尾管) = 每行管道数
  const colCount = (header.match(/\|/g) ?? []).length;
  // 找到分隔行结束: 第一个后面跟着普通文本(非 : 非 -)的 | 即数据行起点
  const sepRowEnd = rest.search(/\| [^:\-]/);
  const sepEnd = sepRowEnd > 0 ? sepRowEnd : rest.length;
  const sepRow = rest.slice(0, sepEnd).trimEnd(); // |:---|:---|...  分隔行(已含开头管)
  if (!sepRow.startsWith("|")) return line; // 防御
  const dataPart = rest.slice(sepEnd); // 从数据行第一个 | 开始
  // 按 colCount 拆分: 每个完整数据行 = colCount 个管道
  const dataRows: string[] = [];
  let cur = "";
  let pipes = 0;
  for (const ch of dataPart) {
    cur += ch;
    if (ch === "|") {
      pipes++;
      if (pipes === colCount) {
        dataRows.push(cur.trimEnd());
        cur = "";
        pipes = 0;
      }
    }
  }
  if (cur.trim()) dataRows.push(cur.trim());
  return [header, sepRow, ...dataRows].map((r) => r.trim()).join("\n");
}

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
