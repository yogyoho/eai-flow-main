// EAI-CUSTOM: 文档编辑器辅助纯函数（B 组：字数统计 + 查找/替换文本重写）。
// 从 DocumentManagement / PersonalBlockNoteEditor 抽出以便单测。

export interface DocStats {
  /** 字数 = 汉字数 + 连续拉丁/数字词数 */
  words: number;
  /** 非空白字符数 */
  chars: number;
}

/** 从 markdown 文本计算文档统计（剥离代码块/图片/链接/标题/markdown 符号后计数）。 */
export function computeDocStats(md: string): DocStats {
  if (!md) return { words: 0, chars: 0 };
  const text = md
    .replace(/^```[\s\S]*?```$/gm, "") // 代码块
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // 图片
    .replace(/\[[^\]]*\]\([^)]*\)/g, "") // 链接
    .replace(/^#{1,6}\s+/gm, "") // 标题标记
    .replace(/[*_`>#|\-]/g, ""); // 其余 markdown 符号
  const cjk = (text.match(/[一-鿿㐀-䶿]/g) ?? []).length;
  const latin = (text.match(/[A-Za-z0-9]+/g) ?? []).length;
  return { words: cjk + latin, chars: text.replace(/\s/g, "").length };
}

/** 块内联内容节点的结构子集（文本节点，宽松类型） */
interface ContentNode {
  type: string;
  text?: string;
}

/**
 * 在块内文本节点中替换 query（逐节点匹配，不跨节点）。
 * 返回新 content（即使无替换也返回新数组）与替换次数；调用方仅当 replaced > 0 时 updateBlock。
 */
export function replaceTextInContent(
  content: ContentNode[],
  query: string,
  replacement: string,
): { content: ContentNode[]; replaced: number } {
  if (!query) return { content, replaced: 0 };
  let replaced = 0;
  const newContent = content.map((node: ContentNode) => {
    if (node.type !== "text" || !node.text) return node;
    const parts = node.text.split(query);
    if (parts.length > 1) {
      replaced += parts.length - 1;
      return { ...node, text: parts.join(replacement) };
    }
    return node;
  });
  return { content: newContent, replaced };
}
