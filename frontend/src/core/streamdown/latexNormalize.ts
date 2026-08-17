// ponytail: KaTeX 字体缺 ²³¹℃° 等字符的 text-mode metric（console 警告 "No character
// metrics"），且 \text{...^N...} 里脱字符会报错变红。把 \text{...} 尾部的上标/度数 unicode
// 移到 \text{} 外面作 ^{...}，KaTeX 才能正确渲染成上标。数学模式下的 ²³¹ KaTeX 已自动处理。
// 已知 ceiling：仅处理 \text{...} 末尾连续的上标/度数；文本中间的 ²³¹ 仍是字面字符（罕见）。

const SUP_MAP: Record<string, string> = {
  "⁰": "0",
  "¹": "1",
  "²": "2",
  "³": "3",
  "⁴": "4",
  "⁵": "5",
  "⁶": "6",
  "⁷": "7",
  "⁸": "8",
  "⁹": "9",
};

/**
 * Normalize LaTeX so KaTeX renders unicode superscripts/degrees that it otherwise can't.
 * Moves trailing ²³¹… / ℃ / ° out of `\text{...}` into proper `^{...}` superscripts.
 */
export function normalizeLatexForKatex(input: string): string {
  if (!input) return input;
  // 编辑器 markdown 往返会把 \frac 存成 \\frac(双反斜杠);KaTeX 把 \\ 当换行,命令变文本 → 渲染坏。
  // 归一 \\X → \X(只压字母命令,不碰 \\ 换行符=非字母场景)。
  const s = input.replace(/\\{2,}([a-zA-Z])/g, "\\$1");
  return s.replace(/\\text\{([^{}]*)\}/g, (whole, content: string) => {
    let cleaned = content;
    let tail = "";
    let changed = true;
    while (changed) {
      changed = false;
      const last = cleaned.slice(-1);
      if (SUP_MAP[last]) {
        tail = `^{${SUP_MAP[last]}}${tail}`;
        cleaned = cleaned.slice(0, -1);
        changed = true;
      } else if (last === "℃") {
        tail = `^{\\circ}C${tail}`;
        cleaned = cleaned.slice(0, -1);
        changed = true;
      } else if (last === "°") {
        tail = `^{\\circ}${tail}`;
        cleaned = cleaned.slice(0, -1);
        changed = true;
      }
    }
    return `\\text{${cleaned}}${tail}`;
  });
}

/**
 * rehype plugin: normalize raw LaTeX inside math elements before rehype-katex renders them.
 * rehype-katex v7 reads className `math-display`/`math-inline`/`language-math` elements and
 * takes their text content as the latex (NOT a `type:'math'` node.value). So we rewrite the
 * text children of those elements. Place BEFORE rehypeKatex in the rehype chain.
 */
export function rehypeNormalizeMath() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (tree: any) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const textOf = (n: any): string => {
      if (!n) return "";
      if (n.type === "text") return n.value ?? "";
      if (Array.isArray(n.children)) return n.children.map(textOf).join("");
      return "";
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const walk = (node: any) => {
      if (node?.type === "element") {
        const cls = node.properties?.className;
        const classes = Array.isArray(cls) ? cls : [];
        if (
          classes.includes("math-display") ||
          classes.includes("math-inline") ||
          classes.includes("language-math")
        ) {
          const raw = textOf(node);
          const normalized = normalizeLatexForKatex(raw);
          if (normalized !== raw) {
            node.children = [{ type: "text", value: normalized }];
          }
        }
      }
      if (node && Array.isArray(node.children)) {
        for (const c of node.children) walk(c);
      }
    };
    walk(tree);
    return tree;
  };
}
