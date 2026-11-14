// EAI-CUSTOM 批廿九 M3——负偏离展开(方案 §5.4):enum_cell current=负偏离 ⇔
// 所属 table 后存在 deviation_note(row_id 关联)。appendTransaction 自愈不变式:
//  · 负偏离行 ∧ 无 note → 表后插 note(偏离原因/替代方案 两 labeled para);
//  · note 缺 labeled para → 补(破损自愈,含手删;PM appendTransaction 迭代至不动点);
//  · 行非负偏离(或行没了)∧ note 双字段全空 → 收拢删除;
//  · 行非负偏离 ∧ note 有内容 → 保留(用户文本零丢失),由 editorLocalAssert
//    出 D1 孤儿提示人工撤回。
// appended tr 只 setMeta("source","system") 过 constraints filterTransaction;
// 不设 addToHistory=false —— prosemirror-history 把 appended tr 并入当前事务
// 同一 undo 事件,一撤=翻策略+展开面一起回。
import { type Node as PMNode, type Schema } from "prosemirror-model";
import { Plugin, type EditorState, type Transaction } from "prosemirror-state";

export const REASON_LABEL = "偏离原因";
export const ALT_LABEL = "替代方案";

interface NoteInfo {
  pos: number;
  end: number;
  hasReason: boolean;
  reasonFilled: boolean;
  hasAlt: boolean;
  altFilled: boolean;
}

interface Op {
  pos: number;
  to?: number;
  node?: PMNode;
}

function labeledPara(schema: Schema, label: string): PMNode {
  return schema.nodes.para!.create({ label });
}

function buildNote(schema: Schema, rowId: string): PMNode {
  return schema.nodes.deviation_note!.create(
    { row_id: rowId },
    [labeledPara(schema, REASON_LABEL), labeledPara(schema, ALT_LABEL)],
  );
}

/** 负偏离行 → 所属 table 末位(展开面插入点);row_id 全文唯一约定,首行胜出。 */
function collectNegativeRows(doc: PMNode): Map<string, number> {
  const map = new Map<string, number>();
  doc.descendants((node, pos, parent) => {
    if (node.type.name !== "enum_cell" || parent?.type.name !== "table_row") return;
    if (String(node.attrs.current ?? "") !== "负偏离") return;
    const rowId = String(parent.attrs.row_id ?? "");
    if (!rowId || map.has(rowId)) return;
    const $pos = doc.resolve(pos);
    for (let d = $pos.depth; d > 0; d--) {
      if ($pos.node(d).type.name === "table") {
        map.set(rowId, $pos.after(d));
        return;
      }
    }
  });
  return map;
}

function collectNotes(doc: PMNode): Map<string, NoteInfo> {
  const map = new Map<string, NoteInfo>();
  doc.descendants((node, pos) => {
    if (node.type.name !== "deviation_note") return;
    const info: NoteInfo = {
      pos,
      end: pos + node.nodeSize,
      hasReason: false,
      reasonFilled: false,
      hasAlt: false,
      altFilled: false,
    };
    for (let i = 0; i < node.childCount; i++) {
      const child = node.child(i);
      const label = String(child.attrs.label ?? "");
      const filled = child.textContent.trim().length > 0;
      if (label === REASON_LABEL) {
        info.hasReason = true;
        info.reasonFilled = info.reasonFilled || filled;
      } else if (label === ALT_LABEL) {
        info.hasAlt = true;
        info.altFilled = info.altFilled || filled;
      }
    }
    map.set(String(node.attrs.row_id ?? ""), info);
  });
  return map;
}

/** 自愈 diff;调用方 appendTransaction 无 ops 时须返回 null(契约:Transaction|null)。 */
function diffDeviation(state: EditorState): Op[] {
  const rows = collectNegativeRows(state.doc);
  const notes = collectNotes(state.doc);
  const ops: Op[] = [];
  for (const [rowId, tableEnd] of rows) {
    const note = notes.get(rowId);
    if (!note) {
      ops.push({ pos: tableEnd, node: buildNote(state.schema, rowId) });
    } else {
      const noteEnd = note.end - 1; // note 内部末位
      if (!note.hasReason) ops.push({ pos: noteEnd, node: labeledPara(state.schema, REASON_LABEL) });
      if (!note.hasAlt) ops.push({ pos: noteEnd, node: labeledPara(state.schema, ALT_LABEL) });
    }
  }
  for (const [rowId, note] of notes) {
    if (rows.has(rowId)) continue;
    if (!note.reasonFilled && !note.altFilled) ops.push({ pos: note.pos, to: note.end });
    // 非空孤儿保留(assert 面 D1),不在事务里删用户文本
  }
  return ops;
}

export function deviationPlugin(): Plugin<undefined> {
  return new Plugin<undefined>({
    appendTransaction(trs, _old, newState) {
      if (!trs.some((tr) => tr.docChanged)) return null;
      const ops = diffDeviation(newState);
      if (ops.length === 0) return null;
      const tr: Transaction = newState.tr;
      // 位置降序应用:后位先动,前位不漂移
      ops.sort((a, b) => b.pos - a.pos);
      for (const op of ops) {
        if (op.node) tr.insert(op.pos, op.node);
        else tr.delete(op.pos, op.to ?? op.pos);
      }
      tr.setMeta("source", "system");
      return tr; // 契约:单个 Transaction(1.4.4 state 机不摊平数组,返回 [tr] 同样炸)
    },
  });
}
