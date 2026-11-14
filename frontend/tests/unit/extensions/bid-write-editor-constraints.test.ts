// EAI-CUSTOM 批廿七 M1——constraints 守卫单测(node env:EditorState.apply 直跑 filterTransaction)
import { describe, expect, it } from "@rstest/core";
import { undo } from "prosemirror-history";
import {
  EditorState,
  NodeSelection,
  TextSelection,
  type Transaction,
} from "prosemirror-state";

import {
  findProtected,
  setEnumValue,
} from "@/extensions/bid-write/editor/constraints";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { createBidWriteEditorState, systemTr } from "@/extensions/bid-write/editor/state";

/** 演示文档中首个含 needle 的文本节点位置 */
function textPos(state: EditorState, needle: string): number {
  let hit = -1;
  state.doc.descendants((node, pos) => {
    if (hit >= 0) return false;
    if (node.isText && (node.text ?? "").includes(needle)) {
      hit = pos;
      return false;
    }
    return true;
  });
  if (hit < 0) throw new Error(`text not found: ${needle}`);
  return hit;
}

/** 含 rowNeedle 文本的 table_row 中,指定列(col_role 或节点名)单元格的位置 */
function cellPos(
  state: EditorState,
  rowNeedle: string,
  pick: { colRole?: string; typeName?: string },
): number {
  let rowPos = -1;
  state.doc.descendants((node, pos) => {
    if (rowPos >= 0) return false;
    if (node.type.name === "table_row" && node.textContent.includes(rowNeedle)) {
      rowPos = pos;
      return false;
    }
    return true;
  });
  if (rowPos < 0) throw new Error(`row not found: ${rowNeedle}`);
  const row = state.doc.nodeAt(rowPos);
  if (!row) throw new Error("row node missing");
  let cell = -1;
  row.forEach((child, offset) => {
    if (cell >= 0) return;
    const roleOk = pick.colRole ? child.attrs.col_role === pick.colRole : true;
    const typeOk = pick.typeName ? child.type.name === pick.typeName : true;
    if (roleOk && typeOk) cell = rowPos + 1 + offset;
  });
  if (cell < 0) throw new Error(`cell not found in row: ${rowNeedle}`);
  return cell;
}

/** 在 pos+1(单元格内容起点)插入一个字符的 user 事务 */
function insertInCell(state: EditorState, pos: number): Transaction {
  const tr = state.tr;
  tr.setSelection(TextSelection.create(tr.doc, pos + 1));
  tr.insertText("X");
  return tr;
}

/** 在文本节点 needle 内 offset 处插入一个字符 */
function insertInText(state: EditorState, needle: string, offset = 2): Transaction {
  const tr = state.tr;
  tr.setSelection(TextSelection.create(tr.doc, textPos(state, needle) + offset));
  tr.insertText("X");
  return tr;
}

function docText(state: EditorState): string {
  return state.doc.textBetween(0, state.doc.content.size, "\n", "");
}

describe("M1 约束过滤(方案 §5.2/5.3/5.4/5.6)", () => {
  it("普通 para 编辑放行", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(insertInText(s0, "根据贵方招标文件"));
    expect(s1).not.toBe(s0);
  });

  it("locked_paragraph 禁改 + 违规提示含 SK-BL-007(§5.2)", () => {
    const violations: string[] = [];
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {
      onViolation: (v) => violations.push(v.message),
    });
    const s1 = s0.apply(insertInText(s0, "本投标函自开标之日起"));
    expect(s1).toBe(s0);
    expect(violations[0]).toContain("SK-BL-007");
  });

  it("amount_cell 只读(§5.3)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = cellPos(s0, "设备 A", { typeName: "amount_cell" });
    expect(s0.apply(insertInCell(s0, pos))).toBe(s0);
  });

  it("table_cell qty/unit 来源列只读(§5.6 SK-PS-002)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const qty = cellPos(s0, "设备 A", { colRole: "qty" });
    expect(s0.apply(insertInCell(s0, qty))).toBe(s0);
    const unit = cellPos(s0, "安装调试", { colRole: "unit" });
    expect(s0.apply(insertInCell(s0, unit))).toBe(s0);
  });

  it("table_cell name 列可编辑(对照)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const name = cellPos(s0, "设备 A", { colRole: "name" });
    const s1 = s0.apply(insertInCell(s0, name));
    expect(s1).not.toBe(s0);
    expect(docText(s1)).toContain("X设备 A");
  });

  it("enum_cell 禁自由输入(§5.4)", () => {
    const violations: string[] = [];
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {
      onViolation: (v) => violations.push(v.message),
    });
    const pos = cellPos(s0, "合计", { typeName: "enum_cell" });
    const s1 = s0.apply(insertInCell(s0, pos));
    expect(s1).toBe(s0);
    expect(violations[0]).toContain("下拉");
  });

  it("setEnumValue 合法通道:attr+文本同改,user 源可撤销(§5.4)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = cellPos(s0, "合计", { typeName: "enum_cell" });
    const tr = setEnumValue(s0, pos, "正偏离");
    expect(tr).not.toBeNull();
    const s1 = s0.apply(tr as Transaction);
    expect(s1).not.toBe(s0);
    expect(docText(s1)).toContain("正偏离");
    expect(docText(s1)).not.toContain("完全响应");
    expect(s1.doc.nodeAt(pos)?.attrs.current).toBe("正偏离");
  });

  it("undo 可撤销枚举切换且不被守卫拦截(不变式天然放行)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = cellPos(s0, "合计", { typeName: "enum_cell" });
    const s1 = s0.apply(setEnumValue(s0, pos, "负偏离") as Transaction);
    let captured: Transaction | undefined;
    const ok = undo(s1, (t) => {
      captured = t;
    });
    expect(ok).toBe(true);
    const s2 = s1.apply(captured as Transaction);
    expect(docText(s2)).toContain("完全响应");
    expect(s2.doc.nodeAt(pos)?.attrs.current).toBe("完全响应");
  });

  it("todo_block 禁删", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    let todoPos = -1;
    s0.doc.descendants((node, pos) => {
      if (todoPos < 0 && node.type.name === "todo_block") {
        todoPos = pos;
        return false;
      }
      return true;
    });
    const tr = s0.tr;
    tr.setSelection(NodeSelection.create(tr.doc, todoPos));
    tr.deleteSelection();
    expect(s0.apply(tr)).toBe(s0);
  });

  it("selection-only 事务放行(docChanged=false)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const tr = s0.tr;
    tr.setSelection(TextSelection.create(s0.doc, textPos(s0, "根据贵方招标文件") + 1));
    expect(s0.apply(tr)).not.toBe(s0);
  });

  it("system 事务放行(§5.2 审批替换通道)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const s1 = s0.apply(systemTr(insertInText(s0, "本投标函自开标之日起")));
    expect(s1).not.toBe(s0);
  });

  it("findProtected 直接判定违规码", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const amount = cellPos(s0, "设备 A", { typeName: "amount_cell" });
    expect(findProtected(s0.doc, amount + 1, amount + 1)?.code).toBe("amount_cell");
    expect(findProtected(s0.doc, 1, 1)).toBeNull();
  });
});
