// EAI-CUSTOM 批廿六 M0——事务分层 meta.source ∈ {user, system, decor}(方案 §七);
// 撤销栈只收用户编辑:system/decor 事务 setMeta("addToHistory", false)。
// M1 起系统/装饰事务经此二 helper 构造;用户输入默认 user 且入栈。
import { baseKeymap } from "prosemirror-commands";
import { history, redo, undo } from "prosemirror-history";
import { keymap } from "prosemirror-keymap";
import { EditorState, type Transaction } from "prosemirror-state";

import { constraintsPlugin, type OnViolation } from "./constraints";
import { hydrateAst } from "./doc";
import { type AstJsonNode } from "./schema.gen";

export type EditorTrSource = "user" | "system" | "decor";

export function systemTr(tr: Transaction): Transaction {
  tr.setMeta("source", "system");
  tr.setMeta("addToHistory", false);
  return tr;
}

export function decorTr(tr: Transaction): Transaction {
  tr.setMeta("source", "decor");
  tr.setMeta("addToHistory", false);
  return tr;
}

export function trSource(tr: Transaction): EditorTrSource {
  return (tr.getMeta("source") as EditorTrSource | undefined) ?? "user";
}

export function createBidWriteEditorState(
  ast: AstJsonNode,
  options: { onViolation?: OnViolation } = {},
): EditorState {
  return EditorState.create({
    doc: hydrateAst(ast),
    plugins: [
      history(),
      keymap({ "Mod-z": undo, "Mod-Z": redo, "Mod-y": redo }),
      keymap(baseKeymap),
      constraintsPlugin(options),
    ],
  });
}
