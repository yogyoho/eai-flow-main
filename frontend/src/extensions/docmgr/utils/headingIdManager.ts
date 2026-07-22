/**
 * headingIdManager.ts
 * Manages heading IDs for table of contents
 */

import type { Editor } from "@tiptap/react";

export interface HeadingInfo {
  id: string;
  level: number;
  text: string;
  element: HTMLElement;
}

function slugify(text: string): string {
  // ponytail: \w 不含中文 → 改用 \p{L}\p{N}（Unicode 字母+数字）保留中文
  // 避免"第1章"和"第2章"slugify后只剩数字、碰撞被去重
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

export function extractHeadings(editor: Editor): HeadingInfo[] {
  const headings: HeadingInfo[] = [];
  const doc = editor.state.doc;
  // ponytail: 用 pos 做 fallback ID 前缀,避免纯中文标题 slugify 碰撞后被去重
  let counter = 0;

  doc.descendants((node, pos) => {
    if (node.type.name === "heading") {
      const level = node.attrs.level as number;
      const text = node.textContent || "";
      const slug = slugify(text);
      // slug 为空或太短时用 pos 保证唯一
      const id = slug && slug.length > 1 ? slug : `h-${pos}-${counter++}`;
      const element = editor.view.nodeDOM(pos) as HTMLElement;
      if (element) headings.push({ id, level, text, element });
    }
  });

  return headings;
}
