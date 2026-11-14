// EAI-CUSTOM 批廿六 M0——AST↔PMdoc 同形映射(方案 §三;AST JSON 与 PM JSON 同形,
// nodeFromJSON 顺带校验 schema 合法性,未知类型抛错)。
import { type Node as PMNode } from "prosemirror-model";

import { type AstJsonNode, bidWriteSchema } from "./schema.gen";

export function hydrateAst(ast: AstJsonNode): PMNode {
  return bidWriteSchema.nodeFromJSON(ast);
}

export function serializeDoc(doc: PMNode): AstJsonNode {
  return doc.toJSON() as AstJsonNode;
}

/** 序列化文本投影(导出投影口径:marks 不进文本,方案 §四 剥离规则)。 */
export function docPlainText(doc: PMNode): string {
  return doc.textBetween(0, doc.content.size, "\n", "");
}
