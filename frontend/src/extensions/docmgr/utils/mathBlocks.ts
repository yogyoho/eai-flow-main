// EAI-CUSTOM: BlockNote ↔ markdown 数学公式块转换纯函数。
// 从 PersonalBlockNoteEditor.tsx 抽出以便单测（@defensestation/blocknote-math 无 toMarkdown，
// 需在 blocksToMarkdownLossy 前手动回写；加载时也需手动把 $...$ / $$...$$ 文本转成 latex/equation 节点）。

/**
 * Block types whose inline content may contain $...$ / $$...$$ math.
 * EAI-CUSTOM: "heading" 原缺失 → 标题内联公式（如 $V_s$）加载/输入时都不转换、原样显示字面文本。
 * 已补上，标题内联 $...$ 现在会被转成 latex 内联节点渲染。
 */
export const TEXT_BLOCK_TYPES = new Set([
  "paragraph",
  "bulletListItem",
  "numberedListItem",
  "checkListItem",
  "heading",
]);

// 只有 paragraph 类块才允许被整段 $$...$$ 替换成独立 equation 块。
// 标题是结构性块：`## $$E=mc^2$$` 不能变成公式块丢标题层级（只做行内转换）。
const EQUATION_CAPABLE_TYPES = new Set([
  "paragraph",
  "bulletListItem",
  "numberedListItem",
  "checkListItem",
]);

// ── 宽松结构类型（BlockNote 块 + 自定义 equation/latex 节点的结构子集） ──
/** 行内内容节点：文本节点或自定义 latex 节点 */
export interface InlineNode {
  type: string;
  text?: string;
  props?: { latex?: string; displayMode?: boolean };
  styles?: Record<string, unknown>;
}

/** 表格单元格 */
export interface TableCellStyle {
  content?: InlineNode[];
}

/** 表格行 */
export interface TableRowStyle {
  cells?: TableCellStyle[];
}

/** 表格内容 */
export interface TableContentStyle {
  type: string;
  rows?: TableRowStyle[];
}

/** 块节点（含自定义 equation 块；props 用索引签名兼容 level 等任意块属性） */
export interface BlockNode {
  type: string;
  id?: string;
  props?: { latex?: string; [key: string]: unknown };
  content?: InlineNode[] | TableContentStyle;
  children?: BlockNode[];
}

/** 把内联内容里的 $...$ 文本节点转成 latex 内联节点。不修改原对象；返回 { content, changed }。 */
export function convertInlineMathInContent(content: InlineNode[]): {
  content: InlineNode[];
  changed: boolean;
} {
  let changed = false;
  const newContent: InlineNode[] = [];
  for (const node of content) {
    if (node.type !== "text" || !node.text) {
      newContent.push(node);
      continue;
    }
    const text: string = node.text;
    const parts = text.split(/(\$[^$\n]+\$)/g);
    if (parts.every((p: string) => !/^\$[^$\n]+\$$/.test(p))) {
      newContent.push(node);
      continue;
    }
    changed = true;
    for (const part of parts) {
      const m = /^\$([^$\n]+)\$$/.exec(part);
      if (m) {
        newContent.push({
          type: "latex",
          props: { latex: m[1]!.trim(), displayMode: false },
        });
      } else if (part) {
        newContent.push({ ...node, text: part });
      }
    }
  }
  return { content: newContent, changed };
}

// ── Markdown 导出回写 ────────────────────────────────────────────────
// ponytail: @defensestation/blocknote-math 定义不了 toMarkdown（只有 toExternalHTML），
// blocksToMarkdownLossy 会静默跳过 "content: none" 类型，公式从保存的 markdown 里消失 → 重进损坏。
// 修复：blocksToMarkdownLossy 前复制一份块，equation→paragraph($$...$$)、latex→text($...$)，
// 导出才正确。不改编辑器状态——只操作浅拷贝。
export function prepareBlocksForMarkdownExport(
  blocks: BlockNode[],
): BlockNode[] {
  return blocks.map((block: BlockNode) => {
    // equation block → paragraph with $$latex$$
    if (block.type === "equation") {
      const latex: string = block.props?.latex ?? "";
      return {
        type: "paragraph",
        props: {},
        content: [{ type: "text", text: `$$${latex}$$`, styles: {} }],
        children: block.children ?? [],
        id: block.id,
      };
    }
    // table: scan cells for latex inline content → $latex$
    const tableContent =
      block.type === "table" && !Array.isArray(block.content)
        ? block.content
        : undefined;
    if (
      tableContent?.type === "tableContent" &&
      Array.isArray(tableContent?.rows)
    ) {
      const newRows = tableContent.rows.map((row: TableRowStyle) => ({
        ...row,
        cells: (row.cells ?? []).map((cell: TableCellStyle) => {
          if (!cell || !Array.isArray(cell.content)) return cell;
          let changed = false;
          const newContent = cell.content.map((node: InlineNode) => {
            if (node.type === "latex") {
              changed = true;
              return {
                type: "text",
                text: `$${node.props?.latex ?? ""}$`,
                styles: {},
              };
            }
            return node;
          });
          return changed ? { ...cell, content: newContent } : cell;
        }),
      }));
      return { ...block, content: { ...tableContent, rows: newRows } };
    }
    // paragraph / heading: scan for latex inline content → $latex$
    if (Array.isArray(block.content)) {
      let changed = false;
      const newContent = block.content.map((node: InlineNode) => {
        if (node.type === "latex") {
          changed = true;
          return {
            type: "text",
            text: `$${node.props?.latex ?? ""}$`,
            styles: {},
          };
        }
        return node;
      });
      return changed ? { ...block, content: newContent } : block;
    }
    return block;
  });
}

