/**
 * 正文目录(batch 34):从 AST/PM doc 提取 section 并稳定定位。
 *
 * 左栏「文档结构」必须来自正文本身,而不是响应矩阵的 target_section 分组;
 * 点击目录只做滚动定位,不改文档内容/选择区。
 */
import type { Node as PMNode } from "prosemirror-model";

import { type AstJsonNode } from "./schema.gen";

export interface DocSection {
  key: string;
  title: string;
  level: number;
  index: number;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asLevel(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 1;
}

/** section 的稳定键:优先 section_id,缺省按正文顺序编号。 */
export function sectionKey(
  attrs: Record<string, unknown> | undefined,
  index: number,
): string {
  const sectionId = asString(attrs?.section_id).trim();
  return sectionId ? `id:${sectionId}` : `index:${index}`;
}

export function astSections(ast: AstJsonNode | null | undefined): DocSection[] {
  const out: DocSection[] = [];
  let index = 0;
  const walk = (node: AstJsonNode | undefined) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "section") {
      index += 1;
      out.push({
        key: sectionKey(node.attrs, index - 1),
        title: asString(node.attrs?.title) || `未命名章节 ${index}`,
        level: asLevel(node.attrs?.level),
        index: index - 1,
      });
    }
    for (const child of node.content ?? []) walk(child);
  };
  walk(ast ?? undefined);
  return out;
}

/** 在 PM doc 中找目录项对应位置;找不到返回 null(不猜、不静默跳到别处)。 */
export function findSectionPos(doc: PMNode, key: string): number | null {
  let index = 0;
  let found: number | null = null;
  doc.descendants((node, pos) => {
    if (found !== null) return false;
    if (node.type.name === "section") {
      const attrs = node.attrs as Record<string, unknown>;
      if (sectionKey(attrs, index) === key) {
        found = pos;
        return false;
      }
      index += 1;
    }
    return true;
  });
  return found;
}
