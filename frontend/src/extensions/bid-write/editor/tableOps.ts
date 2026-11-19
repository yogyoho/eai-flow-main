// EAI-CUSTOM 批卅三 T1——表格行操作:加行/删行(用户痛点:表格不能加行)。
// 价格表(table_type=price)拒绝:行结构(金额/合计/加总链)属报价面,由③配置
// 与素材证据驱动,手加行会破坏 SK-PS-003/007/008 断言面。响应表/清单表全支持。
// 新行克隆末行单元格类型与 attrs,content 全空(enum_cell current="" 与空内容
// 满足 M1 不变式 textContent≡current)。
import { type Node as PMNode } from "prosemirror-model";
import { type EditorState, type Transaction } from "prosemirror-state";

function findTable(
  $from: EditorState["selection"]["$from"],
): { depth: number; node: ReturnType<EditorState["selection"]["$from"]["node"]> } | null {
  for (let d = $from.depth; d > 0; d--) {
    const node = $from.node(d);
    if (node.type.name === "table") return { depth: d, node };
  }
  return null;
}

export function addRowInSelection(state: EditorState): Transaction | null {
  const hit = findTable(state.selection.$from);
  if (!hit) return null;
  if (String(hit.node.attrs.table_type) === "price") return null;
  const lastRow = hit.node.child(hit.node.childCount - 1);
  const cells: PMNode[] = [];
  for (let i = 0; i < lastRow.childCount; i++) {
    const cell = lastRow.child(i);
    cells.push(cell.type.create({ ...cell.attrs }, []));
  }
  const row = state.schema.nodes.table_row!.create({ row_id: "" }, cells);
  // after(hit.depth) 是表节点之后(兄弟位,PM transform 不校验 fit 会造成非法
  // 文档)——-1 落到表闭合 token 前=表内末行之后
  return state.tr.insert(state.selection.$from.after(hit.depth) - 1, row);
}

export function deleteRowInSelection(state: EditorState): Transaction | null {
  const $from = state.selection.$from;
  const hit = findTable($from);
  if (!hit) return null;
  if (String(hit.node.attrs.table_type) === "price") return null;
  if (hit.node.childCount <= 1) return null; // 保底:不留空表
  const rowDepth = hit.depth + 1;
  const rowPos = $from.before(rowDepth);
  const rowSize = $from.node(rowDepth).nodeSize;
  return state.tr.delete(rowPos, rowPos + rowSize);
}
