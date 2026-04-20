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
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

export function extractHeadings(editor: Editor): HeadingInfo[] {
  const headings: HeadingInfo[] = [];
  const doc = editor.state.doc;

  doc.descendants((node, pos) => {
    if (node.type.name === "heading") {
      const level = node.attrs.level as number;
      const text = node.textContent || "";
      const id = slugify(text) || `heading-${pos}`;
      const element = editor.view.nodeDOM(pos) as HTMLElement;
      if (element) headings.push({ id, level, text, element });
    }
  });

  return headings;
}
