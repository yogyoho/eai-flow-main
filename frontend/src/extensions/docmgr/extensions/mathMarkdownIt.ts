// ponytail: 极简 markdown-it 数学插件 —— 在状态机层 tokenize $...$/$$...$$,
// 渲染成 mathInline/mathBlock 节点 parseHTML 已匹配的 HTML 元素。
// 替代 encodeMath/decodeMath 正则方案，根治往返损坏。
// markdown-it 的 block/inline ruler 按字符扫描，天然跳过代码块/行内代码。

/** HTML 转义 latex 内容（与 encodeMath 的 escapeAttr 一致） */
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** markdown-it 实例的宽松类型（避免直接 import markdown-it 类型） */
interface MdInstance {
  block: { ruler: { before: (before: string, name: string, fn: Function, opts?: object) => void } };
  inline: { ruler: { after: (after: string, name: string, fn: Function, opts?: object) => void } };
  renderer: { rules: Record<string, (tokens: any[], idx: number) => string> };
}

/** markdown-it block ruler 状态的宽松类型 */
interface BlockState {
  src: string;
  bMarks: number[];
  eMarks: number[];
  tShift: number[];
  line: number;
  push(type: string, tag: string, nesting: number): { content: string; markup: string; map: [number, number]; block: boolean };
}

/** markdown-it inline ruler 状态的宽松类型 */
interface InlineState {
  src: string;
  pos: number;
  posMax: number;
  push(type: string, tag: string, nesting: number): { content: string; markup: string };
}

/**
 * 块级数学规则：识别 $$...$$（单行或跨行）
 * 注册在 paragraph 之前，确保 markdown-it 先处理数学再处理段落
 */
function mathBlockRule(state: BlockState, startLine: number, endLine: number, silent: boolean): boolean {
  const start = state.bMarks[startLine]! + state.tShift[startLine]!;
  const max = state.eMarks[startLine]!;

  // 必须以 $$ 开头
  if (start + 2 > max) return false;
  if (state.src.charCodeAt(start) !== 0x24 /* $ */ || state.src.charCodeAt(start + 1) !== 0x24) return false;

  // $$ 后面的内容
  const afterDelim = state.src.slice(start + 2, max).trim();

  if (silent) return true;

  // 单行情况：$$ latex $$ 在同一行
  if (afterDelim.endsWith("$$") && afterDelim.length > 2) {
    const latex = afterDelim.slice(0, -2).trim();
    if (!latex) return false; // $$$$ → 空数学块，跳过
    const token = state.push("math_block", "div", 0);
    token.content = latex;
    token.markup = "$$";
    token.block = true;
    token.map = [startLine, startLine];
    state.line = startLine + 1;
    return true;
  }

  // 多行情况：$$ 开头，后续行是内容，某行单独 $$ 闭合
  let nextLine = startLine + 1;
  let foundClose = false;
  const lines: string[] = [];
  // 如果 $$ 后面还有内容（afterDelim 非空），它是第一行内容
  if (afterDelim) lines.push(afterDelim);

  while (nextLine < endLine) {
    const ls = state.bMarks[nextLine]! + state.tShift[nextLine]!;
    const le = state.eMarks[nextLine];
    const lt = state.src.slice(ls, le).trim();
    if (lt === "$$") {
      foundClose = true;
      break;
    }
    lines.push(lt);
    nextLine++;
  }

  if (!foundClose) return false; // 未闭合 $$ → 不是数学块

  const latex = lines.join("\n").trim();
  const token = state.push("math_block", "div", 0);
  token.content = latex;
  token.markup = "$$";
  token.block = true;
  token.map = [startLine, nextLine];
  state.line = nextLine + 1;
  return true;
}

/**
 * 行内数学规则：识别 $...$（不跨行）
 * 注册在 escape 之后，确保转义字符先处理
 */
function mathInlineRule(state: InlineState, silent: boolean): boolean {
  // 必须是 $ 开头
  if (state.src.charCodeAt(state.pos) !== 0x24 /* $ */) return false;
  // 排除 $$（块级数学，由 block ruler 处理）
  if (state.src.charCodeAt(state.pos + 1) === 0x24) return false;

  // 前一个字符不能是数字或 $（避开货币 $5、$$ 残留）
  if (state.pos > 0) {
    const prev = state.src.charCodeAt(state.pos - 1);
    // 0x24=$, 0x30-0x39=数字
    if (prev === 0x24 || (prev >= 0x30 && prev <= 0x39)) return false;
  }

  // $ 后第一个字符必须非空白
  const startPos = state.pos + 1;
  if (startPos >= state.posMax) return false;
  if (/\s/.test(state.src[startPos]!)) return false;

  // 找闭合 $（不跨行）
  let end = -1;
  for (let i = startPos + 1; i < state.posMax; i++) {
    const ch = state.src[i];
    if (ch === "\n") return false; // 行内数学不跨行
    if (ch === "$") {
      // 闭合 $ 后不能跟数字（货币）
      if (i + 1 < state.posMax) {
        const next = state.src.charCodeAt(i + 1);
        if (next >= 0x30 && next <= 0x39) continue; // $5 跳过
      }
      // 闭合 $ 前必须非空白
      if (/\s/.test(state.src[i - 1]!)) return false;
      end = i;
      break;
    }
  }
  if (end === -1) return false;

  const latex = state.src.slice(startPos, end).trim();
  if (!latex) return false;

  if (silent) return true;

  const token = state.push("math_inline", "span", 0);
  token.content = latex;
  token.markup = "$";
  state.pos = end + 1;
  return true;
}

/**
 * markdown-it 数学插件入口
 * 用法: md.use(mathMarkdownIt)
 */
export function mathMarkdownIt(md: MdInstance): void {
  // 块级规则：在 paragraph 之前注册，确保 $$ 先于段落处理
  md.block.ruler.before("paragraph", "math_block", mathBlockRule, { alt: ["paragraph", "reference", "blockquote", "list"] });
  // 行内规则：在 escape 之后注册
  md.inline.ruler.after("escape", "math_inline", mathInlineRule);
  // 渲染规则
  md.renderer.rules["math_block"] = (tokens: any[], idx: number) => {
    const latex = escapeHtml(tokens[idx].content);
    return `<div data-math-block data-latex="${latex}"></div>\n`;
  };
  md.renderer.rules["math_inline"] = (tokens: any[], idx: number) => {
    const latex = escapeHtml(tokens[idx].content);
    return `<span data-math-inline data-latex="${latex}"></span>`;
  };
}
