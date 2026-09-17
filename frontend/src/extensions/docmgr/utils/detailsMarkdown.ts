// EAI-CUSTOM (计算书): <details><summary>折叠块的 markdown 导入/导出纯函数。
// 给排水计算书技能(render_calc_blocks.py)特意生成 <details>折叠计算过程；
// 工件区契约保留该 HTML，BlockNote 导入不解析 HTML → 编辑器丢折叠语义。
// 自研 detailsBlock 的两端转换都在这里（不含 React 渲染，便于单测）。

import { type BlockNode, type InlineNode } from "./mathBlocks";

export const DETAILS_BLOCK_TYPE = "detailsBlock";

/** markdown 分段：普通 markdown 文本 或 一个 details 折叠块 */
export interface DetailsSegment {
  kind: "md" | "details";
  /** kind=md：该段 markdown 原文 */
  text?: string;
  /** kind=details：<summary> 内容（去除标签，trim） */
  summary?: string;
  /** kind=details：<details> 内部 markdown */
  inner?: string;
}

const OPEN_TAG = "<details";
const CLOSE_TAG = "</details>";

/**
 * 把 markdown 切成 普通文本段 与 details 块 的有序分段。
 * 用深度计数扫描（非正则）——正确处理嵌套 details；未闭合的 details 原样保留为文本。
 */
export function extractDetailsSegments(md: string): DetailsSegment[] {
  const segments: DetailsSegment[] = [];
  let pos = 0;
  while (true) {
    const open = md.indexOf(OPEN_TAG, pos);
    if (open === -1) break;
    // 深度计数找配对的 </details>
    let depth = 1;
    let cursor = open + OPEN_TAG.length;
    let close = -1;
    while (depth > 0) {
      const nextOpen = md.indexOf(OPEN_TAG, cursor);
      const nextClose = md.indexOf(CLOSE_TAG, cursor);
      if (nextClose === -1) break; // 未闭合：整体放弃，保持为文本
      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth += 1;
        cursor = nextOpen + OPEN_TAG.length;
      } else {
        depth -= 1;
        if (depth === 0) close = nextClose;
        cursor = nextClose + CLOSE_TAG.length;
      }
    }
    if (close === -1) break;
    const block = md.slice(open, close + CLOSE_TAG.length);
    const summaryMatch = /<summary>([\s\S]*?)<\/summary>/i.exec(block);
    const gt = block.indexOf(">");
    const inner = block
      .slice(gt + 1, block.length - CLOSE_TAG.length)
      .replace(/^\s*<summary>[\s\S]*?<\/summary>/i, "")
      .trim();
    if (open > pos) {
      segments.push({ kind: "md", text: md.slice(pos, open) });
    }
    segments.push({
      kind: "details",
      summary: (summaryMatch?.[1] ?? "").trim(),
      inner,
    });
    pos = close + CLOSE_TAG.length;
  }
  if (pos < md.length) {
    segments.push({ kind: "md", text: md.slice(pos) });
  }
  return segments;
}

/**
 * 把含 <details> 的 markdown 组装成 BlockNote 块树（含 detailsBlock 节点）。
 * parse: 通常是 (s) => editor.tryParseMarkdownToBlocks(s)。
 * 注意：返回的是"原始"块——$...$ 数学转换交给 transformMathInBlocks（其 children
 * 递归会覆盖 detailsBlock 子树），本函数不做数学处理。
 */
export function buildBlocksWithDetails(
  md: string,
  parse: (md: string) => BlockNode[],
): BlockNode[] {
  const result: BlockNode[] = [];
  for (const seg of extractDetailsSegments(md)) {
    if (seg.kind === "md") {
      if (seg.text?.trim()) {
        result.push(...parse(seg.text));
      }
      continue;
    }
    const summaryContent: InlineNode[] = seg.summary
      ? [{ type: "text", text: seg.summary, styles: {} }]
      : [];
    result.push({
      type: DETAILS_BLOCK_TYPE,
      // 对齐工件区语义：<details> 不带 open 属性 = 默认收起
      props: { collapsed: true },
      content: summaryContent,
      children: seg.inner ? buildBlocksWithDetails(seg.inner, parse) : [],
    });
  }
  return result;
}

/**
 * 序列化：detailsBlock → <details><summary>…</summary>，其余块按序交给 mdFn
 * （通常 = (bs) => editor.blocksToMarkdownLossy(bs)）。入参应是已经过
 * prepareBlocksForMarkdownExport 数学回写的块。
 */
export function serializeWithDetails(
  blocks: BlockNode[],
  mdFn: (bs: BlockNode[]) => string,
): string {
  const out: string[] = [];
  let run: BlockNode[] = [];
  const flush = () => {
    if (run.length > 0) {
      out.push(mdFn(run));
      run = [];
    }
  };
  for (const b of blocks) {
    if (b.type === DETAILS_BLOCK_TYPE) {
      flush();
      const summary = (Array.isArray(b.content) ? b.content : [])
        .filter((n) => n.type === "text")
        .map((n) => n.text ?? "")
        .join("")
        .trim();
      const inner = serializeWithDetails(b.children ?? [], mdFn);
      out.push(
        `<details><summary>${summary}</summary>\n\n${inner}\n\n</details>`,
      );
    } else {
      run.push(b);
    }
  }
  flush();
  return out.join("\n\n");
}
