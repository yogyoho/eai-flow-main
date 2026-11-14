import { describe, expect, it } from "@rstest/core";
import { EditorState, TextSelection, type Transaction } from "prosemirror-state";
import { redo, undo } from "prosemirror-history";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import {
  createBidWriteEditorState,
  decorTr,
  systemTr,
  trSource,
} from "@/extensions/bid-write/editor/state";

// 标记串避开演示文档既有内容(如「设备 A」)
const USER_MARK = "用户编辑串";
const SYSTEM_MARK = "系统事务串";
const DECOR_MARK = "装饰事务串";

function type(state: EditorState, text: string): Transaction {
  const tr = state.tr;
  tr.setSelection(TextSelection.create(tr.doc, 1));
  tr.insertText(text);
  return tr;
}

describe("meta.source 事务分层(方案 §七 撤销栈口径)", () => {
  it("默认来源 user 且入撤销栈", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(type(s0, USER_MARK));
    expect(trSource(s1.tr)).toBe("user");
    expect(undo(s1, undefined)).toBe(true);
  });

  it("system 事务不入撤销栈,undo 跳过系统内容", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(type(s0, USER_MARK));
    const s2 = s1.apply(systemTr(type(s1, SYSTEM_MARK)));
    let captured: Transaction | null = null;
    expect(undo(s2, (tr) => { captured = tr; })).toBe(true);
    expect(captured).not.toBeNull();
    const s3 = s2.apply(captured as Transaction);
    const text = s3.doc.textBetween(0, s3.doc.content.size, "\n", "");
    expect(text).not.toContain(USER_MARK);
    expect(text).toContain(SYSTEM_MARK);
    expect(redo(s3, undefined)).toBe(true);
  });

  it("decor 事务同样不入栈", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(decorTr(type(s0, DECOR_MARK)));
    expect(undo(s1, undefined)).toBe(false);
  });

  it("trSource 缺省 user", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    expect(trSource(s0.tr)).toBe("user");
  });
});