// ── 加载转换 ─────────────────────────────────────────────────────────
// BlockNote 内置 markdown 解析不认识自定义 math 块类型（equation/latex）。
// 把解析出的块里 $$...$$ → equation 块、$...$ → latex 内联节点。
export function transformMathInBlocks(blocks: BlockNode[]): BlockNode[] {
  const result: BlockNode[] = [];
  for (const block of blocks) {
    if (TEXT_BLOCK_TYPES.has(block.type) && Array.isArray(block.content)) {
      const fullText = block.content
        .filter((c) => c.type === "text")
        .map((c) => c.text ?? "")
        .reduce((acc: string, c: string) => acc + c, "");

      // 整段 $$...$$ → equation 块（仅 paragraph 类；标题保持标题结构）
      if (EQUATION_CAPABLE_TYPES.has(block.type)) {
        const blockMatch = /^\$\$([\s\S]*?)\$\$$/.exec(fullText);
        if (
          blockMatch &&
          block.content.every((c) => c.type === "text" || !c.text?.trim())
        ) {
          result.push({
            type: "equation",
            props: { latex: blockMatch[1]!.trim() },
          });
          continue;
        }
      }

      // 行内 $...$（含标题）
      const { content: newContent, changed } = convertInlineMathInContent(
        block.content,
      );
      result.push(changed ? { ...block, content: newContent } : block);
      continue;
    }
    // Handle table blocks: scan cells for $...$ inline math
    const tableContent =
      block.type === "table" && !Array.isArray(block.content)
        ? block.content
        : undefined;
    if (
      tableContent?.type === "tableContent" &&
      Array.isArray(tableContent?.rows)
    ) {
      const newRows = tableContent.rows.map((row: TableRowStyle) => ({
        ...row,
        cells: (row.cells ?? []).map((cell: TableCellStyle) => {
          // cell = { type: "tableCell", content: [...], props: {...} }
          if (!cell || !Array.isArray(cell.content)) return cell;
          let changed = false;
          const newContent = cell.content
            .map((node: InlineNode): InlineNode[] => {
              if (node.type !== "text" || !node.text) return [node];
              const text: string = node.text;
              const parts = text.split(/(\$[^$]+\$)/g);
              if (parts.every((p: string) => !/^\$[^$]+\$$/.test(p)))
                return [node];
              changed = true;
              return parts
                .map((part: string): InlineNode | null => {
                  const m = /^\$([^$]+)\$$/.exec(part);
                  return m
                    ? {
                        type: "latex",
                        props: { latex: m[1]!.trim(), displayMode: false },
                      }
                    : part
                      ? { ...node, text: part }
                      : null;
                })
                .filter((n): n is InlineNode => n !== null);
            })
            .flat();
          return changed ? { ...cell, content: newContent } : cell;
        }),
      }));
      result.push({ ...block, content: { ...tableContent, rows: newRows } });
      continue;
    }
    result.push(block);
  }

  // ── Second pass: merge multi-paragraph $$...$$ into equation blocks ──
  // ponytail: AI 生成的 markdown 常把 $$ 单独成行、内容夹空行，拆成三个段落（$$ / 内容 / $$），
  // 单段正则匹配不到。跨连续段扫描合并 $$...$$。
  const merged: BlockNode[] = [];
  let i = 0;
  while (i < result.length) {
    const block = result[i]!;
    if (
      block.type === "paragraph" &&
      Array.isArray(block.content) &&
      block.content.length === 1 &&
      block.content[0]?.type === "text"
    ) {
      const trimmed = (block.content[0].text ?? "").trim();
      if (trimmed === "$$") {
        // Opening $$ found — collect content until closing $$
        const contentParts: string[] = [];
        let j = i + 1;
        let found = false;
        while (j < result.length) {
          const nb = result[j]!;
          if (
            nb.type === "paragraph" &&
            Array.isArray(nb.content) &&
            nb.content.length === 1 &&
            nb.content[0]?.type === "text"
          ) {
            const nt = (nb.content[0].text ?? "").trim();
            if (nt === "$$") {
              found = true;
              break;
            }
          }
          // Collect block text as part of the equation content
          if (nb.type === "paragraph" && Array.isArray(nb.content)) {
            contentParts.push(
              nb.content
                .filter((c) => c.type === "text")
                .map((c) => c.text ?? "")
                .join(""),
            );
          } else if (nb.type === "equation") {
            contentParts.push(`$$${nb.props?.latex ?? ""}$$`);
          }
          j++;
        }
        if (found && contentParts.length > 0) {
          const latex = contentParts.join("\n").trim();
          if (latex) {
            merged.push({ type: "equation", props: { latex } });
            i = j + 1;
            continue;
          }
        }
      }
    }
    merged.push(block);
    i++;
  }
  return merged;
}
